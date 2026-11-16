"""Explicit additive stream reservation schema preparation; no runtime bootstrap."""
import argparse
import hashlib
import importlib.util
from pathlib import Path
import psycopg
from psycopg import sql

ROOT=Path(__file__).parent
spec=importlib.util.spec_from_file_location('storage_base_migrate',ROOT/'migrate.py')
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
DDL=ROOT/'006_stream_sessions.sql'


def apply(connection,schema,runtime_role):
    schema,runtime_role=base.name(schema),base.name(runtime_role)
    raw=DDL.read_bytes();digest=hashlib.sha256(raw).hexdigest()
    with connection.transaction():
        # Validates restricted roles, ownership and the unchanged baseline;
        # its transaction advisory lock remains held until this outer commit.
        base.apply(connection,schema,runtime_role)
        with connection.cursor() as cursor:
            cursor.execute(sql.SQL('SET LOCAL search_path TO {},pg_catalog,pg_temp').format(sql.Identifier(schema)))
            cursor.execute('SELECT to_regclass(%s)',(schema+'.stream_schema_version',))
            if cursor.fetchone()[0] is not None:
                cursor.execute('SELECT version,sha256,runtime_role FROM stream_schema_version')
                if cursor.fetchall()!=[(6,digest,runtime_role)]:
                    raise ValueError('Stream schema version differs')
                for name in ('stream_policies','stream_sessions'):
                    cursor.execute('SELECT to_regclass(%s)',(schema+'.'+name,))
                    if cursor.fetchone()[0] is None:raise ValueError('Stream schema incomplete')
                return False
            for name in ('stream_policies','stream_sessions'):
                cursor.execute('SELECT to_regclass(%s)',(schema+'.'+name,))
                if cursor.fetchone()[0] is not None:raise ValueError('Stream schema incomplete')
            cursor.execute(raw.decode())
            cursor.execute('CREATE TABLE stream_schema_version (version integer PRIMARY KEY CHECK(version=6),sha256 text NOT NULL,runtime_role text NOT NULL)')
            cursor.execute('INSERT INTO stream_schema_version VALUES (6,%s,%s)',(digest,runtime_role))
            cursor.execute(sql.SQL('GRANT SELECT ON stream_policies TO {}').format(sql.Identifier(runtime_role)))
            cursor.execute(sql.SQL('GRANT SELECT,INSERT,UPDATE ON stream_sessions TO {}').format(sql.Identifier(runtime_role)))
            cursor.execute(sql.SQL('GRANT EXECUTE ON FUNCTION stream_session_transition() TO {}').format(sql.Identifier(runtime_role)))
    return True


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database-url-file',type=Path,required=True)
    parser.add_argument('--schema',required=True)
    parser.add_argument('--runtime-role',required=True)
    args=parser.parse_args()
    try:
        with psycopg.connect(args.database_url_file.read_text().strip()) as connection:
            apply(connection,args.schema,args.runtime_role)
    except Exception:
        raise SystemExit('Stream schema application failed; no private details are reported') from None
