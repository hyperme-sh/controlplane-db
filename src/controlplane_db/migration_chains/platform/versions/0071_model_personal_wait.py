"""Expose trusted personal-erasure authorization without waiving model safety."""

from alembic import op

revision = "platform_0071_model_wait"
down_revision = "platform_0070_renter_scope"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("SELECT public.account_lock_financial_inventory_schema()")
    op.execute("""CREATE FUNCTION public.account_personal_model_erasure_allowed(
      p_subject text,p_tenant uuid,p_model_closed_at timestamptz)
    RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER
    SET search_path=pg_catalog SET row_security=off AS $$
    BEGIN
      -- This predicate can run during a lease update. Never wait on a schema
      -- change while already holding owner source rows.
      LOCK TABLE public.account_financial_fence_versions IN SHARE MODE NOWAIT;
      IF p_tenant IS NULL OR p_model_closed_at IS NULL OR p_model_closed_at>transaction_timestamp()
        OR NOT EXISTS(SELECT 1 FROM public.account_lifecycles
          WHERE subject=p_subject AND closed_at>=p_model_closed_at) THEN RETURN false; END IF;
      PERFORM public.account_require_personal_erasure(p_subject,p_tenant);
      RETURN true;
    EXCEPTION
      WHEN insufficient_privilege THEN RETURN false;
      WHEN lock_not_available THEN
        RAISE EXCEPTION 'Personal model authorization must retry' USING ERRCODE='40001';
    END $$""")
    op.execute("REVOKE ALL ON FUNCTION public.account_personal_model_erasure_allowed(text,uuid,timestamptz) FROM PUBLIC")


def downgrade():
    op.execute("SELECT public.account_lock_financial_inventory_schema()")
    op.execute("SELECT public.account_assert_guards_removable()")
    op.execute("""DO $$ BEGIN
      IF to_regprocedure('public.hypermesh_personal_model_wait(text,uuid,timestamptz)') IS NOT NULL THEN
        RAISE EXCEPTION 'Remove dependent personal model guard before its authorization';
      END IF;
    END $$""")
    op.execute("DROP FUNCTION public.account_personal_model_erasure_allowed(text,uuid,timestamptz)")
