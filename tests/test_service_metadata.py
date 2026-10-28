"""The metadata circuit lives in ``ServiceMetadata``, and a failing hook or stranger cannot open it.

The Grok adapter reaches the mixin first. The mixin narrows two things only, both read inside one
spawn's attempt: the values the runner scans that spawn for (``_spawn_secrets``) and the judgement
of its output (``_echoed_login``). What publishes reads ``_login_secrets``, which stays whole. Under
the login lease an exception poisons the login until the OS restarts, so a hook that fails must
read as a refusal, never as an exception.
"""
import json
import threading

import pytest

from conductor.command.adapters.grok_build import GROK_AUTH_RPC, GrokBuildAdapter
from conductor.command.adapters.headless_login import LoginRoad
from conductor.command.adapters.service_metadata import ServiceMetadata
from tests.test_grok_service_echo import (
    ASSET, EMAIL, KEY, PRINCIPAL, REFRESH, TEAM, login, make, refused, reply)

CIRCUIT = ('_attempt', '_spawn_secrets', '_echoed_login')
WHOLE = ('_login_secrets', '_remember_login_values')
HOOKS = ('_service_for', '_reply_metadata', '_masked_reply')
KEYS = {item.encode() for item in (KEY, REFRESH)}
METADATA = {item.encode() for item in (EMAIL, TEAM, PRINCIPAL, ASSET)}


def owner(kind, name):
    """The class in ``kind``'s resolution order that supplies ``name``."""
    return next((base for base in kind.__mro__ if name in vars(base)), None)


def exchange(value):
    """One auth/info exchange through ``_attempt``, as a quota read puts it; a raise fails."""
    value._workspace.work_root()
    return value._attempt(GROK_AUTH_RPC.argv, 'work', timeout=15,
        stdin_bytes=GROK_AUTH_RPC.payload, separate_stderr=True, stdin_completion_id=2)


def fails(*args, **kwargs):
    raise RuntimeError('a hook that fails')


def verified_transcript():
    """A reply that repeats the account's own metadata in its own fields, and nothing else."""
    initialize = {'_meta': {'defaultAuthMethodId': 'cached_token'}}
    rows = ({'jsonrpc': '2.0', 'id': 1, 'result': initialize},
            {'jsonrpc': '2.0', 'id': 2, 'result': reply()})
    return b'\n'.join(json.dumps(row).encode() for row in rows) + b'\n'


def test_the_mixin_is_the_first_base_so_nothing_of_the_login_road_stands_ahead_of_it():
    assert GrokBuildAdapter.__bases__[0] is ServiceMetadata


@pytest.mark.parametrize('name', CIRCUIT)
def test_the_three_circuit_methods_of_grok_resolve_into_the_mixin(name):
    assert owner(GrokBuildAdapter, name) is ServiceMetadata


@pytest.mark.parametrize('name', WHOLE)
def test_what_publishes_and_remembers_the_login_stays_the_login_roads_in_grok(name):
    assert owner(GrokBuildAdapter, name) is LoginRoad


@pytest.mark.parametrize('name', HOOKS)
def test_the_three_hooks_of_grok_are_its_own(name):
    assert owner(GrokBuildAdapter, name) is GrokBuildAdapter


def test_the_hooks_of_the_mixin_alone_admit_nothing():
    base = ServiceMetadata()
    assert base._service_for(GROK_AUTH_RPC.argv, GROK_AUTH_RPC.payload) is None
    assert base._reply_metadata() == {}
    assert base._masked_reply(b'output', GROK_AUTH_RPC, {}) == b'output'


def test_a_road_that_narrows_nothing_scans_a_spawn_for_the_whole_login_set():
    road = LoginRoad()
    road._login_secrets = lambda: (b'first-login-value', b'second-login-value')
    assert road._spawn_secrets() == (b'first-login-value', b'second-login-value')


def test_the_runner_is_told_the_spawn_role_values_and_not_the_login_set(tmp_path, monkeypatch):
    value, runner = make(tmp_path)
    monkeypatch.setattr(value, '_login_secrets', lambda: (b'whole-login-value-0123',))
    monkeypatch.setattr(value, '_spawn_secrets', lambda: (b'spawn-scan-value-0123',))
    exchange(value)
    assert runner.specs[-1].sensitive_extra == (b'spawn-scan-value-0123',)


def test_a_reply_metadata_hook_that_fails_leaves_every_login_value_a_key(tmp_path, monkeypatch):
    value, runner = make(tmp_path)
    monkeypatch.setattr(value, '_reply_metadata', fails)
    outcome = exchange(value)
    assert {*KEYS, *METADATA} <= set(runner.specs[-1].sensitive_extra)
    assert outcome.output_contains_env_value and value._login_echo
    assert value._service is None and value._service_values == ()
    refused(value)


def test_a_masked_reply_hook_that_fails_makes_the_reply_an_echo(tmp_path, monkeypatch):
    value, runner = make(tmp_path)
    monkeypatch.setattr(value, '_masked_reply', fails)
    outcome = exchange(value)
    assert not outcome.output_contains_env_value
    assert value._login_echo is True
    assert value._service is None and value._service_values == ()
    refused(value)


@pytest.mark.parametrize('info', [reply(note='\ud800'), reply(email='\ud800'),
                                  reply(profileImageUrl='https://assets.invalid/\ud800')])
def test_a_lone_surrogate_in_a_reply_refuses_and_no_exception_leaves_the_spawn(info, tmp_path):
    value, runner = make(tmp_path)
    runner.info = info
    exchange(value)
    assert value._login_echo is True
    refused(value)


class Host:
    """What a mixin needs of the class it is mixed into, answered by a spawn that is signed in."""

    def _signed_in_road(self):
        return 'home'

    def _spawn_secrets(self):
        return ()

    def _echoed_login(self, output):
        return False


class Probe(ServiceMetadata, Host):
    """A provider that admits a chosen metadata and records what each judgement is told to mask.

    Its mask removes only the ``blanked`` values, wherever they stand, which is enough to see
    whether a value that is still in the masked reply is read as an echo.
    """

    def __init__(self, metadata, blanked=()):
        self.metadata, self.blanked, self.judged = metadata, blanked, []
        self._service = GROK_AUTH_RPC
        self._service_metadata, self._service_values, self._service_protected = {}, (), ()

    def _reply_metadata(self):
        return self.metadata

    def _masked_reply(self, output, service, own_fields):
        self.judged.append(own_fields)
        for item in self.blanked:
            output = output.replace(item, b'')
        return output


ID = PRINCIPAL.encode()
HOLDER = b'asset-' + ID + b'-0123'
OTHER = b'asset-another-0123456789'
SHARED = b'shared-metadata-0123456789'


def judged(probe, output=b'output'):
    """The own fields each judgement of one verdict was given, as a list in no fixed order."""
    probe._echoed_login(output)
    return probe.judged


def holding(*samples):
    return frozenset(samples)


def test_a_value_is_judged_at_the_fields_whose_samples_equal_or_hold_it_and_those_are_masked():
    probe = Probe({'principal_id': holding(ID), 'image': holding(HOLDER)})
    told = judged(probe)
    assert len(told) == 2
    assert {'principal_id': holding(ID), 'image': holding(HOLDER)} in told
    assert {'image': holding(HOLDER)} in told


def test_a_field_gives_the_judgement_only_the_samples_that_hold_the_value():
    probe = Probe({'image': holding(HOLDER, OTHER), 'principal_id': holding(ID)})
    told = judged(probe)
    assert len(told) == 3
    assert {'principal_id': holding(ID), 'image': holding(HOLDER)} in told
    assert {'image': holding(HOLDER)} in told
    assert {'image': holding(OTHER)} in told


def test_a_sample_that_stands_in_two_fields_is_a_place_in_both():
    probe = Probe({'first': holding(SHARED), 'second': holding(SHARED)})
    assert judged(probe) == [{'first': holding(SHARED), 'second': holding(SHARED)}]


def test_a_sample_that_only_sits_inside_the_value_is_no_place_for_it():
    probe = Probe({'principal_id': holding(ID), 'image': holding(HOLDER)})
    told = judged(probe)
    assert {'principal_id': holding(ID)} not in told
    assert {'image': holding(HOLDER)} in told


def test_a_value_the_masking_of_its_places_leaves_standing_is_an_echo():
    metadata = {'principal_id': holding(ID), 'image': holding(HOLDER)}
    assert Probe(metadata, blanked=(HOLDER, ID))._echoed_login(HOLDER + b' ' + ID) is False
    assert Probe(metadata, blanked=(HOLDER,))._echoed_login(HOLDER + b' ' + ID) is True
    assert Probe(metadata)._echoed_login(HOLDER) is True


def test_another_thread_reading_the_login_mid_exchange_gets_it_whole_and_changes_nothing(tmp_path):
    value, runner = make(tmp_path)
    fresh = 'refreshed-access-key-9876543210'
    relation = ('synthetic-run', 'synthetic-action', 'synthetic-attempt', 'synthetic-provider')
    outside = {}
    original = runner.run

    def other_thread():
        outside.update(secrets=set(value._login_secrets()),
                       published=set(value._sensitive_values(relation)))

    def run(spec):
        if spec.argv[-1] != '--version':
            (runner.home / 'auth.json').write_text(json.dumps(login(key=fresh)))
            outside['before'] = value._service_values
            thread = threading.Thread(target=other_thread)
            thread.start()
            thread.join()
            outside.update(after=value._service_values, scanned=set(spec.sensitive_extra),
                           owner_echoed=value._echoed_login(verified_transcript()))
        return original(spec)
    runner.run = run
    outcome = exchange(value)
    everything = {REFRESH.encode(), fresh.encode(), *METADATA}
    assert everything <= outside['secrets'] and everything <= outside['published']
    assert outside['before'] and outside['after'] == outside['before']
    assert fresh.encode() not in outside['after']
    assert KEYS <= outside['scanned'] and not METADATA & outside['scanned']
    assert outside['owner_echoed'] is False
    assert not outcome.output_contains_env_value and not value._login_echo
    assert value._service is None and value._service_metadata == {}
    assert value._service_values == value._service_protected == ()


# -- a hook that fails ends the exchange for the circuit: the rest of the spawn is judged whole

ROTATED = 'replacement.person@example.invalid'


def scripted(hook, failing):
    """``hook``, raising on the calls (counted from 1) whose number ``failing`` accepts."""
    calls = []

    def run(*args, **kwargs):
        calls.append(None)
        if failing(len(calls)):
            raise RuntimeError('a hook that fails')
        return hook(*args, **kwargs)
    return run


def test_a_reply_metadata_hook_that_fails_once_leaves_the_rest_of_the_spawn_judged_whole(
        tmp_path, monkeypatch):
    value, runner = make(tmp_path)
    runner.after = login(email=ROTATED)
    runner.info = {'methodId': 'cached_token', 'email': ROTATED}
    monkeypatch.setattr(value, '_reply_metadata',
                        scripted(value._reply_metadata, lambda call: call == 1))
    refused(value)
    extra = runner.specs[-1].sensitive_extra
    assert {*KEYS, *METADATA} <= set(extra) and ROTATED.encode() not in extra
    assert value._login_echo is True


def test_a_hook_that_fails_after_the_spawn_keeps_a_value_the_spawn_rotated_away_a_key(
        tmp_path, monkeypatch):
    value, runner = make(tmp_path)
    runner.after = login(email=ROTATED)
    runner.info = {'methodId': 'cached_token', 'note': EMAIL}
    monkeypatch.setattr(value, '_reply_metadata',
                        scripted(value._reply_metadata, lambda call: call > 1))
    refused(value)
    assert EMAIL.encode() not in runner.specs[-1].sensitive_extra
    assert value._login_echo is True


def test_a_hook_that_fails_after_the_spawn_keeps_a_value_the_spawn_wrote_a_key(
        tmp_path, monkeypatch):
    value, runner = make(tmp_path)
    fresh = 'refreshed-access-key-9876543210'
    runner.after = login(key=fresh)
    runner.info = {'methodId': 'cached_token', 'note': fresh}
    monkeypatch.setattr(value, '_reply_metadata',
                        scripted(value._reply_metadata, lambda call: call > 1))
    refused(value)
    assert fresh.encode() not in runner.specs[-1].sensitive_extra
    assert value._login_echo is True


def test_a_hook_that_fails_after_the_spawn_judges_a_reply_with_no_login_value_clean(
        tmp_path, monkeypatch):
    value, runner = make(tmp_path)
    runner.info = {'methodId': 'cached_token'}
    monkeypatch.setattr(value, '_reply_metadata',
                        scripted(value._reply_metadata, lambda call: call > 1))
    outcome = exchange(value)
    assert not outcome.output_contains_env_value
    assert value._login_echo is False and value._service is None
