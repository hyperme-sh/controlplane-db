"""Private personal-access actor bridges for the payment owner."""

from alembic import op

revision = "platform_0073_access_actor"
down_revision = "platform_0072_gc_parties"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("SELECT public.account_lock_financial_inventory_schema()")
    op.execute("""CREATE FUNCTION public.account_lock_personal_access_actor(p_subject text,p_tenant uuid)
    RETURNS void LANGUAGE plpgsql SECURITY DEFINER
    SET search_path=pg_catalog SET row_security=off AS $$ BEGIN
      BEGIN
        LOCK TABLE public.account_financial_fence_versions IN SHARE MODE NOWAIT;
        IF NOT pg_try_advisory_xact_lock(hashtextextended('identity-retirement:'||p_subject,0)) THEN
          RAISE EXCEPTION 'Access actor cleanup must retry' USING ERRCODE='40001';
        END IF;
        PERFORM 1 FROM public.account_lifecycles WHERE subject=p_subject FOR UPDATE NOWAIT;
      EXCEPTION WHEN lock_not_available THEN
        RAISE EXCEPTION 'Access actor cleanup must retry' USING ERRCODE='40001';
      END;
      PERFORM public.account_require_personal_erasure(p_subject,p_tenant);
    END $$""")
    op.execute("REVOKE ALL ON FUNCTION public.account_lock_personal_access_actor(text,uuid) FROM PUBLIC")
    op.execute("""CREATE FUNCTION public.account_unbind_personal_access_actor(p_subject text,p_tenant uuid,p_grant uuid)
    RETURNS void LANGUAGE plpgsql SECURITY DEFINER
    SET search_path=pg_catalog SET row_security=off AS $$ BEGIN
      PERFORM public.account_lock_personal_access_actor(p_subject,p_tenant);
      DELETE FROM public.account_financial_source_bindings
        WHERE subject=p_subject AND tenant_id=p_tenant AND owner='payment'
          AND kind IN ('connect_access_grants','connect_access_results') AND resource=p_grant::text;
    END $$""")
    op.execute("REVOKE ALL ON FUNCTION public.account_unbind_personal_access_actor(text,uuid,uuid) FROM PUBLIC")


def downgrade():
    op.execute("SELECT public.account_lock_financial_inventory_schema()")
    op.execute("SELECT public.account_assert_guards_removable()")
    op.execute("""DO $$ BEGIN
      IF to_regprocedure('public.payment_access_actor_redaction()') IS NOT NULL THEN
        RAISE EXCEPTION 'Payment actor bridge is still installed';
      END IF;
    END $$""")
    op.execute("DROP FUNCTION public.account_unbind_personal_access_actor(text,uuid,uuid)")
    op.execute("DROP FUNCTION public.account_lock_personal_access_actor(text,uuid)")
