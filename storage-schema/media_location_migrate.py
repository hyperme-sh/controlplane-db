"""Explicit additive provider-location schema; never guesses legacy locations."""
import hashlib
import importlib.util
from pathlib import Path
from psycopg import sql

ROOT=Path(__file__).parent
spec=importlib.util.spec_from_file_location('storage_location_media_base',ROOT/'media_migrate.py')
media=importlib.util.module_from_spec(spec);spec.loader.exec_module(media)
DDL=ROOT/'003_media_locations.sql'


def apply(connection,schema,runtime_role):
    schema,runtime_role=media.base.name(schema),media.base.name(runtime_role)
    raw=DDL.read_bytes();digest=hashlib.sha256(raw).hexdigest()
    with connection.transaction():
        media.apply(connection,schema,runtime_role)
        with connection.cursor() as cursor:
            cursor.execute(sql.SQL('SET LOCAL search_path TO {},pg_catalog,pg_temp').format(sql.Identifier(schema)))
            cursor.execute('SELECT to_regclass(%s)',(schema+'.storage_media_location_version',))
            if cursor.fetchone()[0] is not None:
                cursor.execute('SELECT version,sha256,runtime_role FROM storage_media_location_version')
                if cursor.fetchall()!=[(3,digest,runtime_role)]:raise ValueError('Media location schema differs')
                cursor.execute('SELECT to_regclass(%s)',(schema+'.storage_media_locations',))
                if cursor.fetchone()[0] is None:raise ValueError('Media location schema incomplete')
                return False
            cursor.execute('SELECT to_regclass(%s)',(schema+'.storage_media_locations',))
            if cursor.fetchone()[0] is not None:raise ValueError('Media location schema incomplete')
            cursor.execute(raw.decode())
            cursor.execute('CREATE TABLE storage_media_location_version (version integer PRIMARY KEY CHECK(version=3),sha256 text NOT NULL,runtime_role text NOT NULL)')
            cursor.execute('INSERT INTO storage_media_location_version VALUES (3,%s,%s)',(digest,runtime_role))
            cursor.execute(sql.SQL('GRANT SELECT,INSERT ON storage_media_locations TO {}').format(sql.Identifier(runtime_role)))
            cursor.execute(sql.SQL('GRANT EXECUTE ON FUNCTION storage_media_location_transition() TO {}').format(sql.Identifier(runtime_role)))
    return True
