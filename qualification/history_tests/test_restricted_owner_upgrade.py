"""Managed PostgreSQL migrations must work without a cluster-wide RLS bypass."""

import os
import secrets
import uuid

import pytest
from alembic import command
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError

from controlplane_db import migrations


@pytest.fixture
def restricted_database():
    value = os.environ.get("TEST_DATABASE_URL")
    if not value:
        pytest.skip("requires disposable PostgreSQL")
    base = make_url(value).set(drivername="postgresql+psycopg")
    admin = create_engine(base, isolation_level="AUTOCOMMIT")
    name = "restricted_" + uuid.uuid4().hex
    password = secrets.token_hex(24)
    owner_url = base.set(username=name, password=password, database=name)
    owner = create_engine(owner_url)
    created_actor = False
    try:
        with admin.connect() as conn:
            conn.exec_driver_sql(
                f"CREATE ROLE {name} LOGIN NOSUPERUSER NOBYPASSRLS PASSWORD '{password}'"
            )
            if not conn.scalar(
                text(
                    "SELECT EXISTS (SELECT FROM pg_roles WHERE rolname='payment_mismatch_actor')"
                )
            ):
                conn.exec_driver_sql("CREATE ROLE payment_mismatch_actor NOLOGIN")
                created_actor = True
            conn.exec_driver_sql(f"GRANT payment_mismatch_actor TO {name}")
            conn.exec_driver_sql(f"CREATE DATABASE {name} OWNER {name}")
        observer = create_engine(base.set(database=name))
        try:
            yield owner_url.render_as_string(hide_password=False), owner, observer
        finally:
            observer.dispose()
    finally:
        owner.dispose()
        with admin.connect() as conn:
            conn.exec_driver_sql(f"DROP DATABASE IF EXISTS {name} WITH (FORCE)")
            conn.exec_driver_sql(f"DROP ROLE IF EXISTS {name}")
            if created_actor:
                conn.exec_driver_sql("DROP ROLE payment_mismatch_actor")
        admin.dispose()


def test_restricted_owner_upgrades_and_replays_platform_and_payment(
    restricted_database,
):
    url, owner, observer = restricted_database
    chains = ["platform", "payment_service"]
    for _ in range(2):
        migrations.upgrade(url, chains)
    heads = migrations.current_heads(url)
    with owner.connect() as conn:
        for chain in chains:
            assert heads[chain] == migrations.chain_heads()[chain]
        for table in (
            "account_test_policy_originals",
            "account_test_delete_guard_originals",
        ):
            assert conn.scalar(
                text(
                    "SELECT relrowsecurity AND relforcerowsecurity FROM pg_class WHERE oid=to_regclass(:name)"
                ),
                {"name": "public." + table},
            )
            assert conn.scalar(text(f"SELECT count(*) FROM public.{table}")) == 0
            assert not conn.scalar(
                text(
                    "SELECT EXISTS (SELECT FROM pg_policies WHERE schemaname='public' AND tablename=:name)"
                ),
                {"name": table},
            )
    with observer.connect() as conn:
        for table in (
            "account_test_policy_originals",
            "account_test_delete_guard_originals",
        ):
            assert conn.scalar(text(f"SELECT count(*) FROM public.{table}")) > 0


def test_nonempty_custody_refuses_retirement_and_restores_forced_rls(
    restricted_database,
):
    url, owner, observer = restricted_database
    migrations.upgrade(url, ["platform"])
    with owner.begin() as conn:
        command.upgrade(
            migrations._config(migrations._ROOT, "payment_service", conn),
            "payment_service_0063_tax",
        )
    with observer.begin() as conn:
        tenant = uuid.uuid4()
        conn.execute(
            text("INSERT INTO tenants(id,name,is_active) VALUES (:id,'retained',true)"),
            {"id": tenant},
        )
        conn.execute(
            text(
                """INSERT INTO usdc_deposit_addresses(user_id,tenant_id,chain_id,address)
                             VALUES (:id,:tenant,84532,'0x1111111111111111111111111111111111111111')"""
            ),
            {"id": uuid.uuid4(), "tenant": tenant},
        )
    with pytest.raises(DBAPIError, match="Cannot retire nonempty custody"):
        migrations.upgrade(url, ["payment_service"])
    with observer.connect() as conn:
        assert conn.scalar(text("SELECT count(*) FROM usdc_deposit_addresses")) == 1
        assert conn.scalar(
            text(
                "SELECT relforcerowsecurity FROM pg_class WHERE oid='public.usdc_deposit_addresses'::regclass"
            )
        )
