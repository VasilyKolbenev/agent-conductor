"""A verified Codex quota reply may repeat the account id in its two own places; a key never.

The id is ``auth.json`` ``tokens.account_id``; the reply carries it as ``accountId`` of the
rate-limits reply (id 3) and as ``workspaceRouting.chatgptAccountId`` of the account reply
(id 2). Everything else of either login file is a key, wherever it stands. The fake runner
scans every spawn as the real one does (the allowed environment plus ``sensitive_extra``).
"""
import json
import threading
from datetime import timedelta

import pytest

from conductor.command.adapters import login_home
from conductor.command.adapters.codex_cli import (
    LOGIN_STATUS_ARGV, QUOTA_RPC, CodexCliTransport, codex_pin)
from conductor.command.adapters.codex_quota import (
    ACCOUNT_FIELD, masked_reply, reply_metadata, service_for)
from conductor.command.adapters.headless_login import LoginRoad
from conductor.command.adapters.process import ProcessOutcome, ProcessRunner
from conductor.command.adapters.quota_connection import NativeQuotaReadError
from conductor.command.adapters.service_metadata import ServiceMetadata
from conductor.command.quota_plans import quota_plan_for
from conductor.command.quota_service import QuotaService
from conductor.quota_collectors import QuotaCollector
from tests import relay_credentials as fake
from tests.test_service_metadata import fails, owner, scripted
from tests.test_subscription_quota import AT

ACCOUNT = '4d2f6b1e-7a3c-4c58-9e0b-5f1a2d3c4b6a'
OWNER = 'fake-owner-0164'
ISSUER = 'https://fake.invalid'
EMAIL = 'private.person@example.invalid'
CONTEXT = 'synthetic-context-value'
MCP_ACCESS = 'synthetic-mcp-access-token-0123'
MCP_REFRESH = 'synthetic-mcp-refresh-token-0123'
NAMES = ('auth.json', '.credentials.json')
CIRCUIT = ('_attempt', '_spawn_secrets', '_echoed_login')
WHOLE = ('_login_secrets', '_remember_login_values')
HOOKS = ('_service_for', '_reply_metadata', '_masked_reply')
WINDOW = {'usedPercent': 27, 'windowDurationMins': 300, 'resetsAt': int(AT.timestamp()) + 3600}


def login(**tokens):
    """An ``auth.json`` of the 0.164 ChatGPT shape; ``tokens`` replaces any one of its tokens."""
    leaf = fake.codex_leaf(**{'account_id': ACCOUNT, 'login_owner_id': OWNER,
        'oauth_provenance': {'issuer': ISSUER, 'client_id': 'fake-client'}, **tokens})
    return {**leaf, 'auth_mode': 'chatgpt'}


def mcp_login(**changes):
    """A ``.credentials.json``: the OAuth of the vendor's tool servers, which is no account's."""
    return {'synthetic-server|0a1b2c3d': {
        'server_name': 'synthetic-server', 'server_url': 'https://mcp.invalid/sse',
        'client_id': 'synthetic-client', 'access_token': MCP_ACCESS, 'expires_at': 1790000000000,
        'refresh_token': MCP_REFRESH, 'scopes': ['read'], **changes}}


TOKENS = login()['tokens']
KEY_TEXTS = (TOKENS['id_token'], TOKENS['access_token'], TOKENS['refresh_token'], OWNER, ISSUER,
             login()['last_refresh'], MCP_ACCESS, MCP_REFRESH)
KEYS = {item.encode() for item in KEY_TEXTS}


def bucket(**changes):
    return {'limitId': 'codex', 'limitName': None, 'primary': WINDOW, 'secondary': None,
            'planType': 'plus', **changes}


def account_reply(**changes):
    """The reply of ``account/read`` (id 2): the account, and the routing that names its id."""
    return {'account': {'type': 'chatgpt', 'email': EMAIL, 'planType': 'plus'},
            'requiresOpenaiAuth': False, 'workspaceRouting': {'chatgptAccountId': ACCOUNT},
            **changes}


def limits_reply(**changes):
    """The reply of ``account/rateLimits/read`` (id 3): the id, and the windows by limit id."""
    return {'accountId': ACCOUNT, 'rateLimitsByLimitId': {'codex': bucket()}, **changes}


def wire(initialize, account, limits, ascii_wire=True):
    """The three replies of the exchange as the app-server writes them, one row per line."""
    rows = ({'id': 1, 'result': initialize}, {'id': 2, 'result': account},
            {'id': 3, 'result': limits})
    return b'\n'.join(json.dumps(row, ensure_ascii=ascii_wire).encode() for row in rows) + b'\n'


class EchoRunner(ProcessRunner):
    """Answers the exchange with chosen replies, and scans every spawn as the real runner does."""

    def __init__(self, root, env, home):
        super().__init__(root, environ=env)
        self.home, self.specs, self.after, self.raw, self.ascii = home, [], None, None, True
        self.plain = b'codex-cli 0.164.0'
        self.initialize, self.account, self.limits = {'userAgent': 'native'}, account_reply(), (
            limits_reply())

    def transcript(self):
        return wire(self.initialize, self.account, self.limits, self.ascii)

    def run(self, spec):
        self.specs.append(spec)
        if spec.stdin_bytes is None:
            output = self.plain
        else:
            if self.after is not None:
                (self.home / 'auth.json').write_text(json.dumps(self.after))
            output = self.transcript() if self.raw is None else self.raw
        scanned = self.allowed_environment_values(
            spec.env_allow, overrides=spec.env) + spec.sensitive_extra
        return ProcessOutcome('completed', 0, output, False, spec.output_limit, 0, 'synthetic',
                              'delivered' if spec.stdin_bytes else 'not_provided',
                              output_contains_env_value=any(value in output for value in scanned))


def make(tmp_path, document=None, credentials=None):
    home = tmp_path / 'pinned'
    home.mkdir()
    (home / 'auth.json').write_text(json.dumps(login() if document is None else document))
    (home / '.credentials.json').write_text(
        json.dumps(mcp_login() if credentials is None else credentials))
    runner = EchoRunner(tmp_path, {'SELECTED': CONTEXT}, home)
    pin = codex_pin(str(tmp_path / 'native.exe'), ('SELECTED',), auth='subscription',
                    auth_home=str(home))
    counter = [0]

    def ids(kind):
        counter[0] += 1
        return kind + '-' + str(counter[0])
    return CodexCliTransport(pin, runner, root=tmp_path, clock=lambda: AT.isoformat(),
                             ids=ids), runner


def exchange(value):
    """One quota exchange through ``_attempt``, as the quota read puts it; a raise fails."""
    value._workspace.work_root()
    return value._attempt(QUOTA_RPC.argv, 'work', timeout=15, stdin_bytes=QUOTA_RPC.payload,
                          separate_stderr=True, stdin_completion_id=3)


def refused(value):
    with pytest.raises(NativeQuotaReadError):
        value.quota_connection().read()


def refused_as_an_echo(value):
    refused(value)
    assert value._login_echo is True


# -- the wiring: which class answers what -----------------------------------------------------


def test_the_mixin_is_the_first_base_of_codex_so_nothing_of_the_login_road_stands_ahead_of_it():
    assert CodexCliTransport.__bases__[0] is ServiceMetadata


@pytest.mark.parametrize('name', CIRCUIT)
def test_the_three_circuit_methods_of_codex_resolve_into_the_mixin(name):
    assert owner(CodexCliTransport, name) is ServiceMetadata


@pytest.mark.parametrize('name', WHOLE)
def test_what_publishes_and_remembers_the_login_stays_the_login_roads_in_codex(name):
    assert owner(CodexCliTransport, name) is LoginRoad


@pytest.mark.parametrize('name', HOOKS)
def test_the_three_hooks_of_codex_are_its_own(name):
    assert owner(CodexCliTransport, name) is CodexCliTransport


def test_only_the_exact_argv_with_the_exact_stdin_is_the_quota_exchange(tmp_path):
    value, _ = make(tmp_path)
    assert service_for(QUOTA_RPC.argv, QUOTA_RPC.payload) is QUOTA_RPC
    assert value._service_for(QUOTA_RPC.argv, QUOTA_RPC.payload) is QUOTA_RPC
    for argv, stdin in ((QUOTA_RPC.argv, QUOTA_RPC.payload + b'\n'), (QUOTA_RPC.argv, None),
                        (QUOTA_RPC.argv, b''), ((*QUOTA_RPC.argv, '--x'), QUOTA_RPC.payload),
                        (LOGIN_STATUS_ARGV, QUOTA_RPC.payload), (lambda *_: (), QUOTA_RPC.payload)):
        assert service_for(argv, stdin) is None and value._service_for(argv, stdin) is None


# -- the way in: a verified reply may repeat the id in its own places ---------------------------


def test_a_verified_reply_repeats_the_account_id_in_its_places_and_publishes_none_of_it(tmp_path):
    from tests.test_command_quota_routes import contracts, get, quota_api
    value, runner = make(tmp_path)
    assert value.quota_connection().read() == limits_reply()
    assert ACCOUNT.encode() in runner.specs[0].sensitive_extra
    extra = runner.specs[-1].sensitive_extra
    assert KEYS <= set(extra) and ACCOUNT.encode() not in extra
    assert not value._login_echo and value._service is None
    cache = QuotaService()
    collector = QuotaCollector(cache, (quota_plan_for('bound', value),), clock=lambda: AT)
    collector._collect(*collector._work[0])
    api = quota_api(tmp_path, service=cache, providers=contracts('bound'),
                    clock=lambda: AT.isoformat())
    row = json.dumps(get(api).payload['snapshots'][0])
    assert '"remaining_percent": 73' in row
    assert not any(secret in row for secret in (ACCOUNT, EMAIL, *KEY_TEXTS))


@pytest.mark.parametrize('account, limits', [
    ({}, {}), ({'workspaceRouting': None}, {}), ({}, {'accountId': None}),
    ({'workspaceRouting': None}, {'accountId': None})],
    ids=['both-places', 'limits-only', 'routing-only', 'neither'])
def test_the_id_may_stand_in_either_own_place_in_both_or_in_none(account, limits, tmp_path):
    value, runner = make(tmp_path)
    runner.account, runner.limits = account_reply(**account), limits_reply(**limits)
    assert value.quota_connection().read() == runner.limits
    assert not value._login_echo


@pytest.mark.parametrize('ascii_wire', [True, False])
def test_a_non_ascii_id_in_its_places_reads_on_either_wire_form(ascii_wire, tmp_path):
    account = 'fake-account-éè-0001-xxxxxx'
    value, runner = make(tmp_path, login(account_id=account))
    runner.ascii = ascii_wire
    runner.account = account_reply(workspaceRouting={'chatgptAccountId': account})
    runner.limits = limits_reply(accountId=account)
    assert value.quota_connection().read() == runner.limits
    assert not value._login_echo


def test_the_mask_blanks_the_id_in_its_two_places_and_only_there():
    own = {ACCOUNT_FIELD: frozenset((ACCOUNT.encode(),))}
    output = wire({'userAgent': 'native'}, account_reply(), limits_reply())
    masked = masked_reply(output, QUOTA_RPC, own)
    rows = [json.loads(line) for line in masked.splitlines()]
    assert rows[1]['result'] == account_reply(workspaceRouting={'chatgptAccountId': ''})
    assert rows[2]['result'] == limits_reply(accountId='')
    assert ACCOUNT.encode() not in masked
    for admitted in ({}, {'email': own[ACCOUNT_FIELD]}, {ACCOUNT_FIELD: frozenset((b'other',))}):
        assert ACCOUNT.encode() in masked_reply(output, QUOTA_RPC, admitted)


# -- the way out: the id anywhere else, in anything else, refuses -------------------------------


def outside(initialize=None, account=None, limits=None):
    return (initialize or {'userAgent': 'native'}, account or {}, limits or {})


PLACES = {
    'initialize-field': outside(initialize={'userAgent': 'native', 'accountId': ACCOUNT}),
    'initialize-inside-text': outside(initialize={'userAgent': 'native/' + ACCOUNT}),
    'account-object': outside(account={'account': {'type': 'chatgpt', 'email': ACCOUNT}}),
    'account-reply-id-field': outside(account={'accountId': ACCOUNT}),
    'account-reply-top-routing-key': outside(account={'chatgptAccountId': ACCOUNT}),
    'routing-extra-field': outside(account={'workspaceRouting': {
        'chatgptAccountId': ACCOUNT, 'id': ACCOUNT}}),
    'routing-nested': outside(account={'workspaceRouting': {
        'chatgptAccountId': ACCOUNT, 'entries': [{'id': ACCOUNT}]}}),
    'routing-inside-longer-text': outside(account={'workspaceRouting': {
        'chatgptAccountId': ACCOUNT + '-more'}}),
    'routing-is-a-string': outside(account={'workspaceRouting': ACCOUNT}),
    'routing-is-a-list': outside(account={'workspaceRouting': [{'chatgptAccountId': ACCOUNT}]}),
    'limits-routing': outside(limits={'workspaceRouting': {'chatgptAccountId': ACCOUNT}}),
    'limits-bucket': outside(limits={'rateLimitsByLimitId': {'codex': bucket(limitName=ACCOUNT)}}),
    'limits-window': outside(limits={'rateLimitsByLimitId': {'codex': bucket(
        primary={**WINDOW, 'note': ACCOUNT})}}),
    'limits-nested': outside(limits={'nested': {'accountId': ACCOUNT}}),
    'limits-unknown-field': outside(limits={'note': ACCOUNT}),
    'limits-upsell': outside(limits={'rateLimitUpsell': {'text': 'upgrade ' + ACCOUNT}}),
    'limits-inside-text': outside(limits={'note': 'before ' + ACCOUNT + ' after'}),
    'limits-id-inside-longer-text': outside(limits={'accountId': ACCOUNT + '-more'}),
    'limits-id-in-a-list': outside(limits={'accountId': [ACCOUNT]}),
}


@pytest.mark.parametrize('initialize, account, limits', list(PLACES.values()), ids=list(PLACES))
def test_the_id_anywhere_but_its_two_places_refuses(initialize, account, limits, tmp_path):
    value, runner = make(tmp_path)
    runner.initialize = initialize
    runner.account, runner.limits = account_reply(**account), limits_reply(**limits)
    refused_as_an_echo(value)


@pytest.mark.parametrize('raw', [
    pytest.param(lambda row: row + b'{"method": "account/updated", "params": {}}\n',
                 id='notification'),
    pytest.param(lambda row: row + b'{"id": 4, "result": {}}\n', id='unknown-id'),
    pytest.param(lambda row: row + row.splitlines()[2] + b'\n', id='duplicate-id'),
    pytest.param(lambda row: row.splitlines()[0] + b'\n' + row.splitlines()[2] + b'\n',
                 id='missing-id'),
    pytest.param(lambda row: row.replace(b'"chatgpt"', b'"apiKey"'), id='not-a-subscription'),
])
def test_an_exchange_the_decoder_refuses_admits_nothing_and_reads_as_an_echo(raw, tmp_path):
    value, runner = make(tmp_path)
    runner.raw = raw(runner.transcript())
    assert ACCOUNT.encode() in runner.raw
    refused_as_an_echo(value)


def beside(index, **member):
    """The transcript with ``member`` added to reply ``index`` (1 to 3), beside its ``result``."""
    def edit(transcript):
        rows = [json.loads(line) for line in transcript.splitlines()]
        rows[index - 1].update(member)
        return b'\n'.join(json.dumps(row).encode() for row in rows) + b'\n'
    return edit


@pytest.mark.parametrize('index, member', [
    (2, {'note': ACCOUNT}), (3, {'note': ACCOUNT}), (2, {'chatgptAccountId': ACCOUNT}),
    (3, {'accountId': ACCOUNT})],
    ids=['account-reply', 'limits-reply', 'routing-name-beside-result', 'id-name-beside-result'])
def test_the_id_beside_the_result_of_a_reply_refuses_though_the_decoder_accepts_the_reply(
        index, member, tmp_path):
    value, runner = make(tmp_path)
    runner.raw = beside(index, **member)(runner.transcript())
    assert QUOTA_RPC.decode(runner.raw) == limits_reply()
    refused_as_an_echo(value)
    assert ACCOUNT.encode() not in runner.specs[-1].sensitive_extra


def test_a_refused_exchange_reaches_the_screen_as_a_source_error_without_windows_or_the_id(
        tmp_path):
    value, runner = make(tmp_path)
    runner.raw = runner.transcript() + b'{"method": "account/updated", "params": {}}\n'
    cache = QuotaService()
    collector = QuotaCollector(cache, (quota_plan_for('bound', value),), clock=lambda: AT)
    collector._collect(*collector._work[0])
    row = cache.snapshot('bound', now=AT, max_age=timedelta(minutes=5)).as_dict()
    assert row['state'] == 'error' and row['reason'] == 'source_error' and row['windows'] == []
    assert value._login_echo is True and ACCOUNT not in json.dumps(row)


def test_the_reply_is_judged_as_bytes_so_a_non_ascii_id_outside_its_places_refuses(tmp_path):
    account = 'fake-account-éè-0001-xxxxxx'
    value, runner = make(tmp_path, login(account_id=account))
    runner.ascii = False
    runner.account = account_reply(workspaceRouting={'chatgptAccountId': account})
    runner.limits = limits_reply(accountId=account, note=account)
    assert account.encode() in runner.transcript()
    refused_as_an_echo(value)


@pytest.mark.parametrize('account, limits', [
    ({}, {'note': '\ud800'}), ({'account': {'type': 'chatgpt', 'email': '\ud800'}}, {}),
    ({'workspaceRouting': {'chatgptAccountId': ACCOUNT, 'note': '\ud800'}}, {})],
    ids=['limits-note', 'account-email', 'routing-note'])
def test_a_lone_surrogate_in_the_reply_refuses_and_no_exception_leaves_the_spawn(
        account, limits, tmp_path):
    value, runner = make(tmp_path)
    runner.account, runner.limits = account_reply(**account), limits_reply(**limits)
    exchange(value)
    refused_as_an_echo(value)


# -- the keys: kept by place, and they win ------------------------------------------------------

WHERE = {
    'limits-note': lambda key: {'limits': {'note': key}},
    'limits-id-place': lambda key: {'limits': {'accountId': key}},
    'routing-id-place': lambda key: {'account': {'workspaceRouting': {'chatgptAccountId': key}}},
}


@pytest.mark.parametrize('where', WHERE)
@pytest.mark.parametrize('key', KEY_TEXTS, ids=['id_token', 'access_token', 'refresh_token',
    'login_owner_id', 'issuer', 'last_refresh', 'mcp_access', 'mcp_refresh'])
def test_a_key_of_either_login_file_anywhere_in_the_reply_refuses(where, key, tmp_path):
    value, runner = make(tmp_path)
    changes = WHERE[where](key)
    runner.account = account_reply(**changes.get('account', {}))
    runner.limits = limits_reply(**changes.get('limits', {}))
    refused(value)
    assert key.encode() in runner.specs[-1].sensitive_extra


TOP = login()
COLLISIONS = {
    'mcp-value-equals-id': (None, mcp_login(note=ACCOUNT)),
    'mcp-value-holds-id': (None, mcp_login(note='before-' + ACCOUNT + '-after')),
    'owner-equals-id': (login(login_owner_id=ACCOUNT), None),
    'refresh-token-equals-id': (login(refresh_token=ACCOUNT), None),
    'access-token-holds-id': (login(access_token='before-' + ACCOUNT + '-after'), None),
    'last-refresh-equals-id': ({**TOP, 'last_refresh': ACCOUNT}, None),
    'last-refresh-holds-id': ({**TOP, 'last_refresh': 'stamp-' + ACCOUNT}, None),
    'provenance-holds-id': (login(oauth_provenance={
        'issuer': 'https://' + ACCOUNT + '.invalid', 'client_id': 'fake-client'}), None),
    'id-holds-a-key': (login(account_id='x' + TOKENS['refresh_token'] + 'x'), None),
    'id-holds-a-tool-key': (login(account_id='x' + MCP_ACCESS + 'x'), None),
    'tool-array-value-equals-id': (None, mcp_login(scopes=['read', ACCOUNT])),
    'auth-array-cell-equals-id': ({**TOP, 'audience': [ACCOUNT]}, None),
}


@pytest.mark.parametrize('document, credentials', list(COLLISIONS.values()), ids=list(COLLISIONS))
def test_an_id_that_equals_holds_or_sits_inside_a_key_is_never_admitted(
        document, credentials, tmp_path):
    value, runner = make(tmp_path, document, credentials)
    spelled = (document or login())['tokens']['account_id']
    runner.account = account_reply(workspaceRouting={'chatgptAccountId': spelled})
    runner.limits = limits_reply(accountId=spelled)
    refused(value)
    assert spelled.encode() in runner.specs[-1].sensitive_extra


def home_with(tmp_path, document, credentials=None):
    """A login directory holding the two declared files; the tool file only when it is given."""
    home = tmp_path / 'login'
    home.mkdir()
    (home / 'auth.json').write_text(json.dumps(document))
    if credentials is not None:
        (home / '.credentials.json').write_text(json.dumps(credentials))
    return home


@pytest.mark.parametrize('document', [
    [], 'text', {'tokens': []}, {'tokens': {}}, {'account_id': ACCOUNT},
    login(account_id='short'), login(account_id=7), login(account_id=None),
    {**login(), 'tokens': {**TOKENS, 'account_id': ['x' * 20]}}],
    ids=['list', 'text', 'tokens-list', 'tokens-empty', 'id-outside-tokens', 'id-too-short',
         'id-number', 'id-null', 'id-list'])
def test_a_login_without_a_long_enough_id_cell_admits_nothing(document, tmp_path):
    assert reply_metadata(str(home_with(tmp_path, document, mcp_login())), NAMES) == {}


@pytest.mark.parametrize('document, credentials', list(COLLISIONS.values()), ids=list(COLLISIONS))
def test_the_hook_alone_admits_no_id_that_equals_holds_or_sits_inside_a_key(
        document, credentials, tmp_path):
    home = home_with(tmp_path, document or login(),
                     mcp_login() if credentials is None else credentials)
    assert reply_metadata(str(home), NAMES) == {}


def test_the_id_is_the_one_cell_of_auth_json_and_the_other_files_cell_is_no_account(tmp_path):
    home = home_with(tmp_path, {'tokens': {}}, {'tokens': {'account_id': ACCOUNT}})
    assert reply_metadata(str(home), NAMES) == {}


def test_the_tool_files_own_account_cell_is_a_key_and_the_id_of_auth_json_stays_admitted(tmp_path):
    other = 'other-codex-account-0003'
    home = home_with(tmp_path, login(), {'tokens': {'account_id': other}})
    assert reply_metadata(str(home), NAMES) == {ACCOUNT_FIELD: frozenset((ACCOUNT.encode(),))}


def test_a_missing_or_unreadable_tool_credential_file_leaves_the_id_admitted(tmp_path):
    home = home_with(tmp_path, login())
    expected = {ACCOUNT_FIELD: frozenset((ACCOUNT.encode(),))}
    assert reply_metadata(str(home), NAMES) == expected
    (home / '.credentials.json').write_text('not json')
    assert reply_metadata(str(home), NAMES) == expected
    assert reply_metadata('', NAMES) == {}


UNSEEN = {
    'tool-file-holds-the-id': mcp_login(note=ACCOUNT),
    'tool-file-has-only-the-id': {'synthetic-server|0a1b2c3d': {'note': ACCOUNT}},
    'tool-file-has-other-values': mcp_login(),
}


def refused_reader(monkeypatch, name):
    """The hook's reader answers nothing for ``name``; the leak scan still reads that file."""
    read = login_home.credential_document
    monkeypatch.setattr(login_home, 'credential_document',
                        lambda home, file: None if file == name else read(home, file))


@pytest.mark.parametrize('credentials', list(UNSEEN.values()), ids=list(UNSEEN))
def test_a_file_only_the_scan_can_read_leaves_the_id_a_key(credentials, tmp_path, monkeypatch):
    value, runner = make(tmp_path, None, credentials)
    refused_reader(monkeypatch, '.credentials.json')
    refused(value)
    assert ACCOUNT.encode() in runner.specs[-1].sensitive_extra


@pytest.mark.parametrize('credentials', list(UNSEEN.values()), ids=list(UNSEEN))
def test_the_hook_alone_admits_no_id_while_a_file_only_the_scan_reads_holds_values(
        credentials, tmp_path, monkeypatch):
    home = home_with(tmp_path, login(), credentials)
    refused_reader(monkeypatch, '.credentials.json')
    assert reply_metadata(str(home), NAMES) == {}


# -- what changes during the exchange ------------------------------------------------------------


def test_a_token_refreshed_during_the_exchange_and_echoed_refuses(tmp_path):
    value, runner = make(tmp_path)
    fresh = 'refreshed-access-token-9876543210'
    runner.after = login(access_token=fresh)
    runner.limits = limits_reply(note=fresh)
    refused(value)
    assert fresh.encode() not in runner.specs[-1].sensitive_extra


@pytest.mark.parametrize('returned', [ACCOUNT, 'rotated-codex-account-0002'])
def test_a_rotated_id_may_use_its_places_and_both_samples_stay_in_publication_history(
        returned, tmp_path):
    value, runner = make(tmp_path)
    fresh = 'rotated-codex-account-0002'
    runner.after = login(account_id=fresh)
    runner.account = account_reply(workspaceRouting={'chatgptAccountId': returned})
    runner.limits = limits_reply(accountId=returned)
    outcome = exchange(value)
    assert not outcome.output_contains_env_value and not value._login_echo
    relation = ('synthetic-run', 'synthetic-action', 'synthetic-attempt', 'synthetic-provider')
    value._keep_login_values(relation)
    assert {ACCOUNT.encode(), fresh.encode(), *KEYS} <= set(value._sensitive_values(relation))
    assert value._login_seen == () and value._service is None
    assert value._service_metadata == {} and value._service_values == value._service_protected == ()


def test_a_refreshed_token_containing_the_old_id_revokes_the_old_id_exception(tmp_path):
    value, runner = make(tmp_path)
    runner.after = login(access_token='refreshed-' + ACCOUNT, account_id='rotated-account-00002')
    refused(value)


# -- the rest of the product keeps every protection ----------------------------------------------


def test_a_spawn_that_is_not_the_exact_exchange_scans_for_the_id_and_for_every_key(tmp_path):
    value, runner = make(tmp_path)
    value._workspace.work_root()
    runner.plain = b'Logged in using ChatGPT for ' + ACCOUNT.encode()
    outcome = value._attempt(LOGIN_STATUS_ARGV, 'work', timeout=15)
    assert {ACCOUNT.encode(), *KEYS} <= set(runner.specs[-1].sensitive_extra)
    assert outcome.output_contains_env_value and value._login_echo is True
    assert value._service is None


@pytest.mark.parametrize('argv, stdin', [
    (QUOTA_RPC.argv, QUOTA_RPC.payload + b'\n'), ((*QUOTA_RPC.argv, '--other'), QUOTA_RPC.payload)],
    ids=['other-stdin', 'other-argv'])
def test_the_same_transcript_on_another_spawn_is_no_exchange_and_refuses(argv, stdin, tmp_path):
    value, runner = make(tmp_path)
    value._workspace.work_root()
    outcome = value._attempt(argv, 'work', timeout=15, stdin_bytes=stdin,
                             separate_stderr=True, stdin_completion_id=3)
    assert ACCOUNT.encode() in runner.specs[-1].sensitive_extra
    assert outcome.output_contains_env_value and value._login_echo is True


def test_dispatch_artifacts_and_environment_keep_every_protection(tmp_path):
    value, runner = make(tmp_path)
    runner.limits = limits_reply(note=CONTEXT)
    refused(value)
    secrets = set(value._login_secrets())
    assert {ACCOUNT.encode(), *KEYS} <= secrets
    assert value._echoed_login(b'answer ' + ACCOUNT.encode())
    assert ACCOUNT.encode() in value._sensitive_values(
        ('synthetic-run', 'synthetic-action', 'synthetic-attempt', 'synthetic-provider'))


def test_another_thread_reading_the_login_mid_exchange_gets_it_whole_and_changes_nothing(tmp_path):
    value, runner = make(tmp_path)
    fresh = 'refreshed-access-token-9876543210'
    relation = ('synthetic-run', 'synthetic-action', 'synthetic-attempt', 'synthetic-provider')
    seen, original = {}, runner.run

    def other_thread():
        seen.update(secrets=set(value._login_secrets()),
                    published=set(value._sensitive_values(relation)))

    def run(spec):
        if spec.stdin_bytes is not None:
            (runner.home / 'auth.json').write_text(json.dumps(login(access_token=fresh)))
            seen['before'] = value._service_values
            thread = threading.Thread(target=other_thread)
            thread.start()
            thread.join()
            seen.update(after=value._service_values, scanned=set(spec.sensitive_extra),
                        owner_echoed=value._echoed_login(runner.transcript()))
        return original(spec)
    runner.run = run
    outcome = exchange(value)
    everything = {ACCOUNT.encode(), fresh.encode(), *KEYS - {TOKENS['access_token'].encode()}}
    assert everything <= seen['secrets'] and everything <= seen['published']
    assert seen['before'] and seen['after'] == seen['before']
    assert fresh.encode() not in seen['after']
    assert KEYS <= seen['scanned'] and ACCOUNT.encode() not in seen['scanned']
    assert seen['owner_echoed'] is False
    assert not outcome.output_contains_env_value and not value._login_echo
    assert value._service is None and value._service_metadata == {}
    assert value._service_values == value._service_protected == ()


# -- a failing hook reads as a refusal -------------------------------------------------------------


def test_a_reply_metadata_hook_of_codex_that_fails_leaves_every_login_value_a_key(
        tmp_path, monkeypatch):
    value, runner = make(tmp_path)
    monkeypatch.setattr(value, '_reply_metadata', fails)
    outcome = exchange(value)
    assert {ACCOUNT.encode(), *KEYS} <= set(runner.specs[-1].sensitive_extra)
    assert outcome.output_contains_env_value and value._login_echo
    refused(value)


def test_a_reply_metadata_hook_of_codex_that_fails_once_leaves_a_rotated_id_an_echo(
        tmp_path, monkeypatch):
    value, runner = make(tmp_path)
    fresh = 'rotated-codex-account-0002'
    runner.after = login(account_id=fresh)
    runner.account = account_reply(workspaceRouting={'chatgptAccountId': fresh})
    runner.limits = limits_reply(accountId=fresh)
    monkeypatch.setattr(value, '_reply_metadata',
                        scripted(value._reply_metadata, lambda call: call == 1))
    refused_as_an_echo(value)
    extra = runner.specs[-1].sensitive_extra
    assert {ACCOUNT.encode(), *KEYS} <= set(extra) and fresh.encode() not in extra


def test_a_hook_of_codex_that_fails_after_the_spawn_keeps_a_value_the_spawn_wrote_a_key(
        tmp_path, monkeypatch):
    value, runner = make(tmp_path)
    fresh = 'refreshed-access-token-9876543210'
    runner.after = login(access_token=fresh)
    runner.account = account_reply(workspaceRouting=None)
    runner.limits = limits_reply(accountId=None, note=fresh)
    monkeypatch.setattr(value, '_reply_metadata',
                        scripted(value._reply_metadata, lambda call: call > 1))
    refused_as_an_echo(value)
    assert fresh.encode() not in runner.specs[-1].sensitive_extra


def test_a_masked_reply_hook_of_codex_that_fails_makes_the_reply_an_echo(tmp_path, monkeypatch):
    value, runner = make(tmp_path)
    monkeypatch.setattr(value, '_masked_reply', fails)
    outcome = exchange(value)
    assert not outcome.output_contains_env_value
    assert value._login_echo is True and value._service is None
    refused(value)
