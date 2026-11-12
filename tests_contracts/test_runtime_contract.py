"""Runtime metadata contracts, without a database server."""
from controlplane_db.base import Base
import controlplane_db.models
from controlplane_db.session import normalize_database_url


def test_generic_budget_model_is_tenant_bound():
    table = Base.metadata.tables['crypto_agent_budgets']
    assert 'tenant_id' in table.columns
    assert not table.columns['tenant_id'].nullable


def test_postgres_driver_normalization_preserves_connection_scope():
    value = normalize_database_url('postgresql://caller:password@db.example:5432/tenant_db')
    assert 'caller:password@db.example:5432/tenant_db' in value
    assert value.startswith('postgresql')
