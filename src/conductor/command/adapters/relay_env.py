"""The environment NAMES that replace a subscription login or reroute its traffic.

A subscription task runs on a login the product copied for it, with the vendor's own CLI. A
variable that carries a token of its own, points the CLI at another credential store or account, or
reroutes the traffic or the certificates it trusts, replaces that login without a word: the run goes
on, on something else, and nothing afterwards can see it. A row that pins the subscription therefore
refuses these names (`provider.ProviderConfig`, and the question in `conduct providers`), and the
relay spec of each harness carries the same names for a pin that was built without a row.

The roster comes from F10 of H5-SUB-R5 and the Codex 0.164.0 source/binary census P5 of
H5-CODEX-COMPAT A. It is not a list of every variable a proxy library might read.
Names are matched ignoring case on every platform: a Windows variable named `https_proxy` IS
`HTTPS_PROXY`, and elsewhere the lower-case spelling of a proxy variable is the one most tools read
first.

A value module: names and pure decisions, nothing read from the machine.
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
    "CLAUDE_CODE_ORGANIZATION_UUID", "CLAUDE_CODE_HOST_AUTH_ENV_VAR",
    "CLAUDE_CODE_HFI_BEARER_TOKEN", "CLAUDE_CODE_PROVIDER_MANAGED_BY_HOST",
    "CLAUDE_CODE_HOST_HTTP_PROXY_PORT", "CLAUDE_CODE_HOST_SOCKS_PROXY_PORT",
    "ANTHROPIC_UNIX_SOCKET", "ANTHROPIC_CUSTOM_HEADERS", "ANTHROPIC_IDENTITY_TOKEN",
    "ANTHROPIC_IDENTITY_TOKEN_FILE", "ANTHROPIC_FOUNDRY_API_KEY", "ANTHROPIC_FOUNDRY_AUTH_TOKEN",
    "ANTHROPIC_AWS_API_KEY")))
#: Codex: OAuth/store endpoints, certificates, remote execution, identity and raw trace routes.
CODEX_ROUTE_ENV = tuple(sorted((
    "CODEX_REFRESH_TOKEN_URL_OVERRIDE", "CODEX_REVOKE_TOKEN_URL_OVERRIDE",
    "CODEX_AUTHAPI_BASE_URL", "CODEX_APP_SERVER_LOGIN_CLIENT_ID", "CODEX_SQLITE_HOME",
    "CODEX_CA_CERTIFICATE", "CODEX_EXEC_SERVER_URL", "CODEX_EXEC_SERVER_NOISE_REGISTRY_URL",
    "CODEX_EXEC_SERVER_NOISE_ENVIRONMENT_ID", "CODEX_EXEC_SERVER_NOISE_AUTH_TOKEN",
    "CODEX_EXEC_SERVER_NOISE_CHATGPT_ACCOUNT_ID", "CODEX_AGENT_IDENTITY_AUTHAPI_BASE_URL",
    "CODEX_AGENT_IDENTITY_JWKS_BASE_URL", "CODEX_APP_SERVER_LOGIN_ISSUER", "CODEX_CONNECTORS_TOKEN",
    "CODEX_ROLLOUT_TRACE_ROOT", "OPENAI_ORGANIZATION", "OPENAI_PROJECT",
    "CODEX_INTERNAL_ORIGINATOR_OVERRIDE", "CODEX_OSS_BASE_URL", "CODEX_OSS_PORT")))

#: Alternate credentials must be refused by the transport too, including a direct pin that did
#: not pass through ProviderConfig. A login-status sentence is not an environment-source guard.
CODEX_CREDENTIAL_ENV = tuple(sorted((
    "OPENAI_API_KEY", "CODEX_API_KEY", "CODEX_ACCESS_TOKEN", "OPENAI_FEDERATION_RULE_ID",
    "OPENAI_IDENTITY_TOKEN_FILE", "OPENAI_WORKLOAD_IDENTITY_CONTEXT",
    "CODEX_GUARDIAN_DECISIONS_API_KEY")))

#: This code-owned pair enters the profile digest, but only the access-only child receives it.
#: It constrains the refresh route; it does not promise that refresh can never be attempted.
CODEX_ACCESS_ONLY_ENV = (("CODEX_REFRESH_TOKEN_URL_OVERRIDE", "http://127.0.0.1:9/oauth/token"),)

#: Grok 1.0.5 AuthStore scope and compatibility switches (H5-GROK-DIAGNOSE, addendum 1).
GROK_SCOPE = "https://auth.x.ai::b1a00492-073a-47ea-816f-4c329264a828"
GROK_COMPAT_ENV = (
    ("GROK_CLAUDE_SKILLS_ENABLED", "false"), ("GROK_CLAUDE_RULES_ENABLED", "false"),
    ("GROK_CLAUDE_AGENTS_ENABLED", "false"), ("GROK_CLAUDE_MCPS_ENABLED", "false"),
    ("GROK_CLAUDE_HOOKS_ENABLED", "false"), ("GROK_CLAUDE_SESSIONS_ENABLED", "false"),
    ("GROK_CURSOR_SKILLS_ENABLED", "false"), ("GROK_CURSOR_RULES_ENABLED", "false"),
    ("GROK_CURSOR_AGENTS_ENABLED", "false"), ("GROK_CURSOR_MCPS_ENABLED", "false"),
    ("GROK_CURSOR_HOOKS_ENABLED", "false"), ("GROK_CURSOR_SESSIONS_ENABLED", "false"),
)
GROK_ROUTE_ENV = (
    "XAI_API_KEY", "GROK_CLI_CHAT_PROXY_BASE_URL", "GROK_AUTH_PROVIDER_COMMAND",
    "GROK_OIDC_ISSUER", "GROK_OIDC_CLIENT_ID", "GROK_DEPLOYMENT_KEY")
GROK_ROUTE_PREFIXES = ("GROK_TRACE_UPLOAD_", "GROK_INTERNAL_OTLP_")
GROK_FORBIDDEN_ENV = tuple(sorted({*GROK_ROUTE_ENV, *COMMON_ROUTE_ENV,
    *(name for name, _value in GROK_COMPAT_ENV),
    "GROK_AUTH", "GROK_AUTH_PATH", "GROK_AUTH_EARLY_INVALIDATION_SECS",
    "GROK_AUTH_TOKEN_TTL", "GROK_AUTH_PROVIDER_LABEL", "GROK_LOCAL_AUTH",
    "GROK_OAUTH2_ISSUER", "GROK_OAUTH2_CLIENT_ID", "GROK_OAUTH2_PRINCIPAL_TYPE",
    "GROK_OAUTH2_PRINCIPAL_ID", "GROK_OAUTH2_SCOPES", "GROK_OAUTH2_REFERRER",
    "GROK_OIDC_SCOPES", "GROK_OIDC_AUDIENCE", "GROK_FORCE_LOGIN_TEAM_ID",
    "GROK_DISABLE_API_KEY_AUTH", "GROK_FOLDER_TRUST", "GROK_TRACK_HEADLESS",
    "GROK_WS_URL", "GROK_WS_ORIGIN", "GROK_TELEMETRY_EVENTS_URL",
    "GROK_TELEMETRY_EVENTS_API_KEY", "GROK_TELEMETRY_MIXPANEL_TOKEN",
    "XAI_API_BASE_URL", "GROK_MODELS_BASE_URL", "GROK_MODELS_LIST_URL",
    "GROK_MANAGED_CONFIG_URL", "GROK_FEEDBACK_BASE_URL", "GROK_ALPHA_TEST_KEY",
    "GROK_AUTH_FORCE_DARK_WAKE"}))


def grok_forbidden_name(name: str, *, names=GROK_FORBIDDEN_ENV,
                        prefixes=GROK_ROUTE_PREFIXES) -> bool:
    """One pure decision for Grok's bound relay policy and the subscription config door."""
    folded = name.casefold()
    return (any(folded == own.casefold() for own in names)
            or any(folded.startswith(prefix.casefold()) for prefix in prefixes))


def grok_compat_switch(profile, name: str, value: str) -> bool:
    """Only Grok's exact code-owned import disable; never exempts an operator selection."""
    relay = profile.login_relay
    return (profile.home_env == "GROK_HOME" and relay is not None
            and relay.kind == "g" and relay.credential == "auth.json"
            and relay.section == GROK_SCOPE and (name, value) in GROK_COMPAT_ENV)


def access_only_switch(profile, name: str, value: str) -> bool:
    """The one exact code-owned switch of Codex's access-only relay, never an operator grant."""
    relay = profile.login_relay
    return (profile.home_env == "CODEX_HOME" and relay is not None
            and relay.kind == "x" and relay.credential == "auth.json"
            and (name, value) in CODEX_ACCESS_ONLY_ENV)


#: What a spec of each harness forbids, in its own `forbidden_env`.
CLAUDE_FORBIDDEN_ENV = tuple(sorted({*CLAUDE_ROUTE_ENV, *COMMON_ROUTE_ENV}))
CODEX_FORBIDDEN_ENV = tuple(sorted({*CODEX_ROUTE_ENV, *CODEX_CREDENTIAL_ENV, *COMMON_ROUTE_ENV}))
#: What the config door and the wizard refuse beside a subscription: the union, because the door
#: does not branch on which harness a row is for. A name one harness does not read is harmless in
#: the row of another, and a row that forwarded it would gain nothing it could use.
SUBSCRIPTION_ROUTE_ENV = tuple(sorted({
    *CLAUDE_FORBIDDEN_ENV, *CODEX_FORBIDDEN_ENV, *GROK_FORBIDDEN_ENV}))

_FOLDED = frozenset(name.casefold() for name in SUBSCRIPTION_ROUTE_ENV)


def route_env_named(names: Iterable[str]) -> tuple[str, ...]:
    """Those of `names` that replace a subscription login or reroute its traffic, as written.

    Args:
        names: Environment variable names, as an operator wrote them.
    """
    return tuple(name for name in names
                 if name.casefold() in _FOLDED or grok_forbidden_name(name))
