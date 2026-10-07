"""Native metadata reads on dispatch's existing login, workspace and spawn road.

The provider supplies the finite protocol and account-method test. No task,
login, logout, token refresh command, API key or model invocation is invented.
Raw metadata exists only until the provider's strict quota parser consumes it.
"""
from __future__ import annotations

from dataclasses import dataclass

from .harness_workspace import WorkspaceBusy
from .jsonl_completion import decode_line
from .quota_connection import (NativeQuotaDeferred, NativeQuotaReader, NativeQuotaReadError,
                               NativeQuotaUnconfirmed)


@dataclass(frozen=True)
class SubscriptionRpc:
    argv: tuple[str, ...]
    payload: bytes
    response_ids: tuple[int, ...]
    account_path: tuple[str, ...]
    account_method: str
    notifications: tuple[str, ...] = ()
    #: As on ControlRpc: names this protocol's own spawn runs without. None here.
    unset_env: tuple[str, ...] = ()

    @property
    def completion_id(self):
        return self.response_ids[-1]

    def decode(self, output: bytes) -> dict:
        seen = {}
        try:
            for line in output.splitlines():
                row = decode_line(line)
                if (type(row.get('method')) is str and row['method'] in self.notifications
                        and 'id' not in row and 'result' not in row and 'error' not in row
                        and type(row.get('params')) is dict):
                    continue
                identity = row.get('id')
                if type(identity) is not int or identity not in self.response_ids or identity in seen:
                    raise ValueError('unexpected native message')
                if 'method' in row or ('result' in row) == ('error' in row):
                    raise ValueError('ambiguous native response')
                seen[identity] = row
            if tuple(sorted(seen)) != self.response_ids:
                raise ValueError('incomplete native transcript')
            if any(type(seen[key].get('result')) is not dict for key in self.response_ids[:-1]):
                raise NativeQuotaReadError()
            account = seen[self.response_ids[-2]]['result']
            for key in self.account_path:
                account = account.get(key) if type(account) is dict else None
            if account != self.account_method:
                raise NativeQuotaReadError('not_authenticated')
            if type(seen[self.response_ids[-1]].get('result')) is not dict:
                raise NativeQuotaReadError()
            return seen[self.response_ids[-1]]['result']
        except NativeQuotaReadError:
            raise
        except (ValueError, UnicodeError, RecursionError):
            raise NativeQuotaReadError('malformed_payload') from None


@dataclass(frozen=True)
class ControlRpc:
    """Finite native control messages; no user turn or model invocation."""
    argv: tuple[str, ...]
    payload: bytes
    request_ids: tuple[str, ...]
    completion_id: None = None
    #: Environment names this ONE control spawn runs without -- dropped from the forced
    #: switches and from the operator allowlist alike, so neither can put them back. The
    #: version preflight of the same read and every task spawn keep the full profile.
    unset_env: tuple[str, ...] = ()

    def decode(self, output: bytes) -> dict:
        seen = {}
        try:
            for line in output.splitlines():
                row = decode_line(line)
                if row.get('type') != 'control_response' or type(row.get('response')) is not dict:
                    raise ValueError('unexpected native message')
                response = row['response']
                identity = response.get('request_id')
                if type(identity) is not str or identity not in self.request_ids or identity in seen:
                    raise ValueError('unexpected native response')
                if (response.get('subtype') != 'success' or 'error' in response
                        or type(response.get('response')) is not dict):
                    raise NativeQuotaReadError()
                seen[identity] = response['response']
            if set(seen) != set(self.request_ids):
                raise ValueError('incomplete native transcript')
            return {'account': seen[self.request_ids[0]].get('account'),
                    'usage': seen[self.request_ids[-1]]}
        except NativeQuotaReadError:
            raise
        except (ValueError, UnicodeError, RecursionError):
            raise NativeQuotaReadError('malformed_payload') from None


def _clean(adapter, outcome, *, input_required=False):
    if (outcome.status != 'completed' or outcome.exit_code != 0 or outcome.output_truncated
            or outcome.output_contains_env_value or adapter._login_echo
            or adapter._retained or adapter._login_residue
            or input_required and outcome.stdin_state != 'delivered'):
        raise NativeQuotaReadError()


#: A quota read waits this long for the root's turn. A running attempt holds the
#: root for its whole doer -> checker -> receipt interval; a read that cannot have
#: it now defers its update instead of queueing the collector's stop.
ROOT_WAIT_SECONDS = 5.0


class _Turn:
    """The root's turn for one read, bounded: a turn that does not come defers the update."""

    def __init__(self, adapter):
        self._turn = adapter._workspace.owned(wait=ROOT_WAIT_SECONDS)

    def __enter__(self):
        try:
            return self._turn.__enter__()
        except WorkspaceBusy:
            raise NativeQuotaDeferred() from None

    def __exit__(self, kind, error, trace):
        return self._turn.__exit__(kind, error, trace)


def _read(adapter, protocol, project):
    with _Turn(adapter):
        adapter._begin_road()
        try:
            home = adapter._signed_in_road()
            if not home or adapter._login_home_grants(home):
                raise NativeQuotaReadError('not_supported')
            if adapter._workspace.sweep_homes():
                raise NativeQuotaReadError()
            adapter._workspace.work_root()
            version = adapter._attempt(adapter.profile.version_argv, 'work', timeout=10)
            _clean(adapter, version)
            if not adapter._version_matches(version.output):
                raise NativeQuotaReadError('not_supported')
            outcome = adapter._attempt(protocol.argv, 'work', timeout=15,
                stdin_bytes=protocol.payload, separate_stderr=True,
                stdin_completion_id=protocol.completion_id,
                **({'unset_env': protocol.unset_env} if protocol.unset_env else {}))
            _clean(adapter, outcome, input_required=True)
            payload = protocol.decode(outcome.output)
            return payload if project is None else project(adapter, payload)
        finally:
            adapter._forget_login_sample()


def native_subscription_connection(adapter, policy, protocol, *, project=None):
    version = adapter.profile.reviewed_version
    if not adapter._signed_in_road():
        return NativeQuotaReader(policy, version, reason='not_supported')
    def read():
        try:
            return _read(adapter, protocol, project)
        except (NativeQuotaReadError, NativeQuotaDeferred, NativeQuotaUnconfirmed):
            raise
        except Exception:
            raise NativeQuotaReadError() from None
    return NativeQuotaReader(policy, version, read)
