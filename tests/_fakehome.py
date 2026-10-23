"""What a fake harness child can say about the config directory it was handed.

A relay home is judged from the far side: the fake child is a real process that was given a
`CLAUDE_CONFIG_DIR` or `CODEX_HOME`, so what it finds there at the moment it starts is the one fact
no parent can settle for it. The report holds file NAMES and one boolean (whether any credential
in the folder carries a refresh token) and never a value: a test log is not a place for a token.
"""
from __future__ import annotations

import json
from pathlib import Path

#: The keys under which the two harnesses keep a refresh token.
REFRESH_KEYS = ("refreshToken", "refresh_token")


def _pairs(value):
    """Every (key, value) pair at any depth of a JSON value."""
    pending = [value]
    while pending:
        item = pending.pop()
        if isinstance(item, dict):
            for key, inner in item.items():
                yield key, inner
                pending.append(inner)
        elif isinstance(item, list):
            pending.extend(item)


def report(directory: str | Path) -> dict:
    """The names of the files under a folder, and whether any JSON among them holds a refresh token.

    A refresh token counts when its key holds a non-empty text: Codex is given the key with an
    empty text (the CLI refuses a file without it), and that is no token.
    """
    base = Path(directory)
    names = sorted(path.relative_to(base).as_posix() for path in base.rglob("*") if path.is_file())
    refresh = False
    for name in names:
        if not name.endswith(".json"):
            continue
        try:
            document = json.loads((base / name).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        refresh = refresh or any(
            key in REFRESH_KEYS and type(value) is str and bool(value)
            for key, value in _pairs(document))
    return {"files": names, "refresh": refresh}


def rotate(directory: str | Path, name: str, path: tuple[str, ...], fresh: str) -> None:
    """Rewrite one credential in place with a new access token, keeping the rest of the document.

    What a vendor does with a token about to expire, in the schema the relay admits: the key at
    `path` (for example `("claudeAiOauth", "accessToken")`) takes the value `fresh`.
    """
    target = Path(directory) / name
    document = json.loads(target.read_text(encoding="utf-8"))
    holder = document
    for key in path[:-1]:
        holder = holder[key]
    holder[path[-1]] = fresh
    target.write_text(json.dumps(document), encoding="utf-8", newline="\n")
