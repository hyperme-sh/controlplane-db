"""Private worker producer coverage check through the owning SQL boundary."""

from alembic import op

revision = "platform_0076_worker_check"
down_revision = "platform_0075_creator_refs"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("SELECT public.account_lock_financial_inventory_schema()")
    op.execute("""CREATE FUNCTION public.account_check_closure_worker_installation()
    RETURNS void LANGUAGE plpgsql SECURITY DEFINER
    SET search_path=pg_catalog SET row_security=off AS $$ BEGIN
      LOCK TABLE public.account_financial_fence_versions IN SHARE MODE;
      IF (SELECT count(*) FROM public.account_financial_fence_versions
          WHERE owner IN ('billing','payment','hypermesh') AND protocol=1)<>3 THEN
        RAISE EXCEPTION 'Native closure owner installation incomplete' USING ERRCODE='42501';
      END IF;
    END $$""")
    op.execute("REVOKE ALL ON FUNCTION public.account_check_closure_worker_installation() FROM PUBLIC")


def downgrade():
    op.execute("SELECT public.account_lock_financial_inventory_schema()")
    op.execute("SELECT public.account_assert_guards_removable()")
    op.execute("DROP FUNCTION public.account_check_closure_worker_installation()")
