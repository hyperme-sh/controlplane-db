"""Additive organization membership delta; preserve all older schema checks."""


def assert_organization_membership_delta(after):
    table = after['tables']['organization_user_memberships']
    assert table['columns'] == [
        ['id', 'uuid', True, None, '', '', None],
        ['tenant_id', 'uuid', True, None, '', '', None],
        ['organization_id', 'uuid', True, None, '', '', None],
        ['user_id', 'uuid', True, None, '', '', None],
        ['role', 'character varying(16)', True, None, '', '', '"default"'],
        ['created_at', 'timestamp with time zone', True, 'now()', '', '', None],
    ]
    assert table['rls'] == [True, True]
    assert table['triggers'] == [] and table['column_grants'] == []
    assert len(table['policies']) == 1
    policy = table['policies'][0]
    assert policy[:4] == ['organization_membership_tenant', '*', True, ['PUBLIC']]
    assert policy[4] == policy[5]
    assert 'tenant_id' in policy[4] and "current_setting('app.current_tenant_id'::text, true)" in policy[4]
    constraints = {row[0]: row[1:] for row in table['constraints']}
    assert set(constraints) == {'organization_user_memberships_pkey', 'uq_org_user_membership_role',
                                'fk_org_user_membership_org', 'fk_org_user_membership_user', 'ck_org_user_membership_role'}
    assert constraints['organization_user_memberships_pkey'] == ['p', 'PRIMARY KEY (id)', True]
    assert constraints['uq_org_user_membership_role'] == ['u', 'UNIQUE (tenant_id, organization_id, user_id, role)', True]
    for name, column, target in [('org', 'organization_id', 'organizations'), ('user', 'user_id', 'users')]:
        assert constraints['fk_org_user_membership_'+name] == ['f', f'FOREIGN KEY ({column}, tenant_id) REFERENCES {target}(id, tenant_id) ON DELETE CASCADE', True]
    check = constraints['ck_org_user_membership_role']
    assert check[0] == 'c' and check[2] is True
    assert all("'"+role+"'" in check[1] for role in ('member', 'owner', 'admin')) and 'platform' not in check[1]
    assert {row[0] for row in table['indexes']} == {'organization_user_memberships_pkey', 'uq_org_user_membership_role'}
    assert table['grants'] and all(row[0] == 'OWNER' and row[2] is False for row in table['grants'])
    after['tables'].pop('organization_user_memberships')
    users = after['tables']['users']
    constraint = ['uq_users_id_tenant', 'u', 'UNIQUE (id, tenant_id)', True]
    assert constraint in users['constraints']; users['constraints'].remove(constraint)
    index = ['uq_users_id_tenant', 'CREATE UNIQUE INDEX uq_users_id_tenant ON public.users USING btree (id, tenant_id)']
    assert index in users['indexes']; users['indexes'].remove(index)
