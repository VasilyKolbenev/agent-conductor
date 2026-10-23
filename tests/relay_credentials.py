"""Synthetic credentials of the full schema of both harnesses, for the relay tests.

Nothing here is a real value and nothing is read from the machine: every token is an invented
string that says what it is, so a copy that reaches a place it should not is readable at a glance.
The shapes are the ones the pinned CLIs write (Claude Code 2.1.239 `.credentials.json` and
`.claude.json`, Codex 0.112.0 `auth.json`), with every key the relay's schema names and a value of
the type the schema names for it. The tests spell the expected relay documents by hand and never
build them from these helpers, so a helper cannot agree with the code under test by construction.
"""
from __future__ import annotations

import base64
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

#: The instant every test calls "now". A token made here expires `ACCESS_LIFE` after it.
NOW = datetime(2026, 10, 23, 12, 0, 0, tzinfo=timezone.utc)
ACCESS_LIFE = timedelta(hours=4)

CLAUDE_ACCESS = "fake-claude-access-token-AAAAAAAAAAAA"
CLAUDE_REFRESH = "fake-claude-refresh-token-RRRRRRRRRRRR"
CLAUDE_PRIMARY_KEY = "fake-claude-primary-api-key-PPPPPPPPPPPP"
CLAUDE_ACCOUNT = "00000000-0000-4000-8000-00000000000a"
CLAUDE_ORGANIZATION = "00000000-0000-4000-8000-00000000000b"
CODEX_REFRESH = "fake-codex-refresh-token-RRRRRRRRRRRR"
CODEX_ACCOUNT = "fake-codex-account-0001"
CODEX_API_KEY = "fake-codex-api-key-KKKKKKKKKKKK"


def millis(moment: datetime) -> int:
    """Milliseconds since 1970 of an instant, as Claude writes `expiresAt`."""
    return int(moment.timestamp() * 1000)


def claude_leaf(**oauth) -> dict:
    """A `.credentials.json` of the full subscription schema; `oauth` replaces any one value."""
    body = {
        "accessToken": CLAUDE_ACCESS,
        "refreshToken": CLAUDE_REFRESH,
        "expiresAt": millis(NOW + ACCESS_LIFE),
        "refreshTokenExpiresAt": millis(NOW + timedelta(days=30)),
        "scopes": ["user:inference", "user:profile"],
        "subscriptionType": "max",
        "rateLimitTier": "default_claude_max_5x",
        "clientId": "fake-claude-client-id-0000",
    }
    body.update(oauth)
    return {"claudeAiOauth": body}


def claude_profile(**changes) -> dict:
    """A `.claude.json` as the vendor keeps it: the account, and much that must not travel."""
    body = {
        "numStartups": 7,
        "oauthAccount": {
            "accountUuid": CLAUDE_ACCOUNT,
            "emailAddress": "fake.person@example.invalid",
            "organizationUuid": CLAUDE_ORGANIZATION,
            "displayName": "Fake Person",
            "organizationName": "Fake Organization",
            "organizationRole": "admin",
        },
        "cachedGrowthBookFeatures": {"tengu_windows_credman": False, "tengu_fake_feature": True},
        "mcpServers": {"fake-server": {"command": "fake-command-that-must-not-travel"}},
        "projects": {"C:/fake/project": {"allowedTools": ["fake-tool-that-must-not-travel"]}},
        "primaryApiKey": CLAUDE_PRIMARY_KEY,
    }
    body.update(changes)
    return body


def segment(value: object) -> str:
    """One unpadded base64url segment of a JWT, from a JSON value."""
    raw = json.dumps(value).encode("utf-8")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def jwt(payload: object) -> str:
    """A JWT-shaped string around a payload; the signature is not one, and nothing checks it."""
    return f"{segment({'alg': 'none', 'typ': 'JWT'})}.{segment(payload)}.fake-signature-SSSSSSSS"


def epoch_seconds(moment: datetime) -> int:
    return int(moment.timestamp())


def codex_leaf(**tokens) -> dict:
    """An `auth.json` of the full ChatGPT schema; `tokens` replaces any one of its values."""
    body = {
        "id_token": jwt({"sub": "fake-subject", "email": "fake.person@example.invalid"}),
        "access_token": jwt({"sub": "fake-subject", "exp": epoch_seconds(NOW + ACCESS_LIFE)}),
        "refresh_token": CODEX_REFRESH,
        "account_id": CODEX_ACCOUNT,
    }
    body.update(tokens)
    return {"OPENAI_API_KEY": None, "tokens": body, "last_refresh": "2026-10-23T11:00:00Z"}


def put(home: Path, name: str, document: object) -> Path:
    """Write one JSON file into a folder, making the folder; return the file."""
    home.mkdir(parents=True, exist_ok=True)
    target = home / name
    target.write_text(json.dumps(document), encoding="utf-8")
    return target


def claude_home(base: Path, *, leaf: dict | None = None, profile: dict | None = None) -> Path:
    """A real login home of the Claude harness: the credential and the vendor's profile."""
    home = base / "real-claude"
    put(home, ".credentials.json", claude_leaf() if leaf is None else leaf)
    put(home, ".claude.json", claude_profile() if profile is None else profile)
    return home


def codex_home(base: Path, *, leaf: dict | None = None) -> Path:
    """A real login home of the Codex harness: the credential, and a config that must not travel."""
    home = base / "real-codex"
    put(home, "auth.json", codex_leaf() if leaf is None else leaf)
    (home / "config.toml").write_text(
        'model = "fake-model-that-must-not-travel"\n', encoding="utf-8")
    return home


def relay_home(base: Path, name: str = "relay-home") -> Path:
    """An empty folder where the relay home of an attempt goes."""
    home = base / name
    home.mkdir(parents=True)
    return home


def listing(home: Path) -> list[str]:
    """Every file under a folder, as sorted forward-slash paths relative to it."""
    return sorted(path.relative_to(home).as_posix() for path in home.rglob("*") if path.is_file())


def all_bytes(home: Path) -> bytes:
    """The bytes of every file under a folder, for a scan for a value that must not be there."""
    return b"".join(path.read_bytes() for path in sorted(home.rglob("*")) if path.is_file())
