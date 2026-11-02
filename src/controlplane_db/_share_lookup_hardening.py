"""Forward-only hardening shared by owner migration and legacy startup."""
from sqlalchemy import text


def apply(connection):
    # Explicit relation/operator resolution defeats temporary-schema shadowing.
    connection.execute(text("""
        CREATE OR REPLACE FUNCTION public.sociacl_share_lookup_by_hash(p_hash varchar)
        RETURNS SETOF public.sociacl_share_links
        LANGUAGE sql STABLE SECURITY DEFINER
        SET search_path = pg_catalog, public, pg_temp
        AS $$ SELECT * FROM public.sociacl_share_links
              WHERE token_hash OPERATOR(pg_catalog.=) p_hash LIMIT 1 $$
    """))
    connection.execute(text("REVOKE ALL ON FUNCTION public.sociacl_share_lookup_by_hash(varchar) FROM PUBLIC"))
    # Match the existing application-role convention without creating roles.
    connection.execute(text("""
        DO $$ DECLARE role_name text; BEGIN
            FOREACH role_name IN ARRAY ARRAY['controlplane', 'controlplane_app'] LOOP
                IF EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = role_name) THEN
                    EXECUTE format('GRANT EXECUTE ON FUNCTION public.sociacl_share_lookup_by_hash(varchar) TO %I', role_name);
                END IF;
            END LOOP;
        END $$
    """))
