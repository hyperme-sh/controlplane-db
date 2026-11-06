"""Require all original native inventories before personal owner erasure."""

from alembic import op

revision = "platform_0068_inventory_gate"
down_revision = "platform_0067_fin_inventory"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("SELECT public.account_lock_financial_inventory_schema()")
    op.execute("""CREATE FUNCTION public.account_require_financial_inventory(
  p_subject text,p_closed_at timestamptz)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog SET row_security=off AS $$
BEGIN
  PERFORM public.account_lock_financial_inventory(p_subject,p_closed_at,NULL);
  IF NOT EXISTS(SELECT 1 FROM public.account_lifecycles a WHERE a.subject=p_subject
    AND a.effects->'financial_inventory' @> '{"billing": 1,"payment": 1,"hypermesh": 1}'::jsonb)
    OR EXISTS(
      SELECT 1 FROM public.account_lifecycles a,
        LATERAL jsonb_array_elements_text(a.effects->'scope_tenants') original(tenant)
      WHERE a.subject=p_subject AND NOT EXISTS(
        SELECT 1 FROM public.account_lifecycle_scopes s
        WHERE s.subject=p_subject AND s.tenant_id=original.tenant::uuid
          AND s.effects @> '{"profile_inventory_complete": true}'::jsonb
          AND s.effects->'financial_inventory' @> '{"billing": 1,"payment": 1,"hypermesh": 1}'::jsonb
      )
    ) THEN
    RAISE EXCEPTION 'Native financial inventory is incomplete' USING ERRCODE='42501';
  END IF;
END $$""")
    op.execute(
        "REVOKE ALL ON FUNCTION public.account_require_financial_inventory(text,timestamptz) FROM PUBLIC"
    )


def downgrade():
    op.execute("SELECT public.account_lock_financial_inventory_schema()")
    op.execute("SELECT public.account_assert_guards_removable()")
    op.execute(
        "DROP FUNCTION public.account_require_financial_inventory(text,timestamptz)"
    )
