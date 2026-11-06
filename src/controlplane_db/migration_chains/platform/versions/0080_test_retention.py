"""Private database-bound TEST retention policy and exact-row delete capabilities."""

from alembic import op
import sqlalchemy as sa
from pathlib import Path

revision = "platform_0080_test_retention"
down_revision = "platform_0079_closure_merge"
branch_labels = None
depends_on = None


_AUTHORITY_FUNCTIONS = (
    "account_test_table_name(oid)",
    "account_lock_test_financial_sources(text,timestamptz)",
    "account_test_read_row(oid,text)",
    "account_test_scope(text,timestamptz,text)",
    "account_test_check_row(text,jsonb)",
    "account_test_check_parties(text,text,jsonb,text[])",
    "account_test_edge(oid,oid,jsonb,jsonb)",
    "account_stage_test_delete(text,timestamptz,oid,text,oid,text)",
    "account_delete_test_financial_row(text,timestamptz,oid,text)",
    "account_clear_test_delete_capabilities()",
    "account_test_json_mentions(jsonb,text[])",
    "account_reconcile_test_financial_bindings(text,timestamptz)",
)


def upgrade():
    op.execute("SELECT public.account_lock_financial_inventory_schema()")
    op.execute(
        """CREATE TABLE public.account_test_data_policy (
      singleton boolean PRIMARY KEY DEFAULT true CHECK(singleton),
      database_oid oid NOT NULL, database_name name NOT NULL,
      enabled boolean NOT NULL DEFAULT false,
      cluster_identifier text NOT NULL DEFAULT ((pg_catalog.pg_control_system()).system_identifier::text));
      ALTER TABLE public.account_test_data_policy ENABLE ROW LEVEL SECURITY;
      ALTER TABLE public.account_test_data_policy FORCE ROW LEVEL SECURITY;
      REVOKE ALL ON public.account_test_data_policy FROM PUBLIC;
      CREATE TABLE public.account_test_delete_capabilities (
        transaction_id text NOT NULL, relation oid NOT NULL, row_digest bytea NOT NULL,
        source_subject text, source_closed_at timestamptz, row_tid text,
        PRIMARY KEY(transaction_id,relation,row_digest));
      ALTER TABLE public.account_test_delete_capabilities ENABLE ROW LEVEL SECURITY;
      ALTER TABLE public.account_test_delete_capabilities FORCE ROW LEVEL SECURITY;
      REVOKE ALL ON public.account_test_delete_capabilities FROM PUBLIC;
    """
    )
    op.execute(
        """CREATE FUNCTION public.account_test_data_enabled() RETURNS boolean
    LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,pg_temp SET row_security=off AS $$
      SELECT EXISTS(SELECT 1 FROM public.account_test_data_policy p
        JOIN pg_catalog.pg_database d ON d.oid=p.database_oid AND d.datname=p.database_name
        WHERE p.enabled AND d.datname=current_database()
          AND p.cluster_identifier=(pg_catalog.pg_control_system()).system_identifier::text)
    $$"""
    )
    op.execute(
        """CREATE FUNCTION public.account_lock_test_data_policy() RETURNS boolean
    LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp SET row_security=off AS $$
    BEGIN
      PERFORM 1 FROM public.account_test_data_policy p JOIN pg_catalog.pg_database d
        ON d.oid=p.database_oid AND d.datname=p.database_name
        WHERE p.enabled AND d.datname=current_database()
          AND p.cluster_identifier=(pg_catalog.pg_control_system()).system_identifier::text FOR SHARE OF p NOWAIT;
      RETURN FOUND;
    END $$"""
    )
    op.execute(
        "REVOKE ALL ON FUNCTION public.account_lock_test_data_policy() FROM PUBLIC"
    )
    op.execute(
        """CREATE FUNCTION public.account_test_row_delete_allowed(p_relation oid,p_row jsonb)
    RETURNS boolean LANGUAGE sql VOLATILE SECURITY DEFINER
    SET search_path=pg_catalog,pg_temp SET row_security=off AS $$
      SELECT public.account_lock_test_data_policy() AND EXISTS(
        SELECT 1 FROM public.account_test_delete_capabilities c
        WHERE c.transaction_id=pg_current_xact_id()::text AND c.relation=p_relation
          AND c.row_digest=sha256(convert_to(p_row::text,'UTF8')))
    $$"""
    )
    op.execute("REVOKE ALL ON FUNCTION public.account_test_data_enabled() FROM PUBLIC")
    op.execute(
        "REVOKE ALL ON FUNCTION public.account_test_row_delete_allowed(oid,jsonb) FROM PUBLIC"
    )
    # Only the private coordinator/installed definer guards may inspect TEST state.
    op.execute(
        """CREATE FUNCTION public.account_test_capabilities_ephemeral() RETURNS trigger
    LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp SET row_security=off AS $$ BEGIN
      IF EXISTS(SELECT 1 FROM public.account_test_delete_capabilities
        WHERE transaction_id=NEW.transaction_id AND relation=NEW.relation AND row_digest=NEW.row_digest) THEN
        RAISE EXCEPTION 'TEST delete capabilities cannot survive commit' USING ERRCODE='23514';
      END IF;
      RETURN NULL;
    END $$;
    REVOKE ALL ON FUNCTION public.account_test_capabilities_ephemeral() FROM PUBLIC;
    CREATE CONSTRAINT TRIGGER test_delete_capabilities_ephemeral
      AFTER INSERT ON public.account_test_delete_capabilities DEFERRABLE INITIALLY DEFERRED
      FOR EACH ROW EXECUTE FUNCTION public.account_test_capabilities_ephemeral();
    """
    )

    op.execute(
        """CREATE TABLE public.account_test_policy_originals (
      signature text PRIMARY KEY, definition text NOT NULL);
      ALTER TABLE public.account_test_policy_originals ENABLE ROW LEVEL SECURITY;
      ALTER TABLE public.account_test_policy_originals FORCE ROW LEVEL SECURITY;
      REVOKE ALL ON public.account_test_policy_originals FROM PUBLIC;
    """
    )
    connection = op.get_bind()
    for signature, before, after in (
        (
            "public.account_lock_financial_erasure(text,timestamptz,uuid)",
            "AND NOT a.financial_hold",
            "AND (NOT a.financial_hold OR public.account_lock_test_data_policy())",
        ),
        (
            "public.account_lock_financial_gc_parties(text,timestamptz,uuid,text[],bigint)",
            "(financial_hold OR financial_deleted_at IS NOT NULL)",
            "((financial_hold AND NOT public.account_lock_test_data_policy()) OR financial_deleted_at IS NOT NULL)",
        ),
    ):
        definition = connection.scalar(
            sa.text("SELECT pg_get_functiondef(CAST(:s AS regprocedure))"),
            {"s": signature},
        )
        if definition.count(before) != 1:
            raise RuntimeError("Expected original financial preservation guard")
        connection.execute(
            sa.text("INSERT INTO public.account_test_policy_originals VALUES(:s,:d)"),
            {"s": signature, "d": definition},
        )
        connection.exec_driver_sql(
            definition.replace(before, after), execution_options={"no_parameters": True}
        )

    from controlplane_db.test_retention import financial_tables

    sql = Path(__file__).with_name("test_retention_authority.sql").read_text()
    names = (
        "ARRAY["
        + ",".join("'" + name + "'" for name in financial_tables())
        + "]::text[]"
    )
    connection.exec_driver_sql(
        sql.replace("__SOURCE_TABLES__", names),
        execution_options={"no_parameters": True},
    )
    for signature in _AUTHORITY_FUNCTIONS:
        connection.exec_driver_sql(
            "REVOKE ALL ON FUNCTION public." + signature + " FROM PUBLIC"
        )


def downgrade():
    op.execute("SELECT public.account_lock_financial_inventory_schema()")
    op.execute(
        """DO $$ BEGIN IF EXISTS(SELECT 1 FROM public.account_test_data_policy WHERE enabled) THEN
      RAISE EXCEPTION 'Disable TEST policy before removing its support'; END IF; END $$"""
    )
    op.execute(
        """DO $$ BEGIN IF to_regclass('public.account_test_delete_guard_originals') IS NOT NULL THEN
      RAISE EXCEPTION 'Restore native owner delete guards before removing TEST support';
      END IF; END $$"""
    )
    connection = op.get_bind()
    for definition in connection.scalars(
        sa.text(
            "SELECT definition FROM public.account_test_policy_originals ORDER BY signature"
        )
    ):
        connection.exec_driver_sql(
            definition, execution_options={"no_parameters": True}
        )
    for signature in reversed(_AUTHORITY_FUNCTIONS):
        connection.exec_driver_sql("DROP FUNCTION public." + signature)
    op.execute("DROP TABLE public.account_test_policy_originals")
    op.execute("DROP TABLE public.account_test_delete_capabilities")
    op.execute("DROP FUNCTION public.account_test_capabilities_ephemeral()")
    op.execute("DROP FUNCTION public.account_test_row_delete_allowed(oid,jsonb)")
    op.execute("DROP FUNCTION public.account_lock_test_data_policy()")
    op.execute("DROP FUNCTION public.account_test_data_enabled()")
    op.execute("DROP TABLE public.account_test_data_policy")
