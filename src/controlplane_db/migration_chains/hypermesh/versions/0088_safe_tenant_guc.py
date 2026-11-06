"""Make empty tenant scope safe under non-superuser PostgreSQL RLS.

PostgreSQL may evaluate a UUID cast before the surrounding boolean guard.
Keep the existing NULL/global and tenant predicates; make only the cast total.
"""
from alembic import op
import sqlalchemy as sa

revision = 'hypermesh_0088_safe_tenant_guc'
down_revision = 'hypermesh_0087_closure_lab_merge'
branch_labels = None
depends_on = None

UNSAFE = "(current_setting('app.current_tenant_id'::text, true))::uuid"
SAFE = "NULLIF(current_setting('app.current_tenant_id'::text, true), '')::uuid"


def upgrade():
    connection = op.get_bind()
    quote = connection.dialect.identifier_preparer.quote
    rows = connection.execute(sa.text("""SELECT tablename, policyname, qual, with_check
        FROM pg_policies WHERE schemaname = 'public'
        AND tablename LIKE 'hypermesh\\_%' ESCAPE '\\'""")).mappings().all()
    for row in rows:
        clauses = []
        for column, keyword in [('qual', 'USING'), ('with_check', 'WITH CHECK')]:
            expression = row[column]
            if expression and UNSAFE in expression:
                clauses.append(f'{keyword} ({expression.replace(UNSAFE, SAFE)})')
        if clauses:
            connection.execute(sa.text(f'ALTER POLICY {quote(row["policyname"])} ON public.{quote(row["tablename"])} ' + ' '.join(clauses)))


def downgrade():
    raise RuntimeError('Refusing to restore unsafe empty-tenant UUID casts')
