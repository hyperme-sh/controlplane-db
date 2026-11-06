"""Reconcile reviewed share-lookup hardening and account-closure histories.

Neither parent revision nor any historical registry/baseline is rewritten.
The two branches modify independent objects; their merge introduces no DDL.
"""
revision = 'platform_0079_closure_merge'
down_revision = ('platform_0078_fin_empty', 'platform_0057_share_lookup')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
