-- The coordinator may discover rows, but cannot mint capabilities or write
-- financial sources. These private owner routines recheck actual database rows.
CREATE FUNCTION public.account_test_table_name(p_relation oid) RETURNS text
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp SET row_security=off AS $$
DECLARE result text;
BEGIN
  SELECT c.relname INTO result FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
    WHERE c.oid=p_relation AND n.nspname='public' AND c.relkind='r' AND c.relname=ANY(__SOURCE_TABLES__);
  IF result IS NULL THEN RAISE EXCEPTION 'Unknown TEST financial owner' USING ERRCODE='42501'; END IF;
  RETURN result;
END $$;

CREATE FUNCTION public.account_lock_test_financial_sources(p_subject text,p_at timestamptz) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp SET row_security=off AS $$
DECLARE item record;
BEGIN
  PERFORM public.account_require_financial_inventory(p_subject,p_at);
  PERFORM public.account_lock_financial_inventory(p_subject,p_at,NULL);
  IF NOT public.account_lock_test_data_policy() THEN
    RAISE EXCEPTION 'Database TEST policy required' USING ERRCODE='42501'; END IF;
  FOR item IN WITH RECURSIVE sources(oid) AS (
    SELECT c.oid FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
      WHERE n.nspname='public' AND c.relkind='r' AND c.relname=ANY(__SOURCE_TABLES__)
    UNION SELECT f.conrelid FROM pg_catalog.pg_constraint f JOIN sources s ON f.confrelid=s.oid
      WHERE f.contype='f')
    SELECT c.oid,n.nspname,c.relname FROM sources s JOIN pg_catalog.pg_class c ON c.oid=s.oid
      JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace WHERE c.relkind='r' ORDER BY c.oid
  LOOP
    IF NOT EXISTS(SELECT 1 FROM pg_catalog.pg_locks WHERE pid=pg_backend_pid() AND relation=item.oid
      AND granted AND mode IN ('ShareRowExclusiveLock','ExclusiveLock','AccessExclusiveLock')) THEN
      EXECUTE format('LOCK TABLE %I.%I IN SHARE ROW EXCLUSIVE MODE',item.nspname,item.relname);
    END IF;
  END LOOP;
END $$;

CREATE FUNCTION public.account_test_read_row(p_relation oid,p_tid text) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp SET row_security=off AS $$
DECLARE name text; result jsonb;
BEGIN
  name:=public.account_test_table_name(p_relation);
  EXECUTE format('SELECT to_jsonb(t) FROM ONLY public.%I t WHERE ctid=$1::tid FOR UPDATE',name)
    INTO result USING p_tid;
  IF result IS NULL THEN RAISE EXCEPTION 'Original TEST source row required' USING ERRCODE='42501'; END IF;
  RETURN result;
END $$;

CREATE FUNCTION public.account_test_scope(p_subject text,p_at timestamptz,p_tenant text) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp SET row_security=off AS $$
DECLARE life jsonb; ids jsonb; keys jsonb:='[]'; effects jsonb; users text[]; aliases text[];
BEGIN
  SELECT a.effects INTO life FROM public.account_lifecycles a WHERE a.subject=p_subject AND a.closed_at=p_at;
  IF p_tenant IS NULL THEN ids:=life->'platform_profile'->'user_ids';
  ELSE
    IF NOT coalesce(life->'scope_tenants' @> jsonb_build_array(p_tenant),false) THEN
      RAISE EXCEPTION 'Original TEST tenant scope required' USING ERRCODE='42501'; END IF;
    SELECT s.user_ids,s.effects INTO ids,effects FROM public.account_lifecycle_scopes s
      WHERE s.subject=p_subject AND s.tenant_id=p_tenant::uuid;
    IF effects->'profile_inventory_complete' IS DISTINCT FROM 'true'::jsonb THEN
      RAISE EXCEPTION 'Original TEST profile scope required' USING ERRCODE='42501'; END IF;
    keys:=coalesce(effects->'api_keys'->'keys','[]'::jsonb);
  END IF;
  IF jsonb_typeof(ids) IS DISTINCT FROM 'array' OR jsonb_typeof(keys) IS DISTINCT FROM 'array' THEN
    RAISE EXCEPTION 'Original TEST identity inventory required' USING ERRCODE='42501'; END IF;
  IF jsonb_array_length(ids)>100000 OR jsonb_array_length(keys)>100000
    OR EXISTS(SELECT 1 FROM jsonb_array_elements(ids) e WHERE jsonb_typeof(e) IS DISTINCT FROM 'string')
    OR EXISTS(SELECT 1 FROM jsonb_array_elements(keys) e WHERE jsonb_typeof(e) IS DISTINCT FROM 'object'
      OR jsonb_typeof(e->'id') IS DISTINCT FROM 'string') THEN
    RAISE EXCEPTION 'Malformed original TEST identities' USING ERRCODE='42501'; END IF;
  users:=ARRAY(SELECT (value#>>'{}')::uuid::text FROM jsonb_array_elements(ids));
  aliases:=ARRAY[p_subject]||ARRAY(SELECT 'apikey:'||(value->>'id')::uuid::text FROM jsonb_array_elements(keys));
  IF cardinality(users)<>(SELECT count(DISTINCT x) FROM unnest(users) x)
    OR cardinality(aliases)<>(SELECT count(DISTINCT x) FROM unnest(aliases) x) THEN
    RAISE EXCEPTION 'Ambiguous original TEST identities' USING ERRCODE='42501'; END IF;
  RETURN jsonb_build_object('users',to_jsonb(users),'aliases',to_jsonb(aliases));
END $$;

CREATE FUNCTION public.account_test_check_row(p_name text,p_data jsonb) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp SET row_security=off AS $$
DECLARE mode boolean;
BEGIN
  IF (p_data ? 'livemode' AND p_data->'livemode' IS DISTINCT FROM 'false'::jsonb)
    OR (p_data ? 'chain_id' AND p_data->>'chain_id' IS DISTINCT FROM '84532') THEN
    RAISE EXCEPTION 'Live or unsupported financial network is not TEST data' USING ERRCODE='42501'; END IF;
  IF p_name='connect_access_grants' THEN
    SELECT r.livemode INTO mode FROM public.connect_access_grants g
      JOIN public.connect_access_states s USING(tenant_id,host_org_id)
      JOIN public.connect_recipient_accounts r USING(tenant_id,host_org_id)
      WHERE g.id=(p_data->>'id')::uuid AND g.tenant_id=(p_data->>'tenant_id')::uuid
        AND r.attempt_id=g.enrollment_attempt_id AND r.stripe_account_id=g.account_id;
  ELSIF p_name='connect_access_results' THEN
    SELECT r.livemode INTO mode FROM public.connect_access_grants g
      JOIN public.connect_access_states s USING(tenant_id,host_org_id)
      JOIN public.connect_recipient_accounts r USING(tenant_id,host_org_id)
      WHERE g.id=(p_data->>'grant_id')::uuid AND g.tenant_id=(p_data->>'tenant_id')::uuid
        AND r.attempt_id=g.enrollment_attempt_id AND r.stripe_account_id=g.account_id;
  ELSIF p_name='connect_access_states' THEN
    SELECT r.livemode INTO mode FROM public.connect_recipient_accounts r
      WHERE r.tenant_id=(p_data->>'tenant_id')::uuid AND r.host_org_id=(p_data->>'host_org_id')::uuid;
  ELSE RETURN;
  END IF;
  IF mode IS DISTINCT FROM false THEN
    RAISE EXCEPTION 'Live or unresolved Connect ancestry is not TEST data' USING ERRCODE='42501'; END IF;
END $$;

CREATE FUNCTION public.account_test_check_parties(p_subject text,p_name text,p_data jsonb,p_users text[]) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp SET row_security=off AS $$
BEGIN
  IF p_name NOT IN ('hypermesh_leases','hypermesh_orders','hypermesh_fills','hypermesh_payouts') THEN RETURN; END IF;
  IF EXISTS(SELECT 1 FROM public.hypermesh_financial_parties(p_name,p_data) p
      WHERE p.direct_reference AND p.subject<>p_subject AND NOT p.subject=ANY(p_users))
    OR EXISTS(SELECT 1 FROM public.hypermesh_financial_parties(p_name,p_data) p
      WHERE p.direct_reference AND p.subject=ANY(p_users) AND
        (EXISTS(SELECT 1 FROM public.users u WHERE u.keycloak_sub=p.subject)
         OR EXISTS(SELECT 1 FROM public.identity_retirements i WHERE i.subject=p.subject))) THEN
    RAISE EXCEPTION 'Conflicting native TEST financial parties' USING ERRCODE='42501'; END IF;
END $$;

CREATE FUNCTION public.account_test_edge(p_child oid,p_parent oid,p_child_data jsonb,p_parent_data jsonb) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp SET row_security=off AS $$
DECLARE edge record; i integer; matches boolean; child_name text; parent_name text;
BEGIN
  child_name:=public.account_test_table_name(p_child); parent_name:=public.account_test_table_name(p_parent);
  IF p_child_data ? 'tenant_id' AND p_parent_data ? 'tenant_id'
    AND p_child_data->'tenant_id' IS DISTINCT FROM p_parent_data->'tenant_id' THEN RETURN false; END IF;
  FOR edge IN SELECT
      ARRAY(SELECT a.attname FROM unnest(f.conkey) WITH ORDINALITY k(num,ord)
        JOIN pg_catalog.pg_attribute a ON a.attrelid=f.conrelid AND a.attnum=k.num ORDER BY k.ord) AS child_cols,
      ARRAY(SELECT a.attname FROM unnest(f.confkey) WITH ORDINALITY k(num,ord)
        JOIN pg_catalog.pg_attribute a ON a.attrelid=f.confrelid AND a.attnum=k.num ORDER BY k.ord) AS parent_cols
      FROM pg_catalog.pg_constraint f WHERE f.contype='f' AND f.conrelid=p_child AND f.confrelid=p_parent
  LOOP
    matches:=true;
    FOR i IN 1..cardinality(edge.child_cols) LOOP
      IF p_child_data->edge.child_cols[i] IS NULL OR p_child_data->edge.child_cols[i]='null'::jsonb
        OR p_child_data->edge.child_cols[i] IS DISTINCT FROM p_parent_data->edge.parent_cols[i] THEN
        matches:=false; EXIT; END IF;
    END LOOP;
    IF matches THEN RETURN true; END IF;
  END LOOP;
  FOR edge IN SELECT * FROM (VALUES
    ('billing_tax_orders','billing_records','billing_record_id','id'),
    ('hypermesh_leases','billing_records','billing_record_id','id'),
    ('hypermesh_payouts','hypermesh_leases','lease_id','id'),
    ('hypermesh_jobs','hypermesh_leases','lease_id','id'),
    ('hypermesh_tunnels','hypermesh_leases','lease_id','id'),
    ('hypermesh_tickets','hypermesh_leases','lease_id','id'),
    ('hypermesh_fills','hypermesh_orders','order_id','order_id')) e(child,parent,child_col,parent_col)
    WHERE e.child=child_name AND e.parent=parent_name
  LOOP
    IF p_child_data->edge.child_col IS NOT NULL AND p_child_data->edge.child_col<>'null'::jsonb
      AND p_child_data->edge.child_col=p_parent_data->edge.parent_col
      AND p_child_data->'tenant_id'=p_parent_data->'tenant_id' THEN RETURN true; END IF;
  END LOOP;
  RETURN false;
END $$;

CREATE FUNCTION public.account_stage_test_delete(p_subject text,p_at timestamptz,p_relation oid,p_tid text,p_parent oid,p_parent_tid text) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp SET row_security=off AS $$
DECLARE name text; data jsonb; parent_data jsonb; scope jsonb; users text[]; aliases text[]; eligible boolean:=false; digest bytea;
BEGIN
  PERFORM public.account_lock_test_financial_sources(p_subject,p_at);
  IF (p_parent IS NULL)<>(p_parent_tid IS NULL) THEN
    RAISE EXCEPTION 'Exact TEST parent scope required' USING ERRCODE='42501'; END IF;
  name:=public.account_test_table_name(p_relation); data:=public.account_test_read_row(p_relation,p_tid);
  IF p_parent IS NOT NULL THEN
    parent_data:=public.account_test_read_row(p_parent,p_parent_tid);
    IF NOT EXISTS(SELECT 1 FROM public.account_test_delete_capabilities c
      WHERE c.transaction_id=pg_current_xact_id()::text AND c.relation=p_parent
        AND c.source_subject=p_subject AND c.source_closed_at=p_at AND c.row_tid=p_parent_tid::tid::text
        AND c.row_digest=sha256(convert_to(parent_data::text,'UTF8')))
      OR NOT public.account_test_edge(p_relation,p_parent,data,parent_data) THEN
      RAISE EXCEPTION 'Authorized native TEST dependency required' USING ERRCODE='42501'; END IF;
    eligible:=true;
  END IF;
  scope:=public.account_test_scope(p_subject,p_at,coalesce(data->>'tenant_id',parent_data->>'tenant_id'));
  users:=ARRAY(SELECT jsonb_array_elements_text(scope->'users'));
  aliases:=ARRAY(SELECT jsonb_array_elements_text(scope->'aliases'));
  IF name='billing_records' AND data->>'actor'='tenant' THEN
    RAISE EXCEPTION 'Company financial records require their own owner authority' USING ERRCODE='42501'; END IF;
  IF name='billing_records' AND EXISTS(SELECT 1 FROM public.account_financial_source_bindings b
      WHERE b.owner='billing' AND b.kind='payment' AND b.resource=data->>'id'
        AND b.tenant_id IS NOT DISTINCT FROM (data->>'tenant_id')::uuid AND b.subject<>p_subject) THEN
    RAISE EXCEPTION 'Shared native billing ownership' USING ERRCODE='42501'; END IF;
  PERFORM public.account_test_check_row(name,data);
  PERFORM public.account_test_check_parties(p_subject,name,data,users);
  IF (data ? 'buyer_id' AND data->>'buyer_id' IS NOT NULL AND NOT data->>'buyer_id'=ANY(users))
    OR (data ? 'user_id' AND data->>'user_id' IS NOT NULL AND NOT data->>'user_id'=ANY(users))
    OR (data ? 'owner_sub' AND data->>'owner_sub' IS NOT NULL AND NOT data->>'owner_sub'=ANY(aliases)) THEN
    RAISE EXCEPTION 'Foreign native TEST customer reference' USING ERRCODE='42501'; END IF;
  IF p_parent IS NULL THEN
    IF name='billing_records' THEN
      eligible:=data->>'actor'<>'tenant' AND jsonb_typeof(data->'metadata')='object'
        AND (NOT (data->'metadata' ? 'actor_sub') OR data->'metadata'->'actor_sub'='null'::jsonb
          OR jsonb_typeof(data->'metadata'->'actor_sub')='string')
        AND (data->>'user_id' IS NULL OR data->>'user_id'=ANY(users))
        AND (data->'metadata'->>'actor_sub' IS NULL OR data->'metadata'->>'actor_sub'=ANY(aliases))
        AND (data->>'user_id'=ANY(users) OR data->'metadata'->>'actor_sub'=ANY(aliases));
    ELSIF name='hypermesh_leases' THEN eligible:=data->>'renter_user_id'=ANY(users||aliases);
    ELSIF name='connect_access_grants' THEN eligible:=data->>'owner_sub'=ANY(aliases);
    ELSIF name IN ('usdc_deposit_addresses','usdc_payment_intents','usdc_chain_transfers','onramp_sessions') THEN
      eligible:=data->>'user_id'=ANY(users);
    ELSIF name='payer_mismatch_accounts' THEN
      eligible:=EXISTS(SELECT 1 FROM public.account_financial_source_bindings b WHERE b.subject=p_subject
        AND b.owner='payment' AND b.kind=name AND b.resource=data->>'account_key')
        AND NOT EXISTS(SELECT 1 FROM public.account_financial_source_bindings b WHERE b.subject<>p_subject
          AND b.kind=name AND b.resource=data->>'account_key');
    END IF;
  END IF;
  IF eligible IS DISTINCT FROM true THEN
    RAISE EXCEPTION 'Original native TEST payer root required' USING ERRCODE='42501'; END IF;
  digest:=sha256(convert_to(data::text,'UTF8'));
  IF EXISTS(SELECT 1 FROM public.account_test_delete_capabilities c
      WHERE c.transaction_id=pg_current_xact_id()::text AND c.relation=p_relation AND c.row_digest=digest
        AND (c.source_subject IS DISTINCT FROM p_subject OR c.source_closed_at IS DISTINCT FROM p_at
          OR c.row_tid IS DISTINCT FROM p_tid::tid::text)) THEN
    RAISE EXCEPTION 'Conflicting native TEST capability scope' USING ERRCODE='42501'; END IF;
  IF (SELECT count(*) FROM public.account_test_delete_capabilities WHERE transaction_id=pg_current_xact_id()::text)>=1000 THEN
    RAISE EXCEPTION 'Bounded TEST capability inventory required' USING ERRCODE='42501'; END IF;
  INSERT INTO public.account_test_delete_capabilities(transaction_id,relation,row_digest,source_subject,source_closed_at,row_tid)
    VALUES(pg_current_xact_id()::text,p_relation,digest,p_subject,p_at,p_tid::tid::text) ON CONFLICT DO NOTHING;
END $$;

CREATE FUNCTION public.account_delete_test_financial_row(p_subject text,p_at timestamptz,p_relation oid,p_tid text) RETURNS integer
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp SET row_security=off AS $$
DECLARE name text; data jsonb; edge record; found_child boolean; predicate text; affected integer;
BEGIN
  PERFORM public.account_lock_test_financial_sources(p_subject,p_at);
  name:=public.account_test_table_name(p_relation); data:=public.account_test_read_row(p_relation,p_tid);
  PERFORM public.account_test_check_row(name,data);
  IF NOT EXISTS(SELECT 1 FROM public.account_test_delete_capabilities c
    WHERE c.transaction_id=pg_current_xact_id()::text AND c.relation=p_relation
      AND c.row_digest=sha256(convert_to(data::text,'UTF8')) AND c.source_subject=p_subject
      AND c.source_closed_at=p_at AND c.row_tid=p_tid::tid::text) THEN
    RAISE EXCEPTION 'Native TEST delete capability required' USING ERRCODE='42501'; END IF;
  -- Even CASCADE cannot erase an undiscovered physical/foreign-owner child.
  FOR edge IN SELECT f.*,n.nspname,c.relname FROM pg_catalog.pg_constraint f JOIN pg_catalog.pg_class c ON c.oid=f.conrelid
    JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace WHERE f.contype='f' AND f.confrelid=p_relation
  LOOP
    SELECT string_agg(format('c.%I=p.%I',a.attname,b.attname),' AND ' ORDER BY k.ord) INTO predicate
      FROM unnest(edge.conkey,edge.confkey) WITH ORDINALITY k(child_col,parent_col,ord)
      JOIN pg_catalog.pg_attribute a ON a.attrelid=edge.conrelid AND a.attnum=k.child_col
      JOIN pg_catalog.pg_attribute b ON b.attrelid=p_relation AND b.attnum=k.parent_col;
    EXECUTE format('SELECT EXISTS(SELECT 1 FROM %I.%I c JOIN ONLY public.%I p ON %s WHERE p.ctid=$1::tid AND (c.tableoid<>p.tableoid OR c.ctid<>p.ctid))',
      edge.nspname,edge.relname,name,predicate) INTO found_child USING p_tid;
    IF found_child THEN RAISE EXCEPTION 'Native dependent rows must be removed first' USING ERRCODE='42501'; END IF;
  END LOOP;
  FOR edge IN SELECT * FROM (VALUES
    ('billing_tax_orders','billing_records','billing_record_id','id'),
    ('hypermesh_leases','billing_records','billing_record_id','id'),
    ('hypermesh_payouts','hypermesh_leases','lease_id','id'),
    ('hypermesh_jobs','hypermesh_leases','lease_id','id'),
    ('hypermesh_tunnels','hypermesh_leases','lease_id','id'),
    ('hypermesh_tickets','hypermesh_leases','lease_id','id'),
    ('hypermesh_fills','hypermesh_orders','order_id','order_id')) e(child,parent,child_col,parent_col)
    WHERE e.parent=name
  LOOP
    IF to_regclass(format('public.%I',edge.child)) IS NOT NULL THEN
      EXECUTE format('SELECT EXISTS(SELECT 1 FROM public.%I c WHERE to_jsonb(c)->>$1=$2)',edge.child)
        INTO found_child USING edge.child_col,data->>edge.parent_col;
      IF found_child THEN RAISE EXCEPTION 'Native logical dependencies must be removed first' USING ERRCODE='42501'; END IF;
    END IF;
  END LOOP;
  EXECUTE format('DELETE FROM ONLY public.%I WHERE ctid=$1::tid',name) USING p_tid;
  GET DIAGNOSTICS affected=ROW_COUNT;
  IF affected<>1 THEN RAISE EXCEPTION 'Native TEST row deletion not acknowledged' USING ERRCODE='42501'; END IF;
  DELETE FROM public.account_test_delete_capabilities WHERE transaction_id=pg_current_xact_id()::text
    AND relation=p_relation AND row_digest=sha256(convert_to(data::text,'UTF8'));
  RETURN affected;
END $$;

CREATE FUNCTION public.account_clear_test_delete_capabilities() RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp SET row_security=off AS $$
BEGIN DELETE FROM public.account_test_delete_capabilities WHERE transaction_id=pg_current_xact_id()::text; END $$;

CREATE FUNCTION public.account_test_json_mentions(p_value jsonb,p_ids text[]) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp SET row_security=off AS $$
DECLARE item jsonb;
BEGIN
  IF jsonb_typeof(p_value)='string' THEN RETURN coalesce(p_value#>>'{}'=ANY(p_ids),false);
  ELSIF jsonb_typeof(p_value)='array' THEN
    FOR item IN SELECT value FROM jsonb_array_elements(p_value) LOOP
      IF public.account_test_json_mentions(item,p_ids) THEN RETURN true; END IF; END LOOP;
  ELSIF jsonb_typeof(p_value)='object' THEN
    FOR item IN SELECT value FROM jsonb_each(p_value) LOOP
      IF public.account_test_json_mentions(item,p_ids) THEN RETURN true; END IF; END LOOP;
  END IF;
  RETURN false;
END $$;

CREATE FUNCTION public.account_reconcile_test_financial_bindings(p_subject text,p_at timestamptz) RETURNS bigint
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp SET row_security=off AS $$
DECLARE scope jsonb; tenant text; ids text[]:=ARRAY[p_subject]; item record; name text; identity_sql text;
  source jsonb; any_rows boolean; mentioned boolean; remaining bigint;
BEGIN
  PERFORM public.account_lock_test_financial_sources(p_subject,p_at);
  FOR tenant IN SELECT NULL::text UNION SELECT s.tenant_id::text FROM public.account_lifecycle_scopes s WHERE s.subject=p_subject
  LOOP
    scope:=public.account_test_scope(p_subject,p_at,tenant);
    ids:=ids||ARRAY(SELECT jsonb_array_elements_text(scope->'users'))||ARRAY(SELECT jsonb_array_elements_text(scope->'aliases'));
  END LOOP;
  FOR item IN SELECT b.tenant_id,b.owner,b.kind,b.resource FROM public.account_financial_source_bindings b
    WHERE b.subject=p_subject ORDER BY b.owner,b.kind,b.resource LIMIT 1000
  LOOP
    name:=CASE WHEN item.owner='billing' AND item.kind='payment' THEN 'billing_records' ELSE item.kind END;
    PERFORM public.account_test_table_name(to_regclass(format('public.%I',name))::oid);
    identity_sql:=CASE WHEN name='host_payout_addresses'
      THEN '(to_jsonb(t)->>''host_org_id'')||'':''||(to_jsonb(t)->>''chain_id'')'
      ELSE 'coalesce(to_jsonb(t)->>''id'',to_jsonb(t)->>''grant_id'',to_jsonb(t)->>''revision_id'',to_jsonb(t)->>''account_key'',to_jsonb(t)->>''host_org_id'',to_jsonb(t)->>''order_id'',to_jsonb(t)->>''lease_id'',to_jsonb(t)->>''organization_id'')' END;
    any_rows:=false; mentioned:=false;
    FOR source IN EXECUTE format('SELECT to_jsonb(t) FROM public.%I t WHERE %s=$1 AND to_jsonb(t)->>''tenant_id'' IS NOT DISTINCT FROM $2',name,identity_sql)
      USING item.resource,item.tenant_id::text
    LOOP
      any_rows:=true;
      IF name='payer_mismatch_accounts' OR public.account_test_json_mentions(source,ids) THEN mentioned:=true; END IF;
    END LOOP;
    IF NOT mentioned THEN
      DELETE FROM public.account_financial_source_bindings b WHERE (NOT any_rows OR b.subject=p_subject)
        AND b.tenant_id IS NOT DISTINCT FROM item.tenant_id AND b.owner=item.owner AND b.kind=item.kind AND b.resource=item.resource;
    END IF;
  END LOOP;
  SELECT count(*) INTO remaining FROM public.account_financial_source_bindings b WHERE b.subject=p_subject;
  RETURN remaining;
END $$;
