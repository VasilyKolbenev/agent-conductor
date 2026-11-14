"""Codex's relay: which login is admitted, and what an attempt is given of it.

Codex CLI 0.164.0 keeps one ChatGPT login in `auth.json`: `tokens` (`id_token`, `access_token`,
`refresh_token`, `account_id`), `last_refresh`, an `auth_mode` and an `OPENAI_API_KEY` slot. Its
tokens may also hold `login_owner_id` (text) and `oauth_provenance` (exactly `issuer` and
`client_id`, both text). The relay admits that closed shape and the older one without those
optional fields. The API-key slot must be empty regardless of the CLI's mode selection: this
route admits only the pinned subscription. A key the schema does not name, at the top or among
the tokens, is refused by name. `auth_mode` is in the real file of a
ChatGPT login (measured, M1 of 23.10.2026) and is admitted only as the text `chatgpt`; a file
without it is admitted as before, and any other mode, or a value that is not text, is refused. The
copy keeps the field as it is.

The copy preserves `login_owner_id` but drops `oauth_provenance`: refresh routing metadata is
not part of the access-only attempt. Neither this removal nor refresh stripping changes the source.

Codex reads its login from a file or from the system keyring by the config key
`cli_auth_credentials_store` (`file`, `keyring`, `auto`, `ephemeral`; a wrong literal fails the
config load, measured on 23.10.2026). The relay copies a file, so every spawn that reads the login
is told `AUTH_STORE_ARGV`. The VALUE half of a `-c` pair is parsed by the CLI as TOML, so the
literal is the quoted string `"file"`, the one form measured (the Codex review of 23.10.2026,
`login status`, exits 0, 1, 0); the bare word `file` would rest on the `--help` fallback ("if it
fails to parse as TOML, the raw string is used"), which was read and not tried on this key. A
shell eats the quotes of a command a person pastes (Windows PowerShell 5.1 hands a program
`cli_auth_credentials_store=file` for either spelling, measured; a POSIX shell does the same by
its rules, not tried), so the printed sign-in command means the same.

The copy has no usable refresh token. The pinned CLI refuses an `auth.json` that lacks the field
(`missing field refresh_token`, measured by the Codex review of 23.10.2026) and reads one holding an
empty string, so the form of the copy (`CODEX_FORM`, the one value to change after the live
measurement M2) is the empty string, and `last_refresh` and every deadline stay as they were: no
value is altered to get a file accepted. Whether the CLI WORKS on it is M2 and not something this
module can show.

The expiry of the login is the `exp` of the access token's JWT payload, read with no check of any
signature (`login_relay.jwt_expiry`): a time and not a proof of anything.

`$CODEX_HOME/.credentials.json` is where the CLI keeps the OAuth of its tool servers. It is not
copied, and the leak scan reads it (`CODEX_MCP_CREDENTIALS`, in the profile's `login_credentials`),
because a child that echoed one back would be publishing a secret the scan had not heard of.

A value module: it judges documents `login_relay.read_leaf` has read and names no OS door.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .login_relay import Refused, RelaySpec, jwt_expiry
from .relay_env import CODEX_FORBIDDEN_ENV

CREDENTIAL = "auth.json"
CODEX_MCP_CREDENTIALS = ".credentials.json"
#: The config override every Codex spawn that reads the login carries, in this one place. The
#: value is a TOML string, like the telemetry pairs of `codex_cli.TELEMETRY_ARGV`.
AUTH_STORE_ARGV = ("-c", 'cli_auth_credentials_store="file"')
SECTION = "tokens"
#: THE form of the access-only copy: the refresh token is present and empty.
CODEX_FORM = (("refresh_token", ""),)
#: The one login mode of a subscription, as `auth.json` of a ChatGPT login spells it.
CHATGPT_MODE = "chatgpt"
_TOP = frozenset({"OPENAI_API_KEY", "tokens", "last_refresh", "auth_mode"})
_TOKENS = frozenset({"id_token", "access_token", "refresh_token", "account_id", "login_owner_id",
                     "oauth_provenance"})


@dataclass(frozen=True)
class CodexRelay(RelaySpec):
    """The relay of Codex; its facts are in `CODEX_RELAY`."""

    def admit(self, doc: dict) -> str | None:
        if not set(doc) <= _TOP:
            return "foreign_credentials"
        if doc.get("OPENAI_API_KEY") is not None:
            return "api_key"
        if "auth_mode" in doc:
            if type(doc["auth_mode"]) is not str:
                return "unknown_shape"
            if doc["auth_mode"] != CHATGPT_MODE:
                return "foreign_credentials"
        tokens = doc.get(SECTION)
        if (type(tokens) is not dict or not set(tokens) <= _TOKENS
                or any(type(value) is not str for key, value in tokens.items()
                       if key != "oauth_provenance")
                or ("last_refresh" in doc and type(doc["last_refresh"]) is not str)):
            return "unknown_shape"
        if "oauth_provenance" in tokens:
            provenance = tokens["oauth_provenance"]
            if (type(provenance) is not dict or set(provenance) != {"issuer", "client_id"}
                    or any(type(value) is not str for value in provenance.values())):
                return "unknown_shape"
        if not tokens.get("access_token"):
            return "no_access_token"
        return None if tokens.get("account_id") else "account_unknown"

    def strip(self, doc: dict) -> dict:
        copied = super().strip(doc)
        tokens = copied.get(SECTION)
        if type(tokens) is dict:
            tokens.pop("oauth_provenance", None)
        return copied

    def bootstrap(self, real_home: Path) -> dict[str, bytes] | Refused:
        """Nothing: `config.toml` carries executable configuration and is not copied."""
        return {}

    def account(self, doc: dict, material: dict[str, bytes]) -> str | None:
        tokens = doc.get(SECTION)
        value = tokens.get("account_id") if type(tokens) is dict else None
        return value if type(value) is str and value else None

    def expires_at(self, doc):
        tokens = doc.get(SECTION)
        return jwt_expiry(tokens.get("access_token")) if type(tokens) is dict else None


CODEX_RELAY = CodexRelay(
    kind="x", credential=CREDENTIAL, files=(CREDENTIAL,),
    secret_fields=("id_token", "access_token", "refresh_token", "OPENAI_API_KEY"),
    refresh_fields=("refresh_token",), section=SECTION, form=CODEX_FORM,
    forbidden_env=CODEX_FORBIDDEN_ENV)
