"""The one operator-writable surface that configures a provider, and its seven keys.

Everything else in this package is reachable only from code. This module is the
door a PERSON uses: one JSON file, read once at startup, holding a list of pinned
providers. It exists so the provider vertical is reachable from the real
``conduct up`` and not only from a Python test harness.

What the file may say is deliberately tiny, and it is exactly what
:class:`~conductor.command.adapters.provider.ProviderConfig` already carries: a
provider id, one ABSOLUTE executable path, an optional ABSOLUTE entrypoint path,
a reviewed protocol token, environment NAMES, which login the harness is pinned
to, and -- where that login is the vendor's own -- the ABSOLUTE directory it is
kept in. There is no argv, no shell, no cwd, no working directory, no timeout,
no installer, no registry URL and no credential: a secret is named here and read
from the live environment at spawn time, or lives in the login directory the
vendor's own command wrote, so no value one names ever lands in this file.

This module PROVES almost nothing itself, on purpose. It reads the document,
refuses any key outside the seven, fills in the four optional halves, and hands
each row to the ProviderConfig door -- which is where a relative path, an
unreviewed protocol, a NUL byte, or an env VALUE masquerading as a name is
refused. What this module adds is that every refusal, wherever it came from,
names the exact file the operator has to go and fix.

It opens no process, no socket, and no environment: the only doors it touches
are one read and one write of one path the caller names.

The write is here rather than beside whoever collects the answers, and that is
the whole reason it is here: a file with a reader in one module and a writer in
another has two opinions about its shape, and they drift. `save_provider_configs`
emits exactly what `load_provider_configs` admits, and a round trip in either
direction is the test that says so. It adds no validation of its own -- what it
writes has already been through the ProviderConfig door, because the only thing
it accepts is a `ProviderConfig`.
"""
from __future__ import annotations

import json
from pathlib import Path

from .adapters.provider import DEFAULT_AUTH_MODE, ProviderConfig, ProviderConfigError
from .run_store import _replace_bytes

#: The file `conduct up` reads out of a project's `conductor/` directory.
PROVIDER_CONFIG_FILENAME = "providers.json"
#: The one document shape this build reads. A file that says anything else is
#: refused rather than partly understood.
SCHEMA_VERSION = 1
_TOP_LEVEL = frozenset({"schema_version", "providers"})
#: The keys an operator MUST write, and the four they may leave out. Together they
#: are exactly the durable config's own fields, so this surface cannot drift into
#: carrying something the config does not, or into hiding something it does.
_REQUIRED_KEYS = frozenset({"provider_id", "executable", "protocol"})
_OPTIONAL_KEYS = frozenset({"entrypoint", "env_allow", "auth", "auth_home"})


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
            document shape, carries a key outside the seven, names one provider
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


def save_provider_configs(
        path: Path | str, configs: "tuple[ProviderConfig, ...] | list[ProviderConfig]") -> Path:
    """Write the operator's pinned providers, all or nothing.

    What is written is the document `load_provider_configs` reads and nothing
    else: the two top-level keys, then one row per config carrying only the
    fields that config holds. An optional half is OMITTED when the config
    carries what an absent key already means -- no entrypoint, no environment
    name, the login that shipped -- so a file written by this function is the
    file a person would have written by hand, and no reader has to tell an
    absent entrypoint from an empty one. A row that spelled such a default out
    loud is therefore written back WITHOUT it: the document means the same
    thing, and this surface has one spelling for one fact.

    Staged and replaced rather than truncated and rewritten. A crash midway
    through a rewrite would leave `conduct up` reading half a document and
    refusing every provider in it, including the ones that were already there.

    Args:
        path: The provider file to write, normally `provider_config_path`'s.
            Its parent directory must already exist -- this module creates no
            project.
        configs: The providers to write, in the order they should appear. Each
            has already been through the ProviderConfig door; nothing here
            re-judges them.

    Returns:
        The path written.

    Raises:
        OperatorConfigError: A value is not a `ProviderConfig`, one provider id
            appears twice, or the file could not be written. The duplicate is
            refused HERE as well as on read, because a writer that produced a
            document its own reader rejects would strand an operator with a
            project they cannot start and a file they were told was saved.
    """
    target = Path(path)
    document = {"schema_version": SCHEMA_VERSION,
                "providers": _rows_document(target, configs)}
    payload = (json.dumps(document, indent=2, sort_keys=True,
                          ensure_ascii=False) + "\n").encode("utf-8")
    try:
        _replace_bytes(target, payload)
    except OSError as error:
        raise OperatorConfigError(f"{target}: cannot be written: {error}") from None
    return target


def _rows_document(target: Path, configs) -> list[dict[str, object]]:
    """Every row, refusing what this file's own reader would refuse.

    The duplicate is caught HERE as well as on read, because a writer that
    produced a document its own reader rejects would tell an operator their
    configuration was saved and leave them unable to start the project.
    """
    rows, seen = [], set()
    for config in configs:
        if type(config) is not ProviderConfig:
            raise OperatorConfigError(
                f"{target}: save_provider_configs takes ProviderConfig values")
        if config.provider_id in seen:
            raise OperatorConfigError(
                f"{target}: provider {config.provider_id!r} is configured more than once")
        seen.add(config.provider_id)
        rows.append(_row_document(config))
    return rows


def _row_document(config: ProviderConfig) -> dict[str, object]:
    """One provider row: the three required keys, and the optional ones it uses.

    `ProviderConfig.as_dict` answers with all seven, spelling "pinned none" as an
    empty string, an empty list, and the login that shipped. Those are the
    defaults `_reviewed_row` fills in, so writing them back would put two
    spellings of the same fact into every file this ever produces.
    """
    row = {key: value for key, value in config.as_dict().items()
           if key in _REQUIRED_KEYS}
    if config.entrypoint:
        row["entrypoint"] = config.entrypoint
    if config.env_allow:
        row["env_allow"] = list(config.env_allow)
    if config.auth != DEFAULT_AUTH_MODE:
        row["auth"] = config.auth
    if config.auth_home:
        row["auth_home"] = config.auth_home
    return row


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
        # The optional halves default to "the operator pinned none", which is the
        # whole shape for a provider that is its own executable, needs no
        # environment name, and takes the login this build shipped with. Nothing
        # else is filled in for them.
        return ProviderConfig.from_dict({
            "entrypoint": "", "env_allow": [], "auth": DEFAULT_AUTH_MODE,
            "auth_home": "", **row})
    except ProviderConfigError as error:
        raise OperatorConfigError(f"{where} was refused: {error}") from None
