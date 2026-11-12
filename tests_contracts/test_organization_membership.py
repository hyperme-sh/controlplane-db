"""Offline directory metadata contracts; PostgreSQL checks run in CI."""
from sqlalchemy import CheckConstraint, ForeignKeyConstraint, UniqueConstraint
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable
from controlplane_db.models import OrganizationUserMembership, User


def test_membership_scopes_both_references_to_the_same_tenant():
    table = OrganizationUserMembership.__table__
    links = {c.name: ([e.parent.name for e in c.elements], [e.target_fullname for e in c.elements], c.ondelete)
             for c in table.constraints if isinstance(c, ForeignKeyConstraint)}
    assert links == {
        'fk_org_user_membership_org': (['organization_id', 'tenant_id'], ['organizations.id', 'organizations.tenant_id'], 'CASCADE'),
        'fk_org_user_membership_user': (['user_id', 'tenant_id'], ['users.id', 'users.tenant_id'], 'CASCADE'),
    }
    for column in ('tenant_id', 'organization_id', 'user_id', 'role'):
        assert not table.c[column].nullable


def test_roles_are_separate_unique_rows_without_default_privilege():
    table = OrganizationUserMembership.__table__
    constraints = [tuple(c.columns.keys()) for c in table.constraints if isinstance(c, UniqueConstraint)]
    assert constraints == [('tenant_id', 'organization_id', 'user_id', 'role')]
    checks = [str(c.sqltext) for c in table.constraints if isinstance(c, CheckConstraint)]
    assert checks == ["role IN ('member', 'owner', 'admin')"]
    assert table.c.role.default is None and table.c.role.server_default is None
    assert 'platform' not in str(CreateTable(table).compile(dialect=postgresql.dialect()))


def test_existing_user_identity_and_tenant_are_referenceable_together():
    pairs = [tuple(c.columns.keys()) for c in User.__table__.constraints if isinstance(c, UniqueConstraint)]
    assert ('id', 'tenant_id') in pairs
