"""The one operator-writable surface that configures a provider, and its five keys.

Everything else in this package is reachable only from code. This module is the
door a PERSON uses: one JSON file, read once at startup, holding a list of pinned
providers. It exists so the provider vertical is reachable from the real
``conduct up`` and not only from a Python test harness.

What the file may say is deliberately tiny, and it is exactly what
:class:`~conductor.command.adapters.provider.ProviderConfig` already carries: a
provider id, one ABSOLUTE executable path, an optional ABSOLUTE entrypoint path,
a reviewed protocol token, and environment NAMES. There is no argv, no shell, no
cwd, no working directory, no timeout, no installer, no registry URL and no
credential: a secret is named here and read from the live environment at spawn
time, so no value one names ever lands in this file.

This module PROVES almost nothing itself, on purpose. It reads the document,
refuses any key outside the five, fills in the two optional halves, and hands
each row to the ProviderConfig door -- which is where a relative path, an
unreviewed protocol, a NUL byte, or an env VALUE masquerading as a name is
refused. What this module adds is that every refusal, wherever it came from,
names the exact file the operator has to go and fix.

It opens no process, no socket, and no environment: the only door it touches is
one read of one path the caller names.
"""
from __future__ import annotations

import json
from pathlib import Path

from .adapters.provider import ProviderConfig, ProviderConfigError

#: The file `conduct up` reads out of a project's `conductor/` directory.
PROVIDER_CONFIG_FILENAME = "providers.json"
#: The one document shape this build reads. A file that says anything else is
#: refused rather than partly understood.
SCHEMA_VERSION = 1
_TOP_LEVEL = frozenset({"schema_version", "providers"})
#: The keys an operator MUST write, and the two they may leave out. Together they
#: are exactly the durable config's own fields, so this surface cannot drift into
#: carrying something the config does not, or into hiding something it does.
_REQUIRED_KEYS = frozenset({"provider_id", "executable", "protocol"})
_OPTIONAL_KEYS = frozenset({"entrypoint", "env_allow"})


class OperatorConfigError(RuntimeError):
    """The operator provider file is unreadable, open-ended, or refused by the door."""


def provider_config_path(conductor_dir: Path | str) -> Path:
    """The exact path `conduct up` reads providers from, given a conductor/ directory."""
    return Path(conductor_dir) / PROVIDER_CONFIG_FILENAME


def load_provider_configs(path: Path | str) -> tuple[ProviderConfig, ...]:
    """Read the operator's pinned providers, or refuse and name the exact file.

    Args:
        path: The provider file to read. An absent file configures nothing.

    Returns:
        One `ProviderConfig` per row, in file order, each already admitted by the
        provider config door.

    Raises:
        OperatorConfigError: The file could not be read, is not the one reviewed
            document shape, carries a key outside the five, names one provider
            twice, or holds a row the ProviderConfig door refuses. Every message
            names `path`.
    """
    target = Path(path)
    document = _read_document(target)
    if document is None:
        return ()
    rows = _reviewed_document(target, document)
    configs: list[ProviderConfig] = []
    seen: set[str] = set()
    for index, row in enumerate(rows):
        config = _reviewed_row(target, index, row)
        if config.provider_id in seen:
            raise OperatorConfigError(
                f"{target}: provider {config.provider_id!r} is configured more than once")
        seen.add(config.provider_id)
        configs.append(config)
    return tuple(configs)


def _read_document(target: Path) -> object | None:
    """One read of one named path; an absent file is silence, not a refusal."""
    try:
        text = target.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except (OSError, UnicodeDecodeError) as error:
        raise OperatorConfigError(f"{target}: cannot be read as UTF-8 text: {error}") from None
    try:
        return json.loads(text)
    except ValueError as error:
        raise OperatorConfigError(f"{target}: is not valid JSON: {error}") from None


def _reviewed_document(target: Path, document: object) -> list[object]:
    """Hold the whole document shape before one provider row is looked at."""
    if type(document) is not dict or any(type(key) is not str for key in document):
        raise OperatorConfigError(
            f"{target}: must be a JSON object with "
            f"exactly the keys {sorted(_TOP_LEVEL)}")
    if set(document) != _TOP_LEVEL:
        raise OperatorConfigError(
            f"{target}: keys must be exactly {sorted(_TOP_LEVEL)}; "
            f"found {sorted(document)}")
    version = document["schema_version"]
    if type(version) is not int or version != SCHEMA_VERSION:
        raise OperatorConfigError(
            f"{target}: schema_version must be exactly {SCHEMA_VERSION}")
    rows = document["providers"]
    if type(rows) is not list:
        raise OperatorConfigError(f"{target}: providers must be a JSON array of rows")
    return rows


def _reviewed_row(target: Path, index: int, row: object) -> ProviderConfig:
    """Close one row's key set, then let the provider config door prove the rest."""
    where = f"{target}: providers[{index}]"
    if type(row) is not dict or any(type(key) is not str for key in row):
        raise OperatorConfigError(f"{where} must be a JSON object with string keys")
    unknown = sorted(set(row) - _REQUIRED_KEYS - _OPTIONAL_KEYS)
    if unknown:
        raise OperatorConfigError(
            f"{where} carries keys this surface does not accept: {unknown}; "
            f"a provider row holds only {sorted(_REQUIRED_KEYS | _OPTIONAL_KEYS)}")
    missing = sorted(_REQUIRED_KEYS - set(row))
    if missing:
        raise OperatorConfigError(f"{where} is missing required keys: {missing}")
    try:
        # The two optional halves default to "the operator pinned none", which is
        # the whole shape for a provider that is its own executable and needs no
        # environment name. Nothing else is filled in for them.
        return ProviderConfig.from_dict({"entrypoint": "", "env_allow": [], **row})
    except ProviderConfigError as error:
        raise OperatorConfigError(f"{where} was refused: {error}") from None
