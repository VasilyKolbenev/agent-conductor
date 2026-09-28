"""A verified Grok metadata reply may repeat account metadata; keys, strangers and collisions refuse."""
import json

import pytest

from conductor.command.adapters.grok_build import GROK_AUTH_RPC, GrokBuildAdapter, grok_pin
from conductor.command.adapters.process import ProcessOutcome
from conductor.command.adapters.quota_connection import NativeQuotaReadError
from conductor.command.quota_plans import quota_plan_for
from conductor.command.quota_service import QuotaService
from conductor.quota_collectors import QuotaCollector
from tests.test_grok_quota import AT, BILLING, NativeRunner

KEY = 'synthetic-access-key-0123456789'
REFRESH = 'synthetic-refresh-token-0123456789'
EMAIL = 'private.person@example.invalid'
TEAM = '11111111-2222-3333-4444-555555555555'
PRINCIPAL = '66666666-7777-8888-9999-000000000000'
ASSET = 'asset-0123456789abcdef'
CONTEXT = 'synthetic-context-value'


def login(**extra):
    return {'https://auth.x.ai::cli': {
        'key': KEY, 'auth_mode': 'web_login', 'create_time': '2026-09-28T00:00:00Z',
        'user_id': PRINCIPAL, 'email': EMAIL, 'profile_image_asset_id': ASSET,
        'principal_type': 'User', 'principal_id': PRINCIPAL, 'team_id': TEAM,
        'refresh_token': REFRESH, **extra}}


def reply(**changes):
    return {'methodId': 'cached_token', 'email': EMAIL, 'teamId': TEAM, 'principalType': 'User',
            'principalId': PRINCIPAL, 'profileImageUrl': 'https://assets.invalid/' + ASSET + '/a.png',
            '_meta': {'currentWorkingDirectory': 'C:/work'}, **changes}


class EchoRunner(NativeRunner):
    """Answers the metadata exchange with a chosen reply, and scans it as the real runner does."""

    def __init__(self, root, env, home):
        super().__init__(root, env)
        self.home, self.info, self.after = home, reply(), None

    def run(self, spec):
        if spec.argv[-1] == '--version':
            return super().run(spec)
        self.specs.append(spec)
        rows = [{'jsonrpc': '2.0', 'id': 1, 'result': {'_meta': {'defaultAuthMethodId': 'cached_token'}}},
                {'jsonrpc': '2.0', 'id': 2, 'result': self.info}]
        if spec.stdin_completion_id == 3:
            rows.append({'jsonrpc': '2.0', 'id': 3, 'result': BILLING})
        output = b'\n'.join(json.dumps(row).encode() for row in rows) + b'\n'
        if self.after is not None:
            (self.home / 'auth.json').write_text(json.dumps(self.after))
        scanned = self.allowed_environment_values(spec.env_allow, overrides=spec.env) + spec.sensitive_extra
        return ProcessOutcome('completed', 0, output, False, spec.output_limit, 0, 'synthetic', 'delivered',
                              output_contains_env_value=any(value in output for value in scanned))


def make(tmp_path, document=None):
    home = tmp_path / 'pinned'
    home.mkdir()
    (home / 'config.toml').write_text('[marketplace]\ndefault_skills_installs_purged = true\n')
    (home / 'auth.json').write_text(json.dumps(login() if document is None else document))
    runner = EchoRunner(tmp_path, {'SELECTED': CONTEXT}, home)
    pin = grok_pin(str(tmp_path / 'native.exe'), ('SELECTED',), auth='subscription', auth_home=str(home))
    counter = [0]

    def ids(kind):
        counter[0] += 1
        return kind + '-' + str(counter[0])
    return GrokBuildAdapter(pin, runner, root=tmp_path, clock=lambda: AT.isoformat(), ids=ids), runner


def refused(value):
    with pytest.raises(NativeQuotaReadError):
        value.quota_connection().read()


def test_a_verified_reply_may_repeat_its_own_account_metadata_and_publishes_none_of_it(tmp_path):
    from tests.test_command_quota_routes import contracts, get, quota_api
    value, runner = make(tmp_path)
    assert value.quota_connection().read() == BILLING
    extra = runner.specs[-1].sensitive_extra
    assert KEY.encode() in extra and REFRESH.encode() in extra
    assert not {EMAIL.encode(), TEAM.encode(), PRINCIPAL.encode(), ASSET.encode()} & set(extra)
    cache = QuotaService()
    collector = QuotaCollector(cache, (quota_plan_for('bound', value),), clock=lambda: AT)
    collector._collect(*collector._work[0])
    api = quota_api(tmp_path, service=cache, providers=contracts('bound'), clock=lambda: AT.isoformat())
    row = json.dumps(get(api).payload['snapshots'][0])
    assert '"remaining_percent": 59' in row
    assert not any(secret in row for secret in (EMAIL, TEAM, PRINCIPAL, ASSET, KEY, REFRESH))


@pytest.mark.parametrize('info', [reply(email=KEY), reply(token=REFRESH),
                                  reply(profileImageUrl='https://assets.invalid/' + ASSET + '?k=' + KEY)])
def test_a_key_anywhere_in_the_reply_refuses(info, tmp_path):
    value, runner = make(tmp_path)
    runner.info = info
    refused(value)


def test_a_key_refreshed_during_the_exchange_and_echoed_refuses(tmp_path):
    value, runner = make(tmp_path)
    fresh = 'refreshed-access-key-9876543210'
    runner.after = login(key=fresh)
    runner.info = reply(note=fresh)
    refused(value)
    assert fresh.encode() not in runner.specs[-1].sensitive_extra


def test_metadata_replaced_during_the_exchange_still_refuses_an_old_value_out_of_place(tmp_path):
    value, runner = make(tmp_path)
    runner.after = login(email='replacement.person@example.invalid')
    runner.info = reply(note=EMAIL)
    refused(value)


def test_an_image_url_cannot_hide_another_metadata_fields_value(tmp_path):
    value, runner = make(tmp_path)
    runner.info = reply(profileImageUrl='https://assets.invalid/' + ASSET + '?email=' + EMAIL)
    refused(value)


@pytest.mark.parametrize('returned_email', [EMAIL, 'replacement.person@example.invalid'])
def test_rotated_metadata_may_use_its_own_field_and_both_samples_stay_in_publication_history(
        returned_email, tmp_path):
    value, runner = make(tmp_path)
    fresh = 'replacement.person@example.invalid'
    runner.after = login(email=fresh)
    runner.info = reply(email=returned_email)
    value._workspace.work_root()
    outcome = value._attempt(GROK_AUTH_RPC.argv, 'work', timeout=15,
        stdin_bytes=GROK_AUTH_RPC.payload, separate_stderr=True, stdin_completion_id=2)
    assert value._login_method_admitted(outcome.output)
    assert not outcome.output_contains_env_value and not value._login_echo
    relation = ('synthetic-run', 'synthetic-action', 'synthetic-attempt', 'synthetic-provider')
    value._keep_login_values(relation)
    assert {EMAIL.encode(), fresh.encode(), KEY.encode(), REFRESH.encode()} <= set(
        value._sensitive_values(relation))
    assert value._login_seen == () and value._service is None
    assert value._service_metadata == {} and value._service_values == value._service_protected == ()


def test_a_refreshed_key_containing_old_metadata_revokes_the_old_metadata_exception(tmp_path):
    value, runner = make(tmp_path)
    runner.after = login(key='refreshed-' + EMAIL, email='replacement.person@example.invalid')
    refused(value)


@pytest.mark.parametrize('info', [reply(contact=EMAIL), reply(_meta={'user': {'email': EMAIL}}),
                                  reply(teamId=PRINCIPAL), reply(email=EMAIL, attachment=[TEAM])])
def test_metadata_outside_its_own_reply_field_refuses(info, tmp_path):
    value, runner = make(tmp_path)
    runner.info = info
    refused(value)


@pytest.mark.parametrize('document', [login(email=KEY), login(team_id='x' + REFRESH + 'x'),
                                      login(session_secret=EMAIL), login(key=PRINCIPAL)])
def test_a_metadata_value_that_collides_with_a_key_is_never_admitted(document, tmp_path):
    value, runner = make(tmp_path, document)
    runner.info = reply(email=document['https://auth.x.ai::cli']['email'],
                        teamId=document['https://auth.x.ai::cli']['team_id'])
    refused(value)


def test_a_reply_the_exchange_decoder_refuses_admits_nothing(tmp_path):
    value, runner = make(tmp_path)
    runner.info = reply(methodId='xai.api_key')
    refused(value)
    assert value._login_echo


def test_dispatch_artifacts_and_environment_keep_every_protection(tmp_path):
    value, runner = make(tmp_path)
    runner.info = reply(note=CONTEXT)
    refused(value)
    secrets = set(value._login_secrets())
    assert {KEY, REFRESH, EMAIL, TEAM, PRINCIPAL, ASSET} <= {item.decode() for item in secrets}
    assert value._echoed_login(b'answer ' + EMAIL.encode())
