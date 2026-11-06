"""Provider-mode observations do not restart production financial retention."""
from alembic import op
import sqlalchemy as sa

revision = "platform_0084_stripe_clock"
down_revision = "platform_0083_stripe_scope"
branch_labels = None
depends_on = None
_SIGNATURE = "public.account_billing_financial_clock()"
_BACKUP = "platform_0084_stripe_clock:" + _SIGNATURE


def upgrade():
    op.execute("SELECT public.account_lock_financial_inventory_schema()")
    connection=op.get_bind()
    definition=connection.scalar(sa.text("SELECT pg_get_functiondef(CAST(:s AS regprocedure))"),{'s':_SIGNATURE})
    before="ARRAY['updated_at','financial_activity_at','financial_retain_until','metadata']"
    after="ARRAY['updated_at','financial_activity_at','financial_retain_until','metadata','stripe_livemode']"
    if definition.count(before)!=2:
        raise RuntimeError("Expected original billing financial clock")
    connection.execute(sa.text("INSERT INTO public.account_test_policy_originals VALUES(:s,:d)"),{'s':_BACKUP,'d':definition})
    connection.exec_driver_sql(definition.replace(before,after),execution_options={'no_parameters':True})


def downgrade():
    op.execute("SELECT public.account_lock_financial_inventory_schema()")
    connection=op.get_bind()
    definition=connection.scalar(sa.text("SELECT definition FROM public.account_test_policy_originals WHERE signature=:s"),{'s':_BACKUP})
    if not definition:raise RuntimeError("Original billing financial clock required")
    connection.exec_driver_sql(definition,execution_options={'no_parameters':True})
    connection.execute(sa.text("DELETE FROM public.account_test_policy_originals WHERE signature=:s"),{'s':_BACKUP})
