"""Durable owner access lifecycle; no financial or grant journal rewrites."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "payment_service_0070_lifecycle"
down_revision = "payment_service_0069_access"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "connect_access_states",
        sa.Column(
            "lifecycle", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
    )
    # Existing native grants keep their fences; no new owner is inferred from
    # an ownerless pre-upgrade enabled state. Require explicit reactivation.
    op.execute("SET LOCAL row_security = off")
    op.execute(
        "UPDATE connect_access_states SET enabled=false, epoch=epoch+1, lifecycle=jsonb_build_object('migration_disabled', true) WHERE policy='embedded-api/v1' AND enabled"
    )
    op.create_table(
        "connect_ended_sessions",
        sa.Column("session_key", sa.String(64), primary_key=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "session_key ~ '^[0-9a-f]{64}$'", name="ck_ended_session_key"
        ),
    )
    op.create_index(
        "ix_connect_ended_sessions_expiry", "connect_ended_sessions", ["ended_at"]
    )
    op.execute("ALTER TABLE connect_ended_sessions ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE connect_ended_sessions FORCE ROW LEVEL SECURITY")
    condition = (
        "session_key = NULLIF(current_setting('app.connect_session_key', true), '')"
    )
    expired = "ended_at < CURRENT_TIMESTAMP - INTERVAL '48 hours'"
    op.execute(
        f"CREATE POLICY ended_session_select ON connect_ended_sessions FOR SELECT USING ({condition} OR {expired})"
    )
    op.execute(
        f"CREATE POLICY ended_session_insert ON connect_ended_sessions FOR INSERT WITH CHECK ({condition})"
    )
    op.execute(
        f"CREATE POLICY ended_session_cleanup ON connect_ended_sessions FOR DELETE USING ({expired})"
    )
    for operation in ("UPDATE", "TRUNCATE"):
        op.execute(
            f"CREATE TRIGGER connect_ended_sessions_{operation.lower()} BEFORE {operation} ON connect_ended_sessions FOR EACH {'STATEMENT' if operation == 'TRUNCATE' else 'ROW'} EXECUTE FUNCTION public.connect_recipient_immutable()"
        )
    op.create_index(
        "ix_connect_access_enabled_lifecycle",
        "connect_access_states",
        ["tenant_id", "host_org_id"],
        postgresql_where=sa.text("policy = 'embedded-api/v1' AND enabled IS TRUE"),
    )
    op.create_check_constraint(
        "ck_access_lifecycle",
        "connect_access_states",
        "jsonb_typeof(lifecycle) = 'object'",
    )


def downgrade():
    op.execute("SET LOCAL row_security = off")
    # Hold both tables before the history check. A concurrent lifecycle write
    # must commit or abort first, so the guard and the drop see the same rows.
    op.execute(
        "LOCK TABLE public.connect_access_states, public.connect_ended_sessions IN ACCESS EXCLUSIVE MODE"
    )
    op.execute("""DO $$ BEGIN
      IF EXISTS (SELECT 1 FROM connect_access_states WHERE lifecycle <> '{}'::jsonb) OR EXISTS (SELECT 1 FROM connect_ended_sessions) THEN
        RAISE EXCEPTION 'Cannot remove access lifecycle history' USING ERRCODE = '23514';
      END IF;
    END $$""")
    op.drop_table("connect_ended_sessions")
    op.drop_index(
        "ix_connect_access_enabled_lifecycle", table_name="connect_access_states"
    )
    op.drop_constraint("ck_access_lifecycle", "connect_access_states")
    op.drop_column("connect_access_states", "lifecycle")
