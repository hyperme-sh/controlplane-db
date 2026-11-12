"""Expected additive first-contact schema, independent of the migration code."""
FIRST_CONTACT_TABLE = {
    'columns': [
        ['lane_id', 'text', True, None, '', '', '"default"'],
        ['message_id', 'text', True, None, '', '', '"default"'],
        ['ciphertext', 'bytea', True, None, '', '', None],
        ['byte_size', 'integer', False, 'octet_length(ciphertext)', '', 's', None],
        ['created_at', 'timestamp with time zone', True, 'clock_timestamp()', '', '', None],
        ['expires_at', 'timestamp with time zone', True, None, '', '', None],
    ],
    'constraints': [
        ['sociacl_first_contact_messages_check', 'c', "CHECK (expires_at > created_at AND expires_at <= (created_at + '7 days'::interval))", True],
        ['sociacl_first_contact_messages_ciphertext_check', 'c', 'CHECK (octet_length(ciphertext) >= 94 AND octet_length(ciphertext) <= 8192)', True],
        ['sociacl_first_contact_messages_lane_id_check', 'c', "CHECK (lane_id ~ '^[0-9a-f]{64}$'::text)", True],
        ['sociacl_first_contact_messages_message_id_check', 'c', "CHECK (message_id ~ '^[0-9a-f]{64}$'::text)", True],
        ['sociacl_first_contact_messages_pkey', 'p', 'PRIMARY KEY (lane_id, message_id)', True],
    ],
    'indexes': [
        ['sociacl_first_contact_expiry', 'CREATE INDEX sociacl_first_contact_expiry ON public.sociacl_first_contact_messages USING btree (expires_at)'],
        ['sociacl_first_contact_messages_pkey', 'CREATE UNIQUE INDEX sociacl_first_contact_messages_pkey ON public.sociacl_first_contact_messages USING btree (lane_id, message_id)'],
    ],
    'rls': [False, False], 'policies': [], 'triggers': [], 'column_grants': [],
}


def assert_first_contact_delta(after):
    table = after['tables']['sociacl_first_contact_messages']
    for field, expected in FIRST_CONTACT_TABLE.items():
        if table.get(field) != expected:
            raise AssertionError('Contact-lane schema differs: ' + field)
    if set(table) != set(FIRST_CONTACT_TABLE) | {'grants'}:
        raise AssertionError('Unexpected first-contact schema fields')
    privileges = {'DELETE', 'INSERT', 'REFERENCES', 'SELECT', 'TRIGGER', 'TRUNCATE', 'UPDATE'}
    grants = table['grants']
    # PostgreSQL 17 added MAINTAIN to the owner's default table privileges.
    if (not all(len(g) == 3 and g[0] == 'OWNER' and g[2] is False for g in grants)
            or {g[1] for g in grants} not in (privileges, privileges | {'MAINTAIN'})
            or len(grants) != len({g[1] for g in grants})):
        raise AssertionError('Contact-lane grants differ')
    after['tables'].pop('sociacl_first_contact_messages')

