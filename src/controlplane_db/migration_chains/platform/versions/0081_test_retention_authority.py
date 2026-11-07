"""Upgrade existing TEST coordinators to database-owned erasure authority."""
from pathlib import Path
from alembic import op

revision = "platform_0081_test_authority"
down_revision = "platform_0080_test_retention"
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
    # Lock out both policy changes and old coordinator capability writes while
    # replacing authority. No transaction-bound capabilities may be carried in.
    op.execute("LOCK TABLE public.account_test_data_policy, public.account_test_delete_capabilities IN ACCESS EXCLUSIVE MODE")
    op.execute("ALTER TABLE public.account_test_delete_capabilities NO FORCE ROW LEVEL SECURITY")
    op.execute("""DO $$ BEGIN
      IF EXISTS(SELECT 1 FROM public.account_test_delete_capabilities) THEN
        RAISE EXCEPTION 'Finish TEST capability transactions before upgrading authority'; END IF;
    END $$""")
    op.execute("ALTER TABLE public.account_test_delete_capabilities FORCE ROW LEVEL SECURITY")
    op.execute("""ALTER TABLE public.account_test_delete_capabilities
      ADD COLUMN source_subject text, ADD COLUMN source_closed_at timestamptz,
      ADD COLUMN row_tid text""")
    # Old installed worker plans granted table DML. Revoke every non-owner
    # table/column capability grant, including grants inherited by login roles.
    op.execute("""DO $$ DECLARE item record; BEGIN
      FOR item IN SELECT DISTINCT acl.grantee,c.relowner FROM pg_catalog.pg_class c,
        LATERAL aclexplode(coalesce(c.relacl,acldefault('r',c.relowner))) acl
        WHERE c.oid='public.account_test_delete_capabilities'::regclass AND acl.grantee<>c.relowner
      LOOP
        EXECUTE format('REVOKE ALL ON public.account_test_delete_capabilities FROM %s',
          CASE WHEN item.grantee=0 THEN 'PUBLIC' ELSE quote_ident(pg_get_userbyid(item.grantee)) END);
      END LOOP;
      FOR item IN SELECT DISTINCT a.attname,acl.grantee FROM pg_catalog.pg_attribute a
        JOIN pg_catalog.pg_class c ON c.oid=a.attrelid,
        LATERAL aclexplode(a.attacl) acl
        WHERE a.attrelid='public.account_test_delete_capabilities'::regclass AND acl.grantee<>c.relowner
      LOOP
        EXECUTE format('REVOKE ALL (%I) ON public.account_test_delete_capabilities FROM %s',item.attname,
          CASE WHEN item.grantee=0 THEN 'PUBLIC' ELSE quote_ident(pg_get_userbyid(item.grantee)) END);
      END LOOP;
    END $$""")
    connection = op.get_bind()
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
    op.execute("LOCK TABLE public.account_test_data_policy, public.account_test_delete_capabilities IN ACCESS EXCLUSIVE MODE")
    op.execute("ALTER TABLE public.account_test_delete_capabilities NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE public.account_test_data_policy NO FORCE ROW LEVEL SECURITY")
    op.execute("""DO $$ BEGIN
      IF EXISTS(SELECT 1 FROM public.account_test_data_policy WHERE enabled) THEN
        RAISE EXCEPTION 'Disable TEST policy before removing erasure authority'; END IF;
      IF EXISTS(SELECT 1 FROM public.account_test_delete_capabilities) THEN
        RAISE EXCEPTION 'Finish TEST capabilities before removing authority'; END IF;
    END $$""")
    op.execute("ALTER TABLE public.account_test_data_policy FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE public.account_test_delete_capabilities FORCE ROW LEVEL SECURITY")
    for signature in reversed(_AUTHORITY_FUNCTIONS):
        op.execute("DROP FUNCTION public." + signature)
    op.execute("""ALTER TABLE public.account_test_delete_capabilities
      DROP COLUMN row_tid, DROP COLUMN source_closed_at, DROP COLUMN source_subject""")
    # Never restore compromised coordinator grants on downgrade.
