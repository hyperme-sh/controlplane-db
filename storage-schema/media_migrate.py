"""Explicit additive storage-media schema preparation; no runtime bootstrap."""
import argparse
import hashlib
import importlib.util
from pathlib import Path
import psycopg
from psycopg import sql

ROOT=Path(__file__).parent
spec=importlib.util.spec_from_file_location('storage_base_migrate',ROOT/'migrate.py')
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
DDL=ROOT/'002_media_objects.sql'


def apply(connection,schema,runtime_role):
    schema,runtime_role=base.name(schema),base.name(runtime_role)
    raw=DDL.read_bytes();digest=hashlib.sha256(raw).hexdigest()
    with connection.transaction():
        # Validates restricted roles, ownership and the unchanged baseline;
        # its transaction advisory lock remains held until this outer commit.
        base.apply(connection,schema,runtime_role)
        with connection.cursor() as cursor:
            cursor.execute(sql.SQL('SET LOCAL search_path TO {},pg_catalog').format(sql.Identifier(schema)))
            cursor.execute('SELECT to_regclass(%s)',(schema+'.storage_media_schema_version',))
            if cursor.fetchone()[0] is not None:
                cursor.execute('SELECT version,sha256,runtime_role FROM storage_media_schema_version')
                if cursor.fetchall()!=[(2,digest,runtime_role)]:
                    raise ValueError('Storage media schema version differs')
                for name in ('storage_media_objects','storage_media_refs'):
                    cursor.execute('SELECT to_regclass(%s)',(schema+'.'+name,))
                    if cursor.fetchone()[0] is None:raise ValueError('Storage media schema incomplete')
                return False
            for name in ('storage_media_objects','storage_media_refs'):
                cursor.execute('SELECT to_regclass(%s)',(schema+'.'+name,))
                if cursor.fetchone()[0] is not None:raise ValueError('Storage media schema incomplete')
            cursor.execute(raw.decode())
            cursor.execute('CREATE TABLE storage_media_schema_version (version integer PRIMARY KEY CHECK(version=2),sha256 text NOT NULL,runtime_role text NOT NULL)')
            cursor.execute('INSERT INTO storage_media_schema_version VALUES (2,%s,%s)',(digest,runtime_role))
            cursor.execute(sql.SQL('GRANT SELECT,INSERT,UPDATE ON storage_media_objects TO {}').format(sql.Identifier(runtime_role)))
            cursor.execute(sql.SQL('GRANT SELECT,INSERT,DELETE ON storage_media_refs TO {}').format(sql.Identifier(runtime_role)))
            cursor.execute(sql.SQL('GRANT EXECUTE ON FUNCTION storage_media_object_transition(),storage_media_ref_transition() TO {}').format(sql.Identifier(runtime_role)))
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
        raise SystemExit('Storage media schema application failed; no private details are reported') from None
