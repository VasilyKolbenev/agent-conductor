"""The environment NAMES that replace a subscription login or reroute its traffic.

A subscription task runs on a login the product copied for it, with the vendor's own CLI. A
variable that carries a token of its own, points the CLI at another credential store or account, or
reroutes the traffic or the certificates it trusts, replaces that login without a word: the run goes
on, on something else, and nothing afterwards can see it. A row that pins the subscription therefore
refuses these names (`provider.ProviderConfig`, and the question in `conduct providers`), and the
relay spec of each harness carries the same names for a pin that was built without a row.

The roster is the one design fact F10 of H5-SUB-R5 lists (names read from the pinned binaries,
Claude Code 2.1.239 and Codex 0.112.0), not a list of every variable a proxy library knows and not
a complete census of what the binaries read: a name that F10 does not list is not refused here.
Names are matched ignoring case on every platform: a Windows variable named `https_proxy` IS
`HTTPS_PROXY`, and elsewhere the lower-case spelling of a proxy variable is the one most tools read
first.

A value module: names and one pure function, nothing read from the machine.
"""
from __future__ import annotations

from collections.abc import Iterable

#: Names both harnesses read: where the API is, which certificates to trust, which proxy to use.
COMMON_ROUTE_ENV = tuple(sorted((
    "ANTHROPIC_BASE_URL", "OPENAI_BASE_URL", "NODE_EXTRA_CA_CERTS",
    "NODE_TLS_REJECT_UNAUTHORIZED", "SSL_CERT_FILE", "SSL_CERT_DIR",
    "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY")))
#: Claude Code: a token, its refresh token, scopes or client; a credential store elsewhere or the
#: Windows credential manager; another OAuth endpoint; an account named from outside.
CLAUDE_ROUTE_ENV = tuple(sorted((
    "CLAUDE_CODE_OAUTH_TOKEN", "CLAUDE_CODE_OAUTH_TOKEN_FILE_DESCRIPTOR",
    "CLAUDE_CODE_OAUTH_REFRESH_TOKEN", "CLAUDE_CODE_OAUTH_SCOPES",
    "CLAUDE_CODE_OAUTH_CLIENT_ID", "CLAUDE_CODE_HOST_CREDS_FILE",
    "CLAUDE_SECURESTORAGE_CONFIG_DIR", "CLAUDE_CODE_FORCE_WINDOWS_CREDMAN",
    "CLAUDE_CODE_CUSTOM_OAUTH_URL", "CLAUDE_CODE_ACCOUNT_UUID", "CLAUDE_CODE_USER_EMAIL",
    "CLAUDE_CODE_ORGANIZATION_UUID")))
#: Codex: the endpoint a refresh token is sent to.
CODEX_ROUTE_ENV = ("CODEX_REFRESH_TOKEN_URL_OVERRIDE",)

#: What a spec of each harness forbids, in its own `forbidden_env`.
CLAUDE_FORBIDDEN_ENV = tuple(sorted({*CLAUDE_ROUTE_ENV, *COMMON_ROUTE_ENV}))
CODEX_FORBIDDEN_ENV = tuple(sorted({*CODEX_ROUTE_ENV, *COMMON_ROUTE_ENV}))
#: What the config door and the wizard refuse beside a subscription: the union, because the door
#: does not branch on which harness a row is for. A name one harness does not read is harmless in
#: the row of another, and a row that forwarded it would gain nothing it could use.
SUBSCRIPTION_ROUTE_ENV = tuple(sorted({*CLAUDE_FORBIDDEN_ENV, *CODEX_FORBIDDEN_ENV}))

_FOLDED = frozenset(name.casefold() for name in SUBSCRIPTION_ROUTE_ENV)


def route_env_named(names: Iterable[str]) -> tuple[str, ...]:
    """Those of `names` that replace a subscription login or reroute its traffic, as written.

    Args:
        names: Environment variable names, as an operator wrote them.
    """
    return tuple(name for name in names if name.casefold() in _FOLDED)
