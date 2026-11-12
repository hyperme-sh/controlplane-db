"""Expected additive contact-lane schema, independent of the migration code."""
CONTACT_TABLE = {
    'columns': [
        ['lane_id', 'text', True, None, '', '', '"default"'],
        ['message_id', 'text', True, None, '', '', '"default"'],
        ['ciphertext', 'bytea', True, None, '', '', None],
        ['byte_size', 'integer', False, 'octet_length(ciphertext)', '', 's', None],
        ['created_at', 'timestamp with time zone', True, 'clock_timestamp()', '', '', None],
        ['expires_at', 'timestamp with time zone', True, None, '', '', None],
    ],
    'constraints': [
        ['sociacl_contact_messages_check', 'c', "CHECK (expires_at > created_at AND expires_at <= (created_at + '7 days'::interval))", True],
        ['sociacl_contact_messages_ciphertext_check', 'c', 'CHECK (octet_length(ciphertext) >= 32 AND octet_length(ciphertext) <= 65536)', True],
        ['sociacl_contact_messages_lane_id_check', 'c', "CHECK (lane_id ~ '^[0-9a-f]{64}$'::text)", True],
        ['sociacl_contact_messages_message_id_check', 'c', "CHECK (message_id ~ '^[0-9a-f]{64}$'::text)", True],
        ['sociacl_contact_messages_pkey', 'p', 'PRIMARY KEY (lane_id, message_id)', True],
    ],
    'indexes': [
        ['sociacl_contact_expiry', 'CREATE INDEX sociacl_contact_expiry ON public.sociacl_contact_messages USING btree (expires_at)'],
        ['sociacl_contact_messages_pkey', 'CREATE UNIQUE INDEX sociacl_contact_messages_pkey ON public.sociacl_contact_messages USING btree (lane_id, message_id)'],
    ],
    'rls': [False, False], 'policies': [], 'triggers': [], 'column_grants': [],
}


def assert_contact_lane_delta(after):
    table = after['tables']['sociacl_contact_messages']
    for field, expected in CONTACT_TABLE.items():
        if table.get(field) != expected:
            raise AssertionError('Contact-lane schema differs: ' + field)
    if set(table) != set(CONTACT_TABLE) | {'grants'}:
        raise AssertionError('Unexpected contact-lane schema fields')
    privileges = {'DELETE', 'INSERT', 'REFERENCES', 'SELECT', 'TRIGGER', 'TRUNCATE', 'UPDATE'}
    grants = table['grants']
    # PostgreSQL 17 added MAINTAIN to the owner's default table privileges.
    if (not all(len(g) == 3 and g[0] == 'OWNER' and g[2] is False for g in grants)
            or {g[1] for g in grants} not in (privileges, privileges | {'MAINTAIN'})
            or len(grants) != len({g[1] for g in grants})):
        raise AssertionError('Contact-lane grants differ')
    after['tables'].pop('sociacl_contact_messages')


def assert_same_schema(actual, expected):
    """Retain exact equality without dumping the entire database into logs."""
    if actual == expected:
        return
    differences = []
    for kind in sorted(set(actual) | set(expected)):
        left, right = actual.get(kind, {}), expected.get(kind, {})
        for name in sorted(set(left) | set(right)):
            if left.get(name) != right.get(name):
                differences.append(kind + '.' + name)
    raise AssertionError('Schema differs: ' + ', '.join(differences))
