"""Case-insensitive unique role name per tenant scope.

Revision ID: 0041_roles_unique_per_tenant
Revises: 0040_scorecard_host_version

Platform roles (tenant_id NULL) and tenant roles may share a name. That is
intentional. Uniqueness is case-insensitive inside one scope: NULL tenant is
its own scope, and each tenant_id is its own scope. Same-scope duplicates
keep the oldest row by created_at, then id. Every foreign key to roles.id
is repointed first; association rows that would collide on a unique key are
deleted. A clean database only gains the two partial unique indexes.
Downgrade drops those indexes and does not restore deleted rows.

There is no global unique index on roles.name.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0041_roles_unique_per_tenant"
down_revision = "0040_scorecard_host_version"
branch_labels = None
depends_on = None

_PLATFORM_INDEX = "uq_roles_platform_lower_name"
_TENANT_INDEX = "uq_roles_tenant_lower_name"


def upgrade() -> None:
    # One statement, one transaction. RLS is disabled only for tables this
    # statement touches and restored before it returns. DDL rolls back with
    # the migration if a later step fails.
    op.execute(sa.text(_DEDUPE_SQL))


def downgrade() -> None:
    op.execute(sa.text(f"DROP INDEX IF EXISTS {_TENANT_INDEX}"))
    op.execute(sa.text(f"DROP INDEX IF EXISTS {_PLATFORM_INDEX}"))


_DEDUPE_SQL = f"""
DO $dedupe$
DECLARE
  fk record;
  idx record;
  col record;
  restored record;
  pred text;
  pred_doomed text;
  pred_kept text;
  pred_other text;
  marked text;
  cmp_kept text;
  cmp_other text;
  pred_kept_sql text;
  pred_other_sql text;
  sql text;
  nulls_not_distinct boolean;
BEGIN
  CREATE TEMP TABLE IF NOT EXISTS role_rls_restore (
    schema_name text NOT NULL,
    table_name text NOT NULL,
    force_rls boolean NOT NULL,
    PRIMARY KEY (schema_name, table_name)
  ) ON COMMIT DROP;
  TRUNCATE role_rls_restore;

  CREATE TEMP TABLE IF NOT EXISTS role_dedupe (
    drop_id uuid PRIMARY KEY,
    keep_id uuid NOT NULL
  ) ON COMMIT DROP;
  TRUNCATE role_dedupe;

  INSERT INTO role_rls_restore (schema_name, table_name, force_rls)
  SELECT n.nspname, c.relname, c.relforcerowsecurity
  FROM pg_class c
  JOIN pg_namespace n ON n.oid = c.relnamespace
  WHERE n.nspname = 'public'
    AND c.relname = 'roles'
    AND c.relrowsecurity
  ON CONFLICT DO NOTHING;

  PERFORM 1 FROM role_rls_restore r
  WHERE r.schema_name = 'public' AND r.table_name = 'roles';
  IF FOUND THEN
    EXECUTE 'ALTER TABLE public.roles DISABLE ROW LEVEL SECURITY';
  END IF;

  INSERT INTO role_dedupe (drop_id, keep_id)
  SELECT ranked.id, ranked.keep_id
  FROM (
    SELECT
      id,
      FIRST_VALUE(id) OVER w AS keep_id,
      ROW_NUMBER() OVER w AS rn
    FROM roles
    WINDOW w AS (
      PARTITION BY tenant_id, lower(name)
      ORDER BY created_at ASC, id ASC
    )
  ) AS ranked
  WHERE ranked.rn > 1;

  FOR fk IN
    SELECT
      n.nspname AS schema_name,
      c.relname AS table_name,
      a.attname AS column_name,
      a.attnum AS attnum,
      c.oid AS table_oid,
      c.relrowsecurity AS rowsecurity,
      c.relforcerowsecurity AS forcerowsecurity
    FROM pg_constraint con
    JOIN pg_class c ON c.oid = con.conrelid
    JOIN pg_namespace n ON n.oid = c.relnamespace
    JOIN pg_class rc ON rc.oid = con.confrelid
    JOIN pg_namespace rn ON rn.oid = rc.relnamespace
    JOIN LATERAL unnest(con.conkey, con.confkey) AS cols(src_att, dst_att) ON true
    JOIN pg_attribute a
      ON a.attrelid = c.oid
     AND a.attnum = cols.src_att
     AND NOT a.attisdropped
    JOIN pg_attribute da
      ON da.attrelid = rc.oid
     AND da.attnum = cols.dst_att
    WHERE con.contype = 'f'
      AND rn.nspname = 'public'
      AND rc.relname = 'roles'
      AND da.attname = 'id'
      AND n.nspname NOT IN ('pg_catalog', 'information_schema')
  LOOP
    IF fk.rowsecurity AND NOT EXISTS (
      SELECT 1 FROM role_rls_restore r
      WHERE r.schema_name = fk.schema_name AND r.table_name = fk.table_name
    ) THEN
      INSERT INTO role_rls_restore (schema_name, table_name, force_rls)
      VALUES (fk.schema_name, fk.table_name, fk.forcerowsecurity);
      EXECUTE format(
        'ALTER TABLE %I.%I DISABLE ROW LEVEL SECURITY',
        fk.schema_name, fk.table_name
      );
    END IF;

    FOR idx IN
      SELECT i.indkey, i.indpred, i.indnullsnotdistinct
      FROM pg_index i
      WHERE i.indrelid = fk.table_oid
        AND i.indisunique
        AND i.indisvalid
    LOOP
      IF 0 = ANY (idx.indkey::smallint[]) THEN
        CONTINUE;
      END IF;
      IF NOT (fk.attnum = ANY (idx.indkey::smallint[])) THEN
        CONTINUE;
      END IF;

      nulls_not_distinct := COALESCE(idx.indnullsnotdistinct, false);
      cmp_kept := 'TRUE';
      cmp_other := 'TRUE';
      FOR col IN
        SELECT a.attname
        FROM unnest(idx.indkey::smallint[]) WITH ORDINALITY AS k(attnum, ord)
        JOIN pg_attribute a
          ON a.attrelid = fk.table_oid
         AND a.attnum = k.attnum
        WHERE k.attnum <> fk.attnum
        ORDER BY k.ord
      LOOP
        IF nulls_not_distinct THEN
          cmp_kept := cmp_kept || format(
            ' AND doomed.%I IS NOT DISTINCT FROM kept.%I',
            col.attname, col.attname
          );
          cmp_other := cmp_other || format(
            ' AND doomed.%I IS NOT DISTINCT FROM other.%I',
            col.attname, col.attname
          );
        ELSE
          cmp_kept := cmp_kept || format(
            ' AND doomed.%I = kept.%I',
            col.attname, col.attname
          );
          cmp_other := cmp_other || format(
            ' AND doomed.%I = other.%I',
            col.attname, col.attname
          );
        END IF;
      END LOOP;

      pred := pg_get_expr(idx.indpred, fk.table_oid);
      pred_kept_sql := '';
      pred_other_sql := '';
      IF pred IS NOT NULL THEN
        pred_doomed := pred;
        pred_kept := pred;
        pred_other := pred;
        marked := pred;
        FOR col IN
          SELECT attname
          FROM pg_attribute
          WHERE attrelid = fk.table_oid AND attnum > 0 AND NOT attisdropped
          ORDER BY length(attname) DESC
        LOOP
          marked := regexp_replace(
            marked,
            '\\m' || col.attname || '\\M',
            '$c$' || col.attname || '$c$',
            'g'
          );
        END LOOP;
        pred_doomed := marked;
        pred_kept := marked;
        pred_other := marked;
        FOR col IN
          SELECT attname
          FROM pg_attribute
          WHERE attrelid = fk.table_oid AND attnum > 0 AND NOT attisdropped
        LOOP
          pred_doomed := replace(
            pred_doomed,
            '$c$' || col.attname || '$c$',
            'doomed.' || quote_ident(col.attname)
          );
          pred_kept := replace(
            pred_kept,
            '$c$' || col.attname || '$c$',
            'kept.' || quote_ident(col.attname)
          );
          pred_other := replace(
            pred_other,
            '$c$' || col.attname || '$c$',
            'other.' || quote_ident(col.attname)
          );
        END LOOP;
        pred_kept_sql := ' AND (' || pred_doomed || ') AND (' || pred_kept || ')';
        pred_other_sql := ' AND (' || pred_doomed || ') AND (' || pred_other || ')';
      END IF;

      sql := format(
        'DELETE FROM %I.%I AS doomed USING %I.%I AS kept, role_dedupe AS d '
        'WHERE doomed.%I = d.drop_id AND kept.%I = d.keep_id '
        'AND doomed.ctid <> kept.ctid AND ',
        fk.schema_name, fk.table_name,
        fk.schema_name, fk.table_name,
        fk.column_name, fk.column_name
      );
      EXECUTE sql || cmp_kept || pred_kept_sql;

      sql := format(
        'DELETE FROM %I.%I AS doomed '
        'USING %I.%I AS other, role_dedupe AS d1, role_dedupe AS d2 '
        'WHERE doomed.%I = d1.drop_id AND other.%I = d2.drop_id '
        'AND d1.keep_id = d2.keep_id AND doomed.ctid > other.ctid AND ',
        fk.schema_name, fk.table_name,
        fk.schema_name, fk.table_name,
        fk.column_name, fk.column_name
      );
      EXECUTE sql || cmp_other || pred_other_sql;
    END LOOP;

    EXECUTE format(
      'UPDATE %I.%I AS t SET %I = d.keep_id FROM role_dedupe AS d WHERE t.%I = d.drop_id',
      fk.schema_name, fk.table_name, fk.column_name, fk.column_name
    );
  END LOOP;

  DELETE FROM roles AS r
  USING role_dedupe AS d
  WHERE r.id = d.drop_id;

  IF EXISTS (
    SELECT 1
    FROM (
      SELECT 1
      FROM roles
      GROUP BY tenant_id, lower(name)
      HAVING count(*) > 1
    ) AS still_dup
  ) THEN
    RAISE EXCEPTION 'roles still has same-scope name duplicates';
  END IF;

  EXECUTE
    'CREATE UNIQUE INDEX IF NOT EXISTS {_PLATFORM_INDEX} '
    'ON roles (lower(name)) WHERE tenant_id IS NULL';
  EXECUTE
    'CREATE UNIQUE INDEX IF NOT EXISTS {_TENANT_INDEX} '
    'ON roles (tenant_id, lower(name)) WHERE tenant_id IS NOT NULL';

  FOR restored IN
    SELECT schema_name, table_name, force_rls FROM role_rls_restore
  LOOP
    EXECUTE format(
      'ALTER TABLE %I.%I ENABLE ROW LEVEL SECURITY',
      restored.schema_name, restored.table_name
    );
    IF restored.force_rls THEN
      EXECUTE format(
        'ALTER TABLE %I.%I FORCE ROW LEVEL SECURITY',
        restored.schema_name, restored.table_name
      );
    END IF;
  END LOOP;
END
$dedupe$;
"""
