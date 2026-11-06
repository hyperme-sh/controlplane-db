"""Migration fixture driver transferred from controlplane-tests 943df6f."""
from __future__ import annotations

import os
from pathlib import Path

from alembic import command
from alembic.config import Config


def alembic_ini_path() -> Path:
    """Use this database owner's frozen historical migration resources.

    Shared wheels omit the file. Qualification reads it from the checkout when
    the installed package does not carry it.
    """
    from importlib.resources import files
    packaged = Path(str(files("controlplane_db") / "alembic.ini"))
    if packaged.is_file():
        return packaged
    checkout = Path(__file__).resolve().parents[2] / "src" / "controlplane_db" / "alembic.ini"
    if checkout.is_file():
        return checkout
    raise FileNotFoundError(packaged)


def normalize_sync_sqlalchemy_url(url: str) -> str:
    """Force psycopg3 driver (postgresql+psycopg). Testcontainers may emit postgresql+psycopg2://."""
    u = url.strip()
    if "+asyncpg" in u:
        return u.replace("+asyncpg", "+psycopg", 1)
    if u.startswith("postgresql+psycopg2://"):
        return "postgresql+psycopg://" + u.removeprefix("postgresql+psycopg2://")
    if u.startswith("postgresql://"):
        return "postgresql+psycopg://" + u.removeprefix("postgresql://")
    if u.startswith("postgres://"):
        return "postgresql+psycopg://" + u.removeprefix("postgres://")
    return u


def run_alembic_upgrade(sync_url: str) -> None:
    """Run Alembic migrations against a sync SQLAlchemy URL (psycopg)."""
    _alembic(sync_url, "upgrade", "head")


def async_db_url(sync_psycopg_url: str) -> str:
    return sync_psycopg_url.replace("+psycopg", "+asyncpg", 1)


def database_url(server_url: str, name: str) -> str:
    """Return ``server_url`` pointed at database ``name`` (same host, port and credentials)."""
    from sqlalchemy.engine import make_url

    url = make_url(normalize_sync_sqlalchemy_url(server_url)).set(database=name)
    return url.render_as_string(hide_password=False)


def _alembic(sync_url: str, action: str, revision: str) -> None:
    """Run one Alembic command against ``sync_url`` and restore ``DATABASE_URL`` afterwards."""
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = normalize_sync_sqlalchemy_url(sync_url)
    try:
        getattr(command, action)(Config(str(alembic_ini_path())), revision)
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous


class MigrationTemplates:
    """Copy-on-demand databases for migration tests that share one PostgreSQL server.

    Starting a container and replaying the whole Alembic chain for every test
    dominated the core suite. This keeps one server per pytest process (one per
    xdist worker), migrates each requested revision into a template database
    once, and hands every test its own ``CREATE DATABASE ... TEMPLATE`` copy.

    A template at revision R is built by copying the nearest lower template and
    upgrading it, which runs the same revision steps as an upgrade from empty.
    The server must not gain the optional ``controlplane``/``controlplane_app``
    roles: several migrations grant to them only when they exist, and the tests
    using this helper expect the role-free behavior a fresh container had.
    """

    def __init__(self, server_url: str, *, prefix: str = "mt") -> None:
        from sqlalchemy import create_engine

        self._server_url = normalize_sync_sqlalchemy_url(server_url)
        self._admin = create_engine(self._server_url, isolation_level="AUTOCOMMIT")
        self._prefix = prefix
        self._templates: dict[str, str] = {}
        self._counter = 0
        self._order: dict[str, int] | None = None

    # -- naming -----------------------------------------------------------------
    def _name(self, kind: str, key: str = "") -> str:
        import re

        self._counter += 1
        slug = re.sub(r"[^a-z0-9]+", "_", key.lower()).strip("_")
        return f"{self._prefix}_{kind}_{self._counter}_{slug}"[:63]

    def url(self, name: str) -> str:
        return database_url(self._server_url, name)

    def _create(self, name: str, template: str = "template0") -> None:
        with self._admin.connect() as cx:
            cx.exec_driver_sql(f'CREATE DATABASE "{name}" TEMPLATE "{template}"')

    def drop(self, name: str) -> None:
        with self._admin.connect() as cx:
            cx.exec_driver_sql(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')

    # -- revisions --------------------------------------------------------------
    def _revision_index(self, revision: str) -> int:
        from alembic.script import ScriptDirectory

        if self._order is None:
            script = ScriptDirectory.from_config(Config(str(alembic_ini_path())))
            heads = script.get_heads()
            if len(heads) != 1:
                raise RuntimeError(f"migration templates need one Alembic head, found {heads}")
            chain = [rev.revision for rev in script.walk_revisions()]  # head first
            self._order = {rev: len(chain) - i for i, rev in enumerate(chain)}
            self._order["head"] = self._order[heads[0]]
        return self._order[revision]

    def template_at(self, revision: str) -> str:
        """Name of a template database upgraded from empty to ``revision`` (built once)."""
        if revision == "head":
            self._revision_index("head")
            assert self._order is not None
            revision = next(rev for rev, i in self._order.items() if rev != "head" and i == self._order["head"])
        key = f"rev:{revision}"
        if key in self._templates:
            return self._templates[key]
        target = self._revision_index(revision)
        base, base_index = "template0", 0
        for built_key, name in self._templates.items():
            if not built_key.startswith("rev:"):
                continue
            index = self._revision_index(built_key.removeprefix("rev:"))
            if base_index < index <= target:
                base, base_index = name, index
        name = self._name("tpl", revision)
        self._create(name, base)
        if base_index != target:
            _alembic(self.url(name), "upgrade", revision)
        self._templates[key] = name
        return name

    def derived_template(self, key: str, base_revision: str, build) -> str:
        """Template made by copying ``template_at(base_revision)`` and running ``build(url)`` once."""
        cache_key = f"derived:{key}"
        if cache_key in self._templates:
            return self._templates[cache_key]
        name = self._name("tpl", key)
        self._create(name, self.template_at(base_revision))
        build(self.url(name))
        self._templates[cache_key] = name
        return name

    def database(self, template: str = "template0", *, label: str = "db") -> tuple[str, str]:
        """Create a fresh database copied from ``template``; return ``(name, sync_url)``."""
        name = self._name("db", label)
        self._create(name, template)
        return name, self.url(name)

    def dispose(self) -> None:
        self._admin.dispose()


def alembic_upgrade(sync_url: str, revision: str = "head") -> None:
    """Upgrade ``sync_url`` to ``revision`` without leaking ``DATABASE_URL``."""
    _alembic(sync_url, "upgrade", revision)


def alembic_downgrade(sync_url: str, revision: str) -> None:
    """Downgrade ``sync_url`` to ``revision`` without leaking ``DATABASE_URL``."""
    _alembic(sync_url, "downgrade", revision)


def _pg_bin(name: str) -> str | None:
    import shutil
    found = shutil.which(name)
    if found:
        return found
    matches = sorted(Path("/usr/lib/postgresql").glob(f"*/bin/{name}"))
    return str(matches[-1]) if matches else None


def _docker_available() -> bool:
    import shutil
    import subprocess
    if shutil.which("docker") is None:
        return False
    try:
        completed = subprocess.run(
            ["docker", "info"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return completed.returncode == 0


def isolated_postgres():
    """Yield a sync URL for one disposable PostgreSQL database.

    Docker keeps the original pinned testcontainer. Otherwise a private
    cluster (or ``TEST_DATABASE_URL``) isolates roles from the shared package
    server. Created databases and roles are removed with that server.
    """
    from contextlib import contextmanager
    import socket
    import subprocess
    import tempfile
    import time
    import uuid

    from sqlalchemy import create_engine, text
    from sqlalchemy.engine import make_url

    @contextmanager
    def _from_container():
        from testcontainers.postgres import PostgresContainer
        image = "postgres:17@sha256:3b0cda93be7c8dba2ed484d19393d93845dc3dafb88973e248ba8e6d99d784e1"
        with PostgresContainer(image, username="migration", password="local-test-only", dbname="source") as pg:
            yield normalize_sync_sqlalchemy_url(pg.get_connection_url())

    @contextmanager
    def _from_cluster():
        data_dir = tempfile.TemporaryDirectory()
        try:
            data = Path(data_dir.name) / "data"
            sock = socket.socket()
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
            sock.close()
            initdb = _pg_bin("initdb")
            pg_ctl = _pg_bin("pg_ctl")
            pg_isready = _pg_bin("pg_isready")
            subprocess.check_call(
                [initdb, "-D", str(data), "-U", "migration", "--auth-local=trust",
                 "--auth-host=trust", "--no-instructions", "--encoding=UTF8", "--locale=C"],
                stdout=subprocess.DEVNULL,
            )
            log = Path(data_dir.name) / "server.log"
            subprocess.check_call([
                pg_ctl, "-D", str(data), "-l", str(log),
                "-o", f"-p {port} -k {data_dir.name} -c listen_addresses=127.0.0.1",
                "start",
            ])
            try:
                for _ in range(50):
                    if subprocess.run(
                        [pg_isready, "-h", "127.0.0.1", "-p", str(port), "-U", "migration"],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    ).returncode == 0:
                        break
                    time.sleep(0.1)
                else:
                    raise RuntimeError(log.read_text()[-4000:])
                yield f"postgresql+psycopg://migration@127.0.0.1:{port}/postgres"
            finally:
                subprocess.call([pg_ctl, "-D", str(data), "stop", "-m", "immediate"],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        finally:
            data_dir.cleanup()

    @contextmanager
    def _from_server(raw: str):
        admin_url = make_url(normalize_sync_sqlalchemy_url(raw))
        name = "hist_" + uuid.uuid4().hex
        admin = create_engine(admin_url, isolation_level="AUTOCOMMIT")
        try:
            with admin.connect() as connection:
                before_dbs = set(connection.execute(text(
                    "SELECT datname FROM pg_database WHERE NOT datistemplate")).scalars())
                before_roles = set(connection.execute(text("SELECT rolname FROM pg_roles")).scalars())
                connection.exec_driver_sql(f'CREATE DATABASE "{name}"')
            try:
                yield admin_url.set(database=name).render_as_string(hide_password=False)
            finally:
                with admin.connect() as connection:
                    created = set(connection.execute(text(
                        "SELECT datname FROM pg_database WHERE NOT datistemplate")).scalars()) - before_dbs
                    for database in sorted(created):
                        connection.exec_driver_sql(f'DROP DATABASE IF EXISTS "{database}" WITH (FORCE)')
                    for role in sorted(set(connection.execute(text(
                            "SELECT rolname FROM pg_roles")).scalars()) - before_roles):
                        quoted = role.replace('"', '""')
                        connection.exec_driver_sql(f'DROP OWNED BY "{quoted}"')
                        connection.exec_driver_sql(f'DROP ROLE IF EXISTS "{quoted}"')
        finally:
            admin.dispose()

    @contextmanager
    def _open():
        if _docker_available():
            with _from_container() as url:
                yield url
        elif _pg_bin("initdb") and _pg_bin("pg_ctl") and _pg_bin("pg_isready"):
            with _from_cluster() as url:
                yield url
        elif os.environ.get("TEST_DATABASE_URL"):
            with _from_server(os.environ["TEST_DATABASE_URL"]) as url:
                yield url
        else:
            raise RuntimeError("historical PostgreSQL isolation needs Docker, initdb, or TEST_DATABASE_URL")

    return _open()
