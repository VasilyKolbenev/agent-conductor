"""Codex's quota read: the policy, the app-server exchange, and the mapping of its fields.

Moved out of `codex_cli`, which stands at the 800-line cap. The exchange is the one the
subscription quota reader runs against the app-server of the
CLI (`subscription_quota.native_subscription_connection`): initialise, read the account, read the
rate limits. It carries `AUTH_STORE_ARGV` like every Codex spawn that reads the login
(`codex_relay`). Initialize opts out of the two ordinary notifications measured in P6 on
0.164.0. The decoder still refuses any notification that reaches this finite reply exchange.

The reply repeats ONE value of the login files, the account id (`auth.json` `tokens.account_id`):
measured on 0.164.0 as the single match of the leak scan, and by the vendor's own source (commit
`6aaac69`, `app-server-protocol/src/protocol/v2`) at exactly two places -- `accountId` of the
rate-limits reply (`account.rs`, id 3) and `workspaceRouting.chatgptAccountId` of the account
reply (`account.rs`, `workspace_routing.rs`, id 2). The three functions below are what
`service_metadata.ServiceMetadata` takes from this provider: which spawn is the exchange, which
login value its reply may repeat, and the reply with that value blanked in those two places. A
key of either login file is never admitted, wherever it stands and whatever it equals or holds.
"""
from __future__ import annotations

import json

from . import login_home
from .codex_relay import AUTH_STORE_ARGV, CREDENTIAL
from .quota_connection import NativeQuotaReadError
from .quota_contracts import QuotaPolicy, bucket_windows
from .subscription_quota import SubscriptionRpc


# The provider owns every native field; the helper only walks keyed windows.
def _native_quota(payload):
    return bucket_windows(
        payload, map_field="rateLimitsByLimitId", legacy_field="rateLimits",
        default_limit="codex", limit_field="limitId", window_fields=("primary", "secondary"),
        used_field="usedPercent", reset_field="resetsAt",
        duration_field="windowDurationMins").bound_to(QUOTA_POLICY)


QUOTA_POLICY = QuotaPolicy("openai", "codex-account-read", "codex-app-server",
                           "quota", "unix", _native_quota)

QUOTA_RPC = SubscriptionRpc(
    (*AUTH_STORE_ARGV, "app-server"),
    b'{"id":1,"method":"initialize","params":'
    b'{"clientInfo":{"name":"december_command","version":"1.0"},'
    b'"capabilities":{"optOutNotificationMethods":'
    b'["account/updated","remoteControl/status/changed"]}}}\n'
    b'{"method":"initialized","params":{}}\n'
    b'{"id":2,"method":"account/read","params":{"refreshToken":false}}\n'
    b'{"id":3,"method":"account/rateLimits/read"}\n',
    (1, 2, 3), ("account", "type"), "chatgpt")

#: The login field the reply may repeat: where `tokens.account_id` stands in `auth.json`.
ACCOUNT_FIELD = "tokens.account_id"
_ACCOUNT_PATH = ("tokens", "account_id")
#: The ids of the two replies of `QUOTA_RPC.payload` that may carry it.
_ACCOUNT_READ_ID = 2
_LIMITS_READ_ID = 3
#: The leak scan's own floor for a login value (`login_home.credential_values`).
_SECRET_FLOOR = 12


def service_for(argv, stdin_bytes: bytes | None) -> SubscriptionRpc | None:
    """The quota exchange, known by its exact argv AND its exact stdin; any other spawn is none."""
    return QUOTA_RPC if argv == QUOTA_RPC.argv and stdin_bytes == QUOTA_RPC.payload else None


def _cells(value: object, path: tuple = ()):
    """Every string leaf of a JSON value with the place it stands at; object names are no cells."""
    pending = [(path, value)]
    while pending:
        location, item = pending.pop()
        if isinstance(item, str):
            yield location, item
        elif isinstance(item, dict):
            pending.extend(((*location, name), child)
                           for name, child in reversed(tuple(item.items())))
        elif isinstance(item, list):
            pending.extend(((*location, index), item[index])
                           for index in range(len(item) - 1, -1, -1))


def reply_metadata(home: str, names: tuple[str, ...]) -> dict[str, frozenset[bytes]]:
    """The one login value a verified reply may repeat: ``auth.json`` ``tokens.account_id``.

    Every string cell of the declared login files from the scan's floor up is a key, BY PLACE,
    except that one cell of ``auth.json``. The id is admitted only when it is itself that long
    and equals, holds or sits inside no key (a token, the other file's value, the owner id, the
    refresh stamp): the key wins. File by file:

    - an ``auth.json`` that is no document, or has no ``tokens.account_id`` cell of the
      floor's length or more, admits nothing;
    - a file the leak scan reads and this reader does not admits nothing when the scan finds
      in it a value that is none of this function's keys (in ``auth.json``, the id's own cell
      is not counted): the scan reads these files by its own road, and a value only it sees is
      a key this function never got to compare;
    - a file that neither reads (absent, or no JSON) changes nothing.
    """
    if not home:
        return {}
    keys: list[bytes] = []
    account = None
    for name in names:
        for path, text in _cells(login_home.credential_document(home, name)):
            if name == CREDENTIAL and path == _ACCOUNT_PATH:
                account = text
            elif len(text) >= _SECRET_FLOOR:
                keys.append(text.encode("utf-8"))
    if account is None or len(account) < _SECRET_FLOOR:
        return {}
    raw = account.encode("utf-8")
    if any(raw in key or key in raw for key in keys):
        return {}
    for name in names:
        # Only the id's own cell of `auth.json` is a scanned value that is no key here.
        known = {*keys, raw} if name == CREDENTIAL else {*keys}
        if not set(login_home.credential_values(home, (name,))) <= known:
            return {}
    return {ACCOUNT_FIELD: frozenset((raw,))}


def masked_reply(output: bytes, service: SubscriptionRpc,
                 own_fields: dict[str, frozenset[bytes]]) -> bytes:
    """The output with the admitted account id blanked in its two own places -- if verified.

    A transcript the exchange's own decoder refuses is returned whole, so nothing in it is
    admitted. Only ``accountId`` of the rate-limits reply and ``chatgptAccountId`` of an
    account reply's ``workspaceRouting`` OBJECT are blanked, and only when they equal the id;
    the id anywhere else (another reply, another field, nested deeper, inside a longer text)
    stays in the output. The rows this edits are written back as they are decoded
    (``ensure_ascii=False``), so a value outside its places is still found as raw bytes; a
    row that cannot be written back, a lone surrogate, fails and the caller reads that as an echo.
    """
    try:
        service.decode(output)
    except NativeQuotaReadError:
        return output
    known = own_fields.get(ACCOUNT_FIELD, frozenset())
    rows = []
    for line in output.splitlines():
        row = json.loads(line)
        result = row.get("result")
        if type(result) is dict and row.get("id") == _LIMITS_READ_ID:
            result = _blanked(result, "accountId", known)
        elif type(result) is dict and row.get("id") == _ACCOUNT_READ_ID:
            routing = result.get("workspaceRouting")
            if type(routing) is dict:
                result = {**result, "workspaceRouting": _blanked(
                    routing, "chatgptAccountId", known)}
        else:
            rows.append(line)
            continue
        rows.append(json.dumps({**row, "result": result}, ensure_ascii=False).encode("utf-8"))
    return b"\n".join(rows)


def _blanked(holder: dict, name: str, known: frozenset[bytes]) -> dict:
    """``holder`` with ``name`` blanked when it is a text equal to an admitted id."""
    value = holder.get(name)
    if type(value) is str and value.encode("utf-8") in known:
        return {**holder, name: ""}
    return holder
