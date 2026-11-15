"""Explicit additive provider-location schema; never guesses legacy locations."""
import hashlib
import importlib.util
from pathlib import Path
from psycopg import sql

ROOT=Path(__file__).parent
spec=importlib.util.spec_from_file_location('storage_location_group_base',ROOT/'group_migrate.py')
group=importlib.util.module_from_spec(spec);spec.loader.exec_module(group)
DDL=ROOT/'005_group_locations.sql'


def apply(connection,schema,runtime_role):
    schema,runtime_role=group.base.name(schema),group.base.name(runtime_role)
    raw=DDL.read_bytes();digest=hashlib.sha256(raw).hexdigest()
    with connection.transaction():
        group.apply(connection,schema,runtime_role)
        with connection.cursor() as cursor:
            cursor.execute(sql.SQL('SET LOCAL search_path TO {},pg_catalog,pg_temp').format(sql.Identifier(schema)))
            cursor.execute('SELECT to_regclass(%s)',(schema+'.storage_group_location_version',))
            if cursor.fetchone()[0] is not None:
                cursor.execute('SELECT version,sha256,runtime_role FROM storage_group_location_version')
                if cursor.fetchall()!=[(5,digest,runtime_role)]:raise ValueError('Group location schema differs')
                cursor.execute('SELECT to_regclass(%s)',(schema+'.storage_group_locations',))
                if cursor.fetchone()[0] is None:raise ValueError('Group location schema incomplete')
                return False
            cursor.execute('SELECT to_regclass(%s)',(schema+'.storage_group_locations',))
            if cursor.fetchone()[0] is not None:raise ValueError('Group location schema incomplete')
            cursor.execute(raw.decode())
            cursor.execute('CREATE TABLE storage_group_location_version (version integer PRIMARY KEY CHECK(version=5),sha256 text NOT NULL,runtime_role text NOT NULL)')
            cursor.execute('INSERT INTO storage_group_location_version VALUES (5,%s,%s)',(digest,runtime_role))
            cursor.execute(sql.SQL('GRANT SELECT,INSERT ON storage_group_locations TO {}').format(sql.Identifier(runtime_role)))
            cursor.execute(sql.SQL('GRANT EXECUTE ON FUNCTION storage_group_location_transition() TO {}').format(sql.Identifier(runtime_role)))
    return True
