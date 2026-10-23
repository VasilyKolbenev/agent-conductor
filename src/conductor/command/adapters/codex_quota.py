"""Codex's quota read: the policy, the app-server exchange, and the mapping of its fields.

Moved out of `codex_cli`, which stands at the 800-line cap, with no change of what is read or
asked. The exchange is the one the subscription quota reader runs against the app-server of the
CLI (`subscription_quota.native_subscription_connection`): initialise, read the account, read the
rate limits. It carries `AUTH_STORE_ARGV` like every Codex spawn that reads the login
(`codex_relay`).
"""
from __future__ import annotations

from .codex_relay import AUTH_STORE_ARGV
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
    b'{"clientInfo":{"name":"december_command","version":"1.0"}}}\n'
    b'{"method":"initialized","params":{}}\n'
    b'{"id":2,"method":"account/read","params":{"refreshToken":false}}\n'
    b'{"id":3,"method":"account/rateLimits/read"}\n',
    (1, 2, 3), ("account", "type"), "chatgpt")
