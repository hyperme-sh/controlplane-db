"""Apply only the fresh storage owner's schema; never import historical chains."""
import argparse
import hashlib
from pathlib import Path
import re

import psycopg
from psycopg import sql

DDL = Path(__file__).with_name('001_storage.sql')


def name(value):
    if not isinstance(value, str) or not re.fullmatch('[a-z][a-z0-9_]{0,62}', value):
        raise ValueError('Invalid storage role/schema name')
    return value


def apply(connection, schema, runtime_role):
    schema, runtime_role = name(schema), name(runtime_role)
    raw = DDL.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    with connection.transaction():
        with connection.cursor() as cursor:
            cursor.execute('SELECT current_user')
            owner = cursor.fetchone()[0]
            if owner == runtime_role:
                raise ValueError('Migration and runtime roles must differ')
            cursor.execute('SELECT rolname, rolsuper, rolbypassrls, rolcreaterole, rolcreatedb, rolreplication FROM pg_roles WHERE rolname IN (%s,%s)', (owner, runtime_role))
            roles = cursor.fetchall()
            if len(roles) != 2 or any(any(flags) for _, *flags in roles):
                raise ValueError('Restricted migration and runtime roles required')
            cursor.execute('SELECT pg_has_role(%s,%s,\'MEMBER\')', (runtime_role, owner))
            if cursor.fetchone()[0]:
                raise ValueError('Runtime must not inherit migration ownership')
            cursor.execute('SELECT pg_get_userbyid(nspowner) FROM pg_namespace WHERE nspname=%s', (schema,))
            if cursor.fetchone() != (owner,):
                raise ValueError('Migration role must own the declared schema')
            lock = int.from_bytes(hashlib.sha256(('storage-schema:'+schema).encode()).digest()[:8], 'big', signed=True)
            cursor.execute('SELECT pg_advisory_xact_lock(%s)', (lock,))
            cursor.execute(sql.SQL('SET LOCAL search_path TO {}, pg_catalog').format(sql.Identifier(schema)))
            cursor.execute('SELECT to_regclass(%s)', (schema+'.storage_schema_version',))
            if cursor.fetchone()[0] is not None:
                cursor.execute('SELECT version, sha256, runtime_role FROM storage_schema_version')
                if cursor.fetchall() != [(1, digest, runtime_role)]:
                    raise ValueError('Storage schema version differs')
                return False
            cursor.execute('SELECT tablename FROM pg_tables WHERE schemaname=%s', (schema,))
            if cursor.fetchall():
                raise ValueError('Fresh storage schema must be empty')
            cursor.execute(raw.decode())
            cursor.execute('CREATE TABLE storage_schema_version (version integer PRIMARY KEY CHECK(version=1), sha256 text NOT NULL, runtime_role text NOT NULL)')
            cursor.execute('INSERT INTO storage_schema_version VALUES (1,%s,%s)', (digest, runtime_role))
            cursor.execute(sql.SQL('GRANT USAGE ON SCHEMA {} TO {}').format(sql.Identifier(schema), sql.Identifier(runtime_role)))
            cursor.execute(sql.SQL('GRANT SELECT, UPDATE(id) ON tenants TO {}').format(sql.Identifier(runtime_role)))
            cursor.execute(sql.SQL('GRANT SELECT, INSERT, UPDATE ON storage_settings TO {}').format(sql.Identifier(runtime_role)))
    return True


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database-url-file', type=Path, required=True)
    parser.add_argument('--schema', required=True)
    parser.add_argument('--runtime-role', required=True)
    args = parser.parse_args()
    try:
        with psycopg.connect(args.database_url_file.read_text().strip()) as connection:
            apply(connection, args.schema, args.runtime_role)
    except Exception:
        raise SystemExit('Storage schema application failed; no credentials or database details are reported') from None
