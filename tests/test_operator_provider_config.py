"""The operator's provider file is the whole configuration surface, and `up` reads it.

Before this seam existed the provider vertical was reachable only by injecting
Python objects: a person who installed the alpha could configure no provider at
all. The seam closed here is deliberately tiny -- a provider id, one absolute
executable, an optional absolute entrypoint, a reviewed protocol token, and
environment NAMES -- and it proves nothing itself. Every dangerous shape is
handed to the session-1 ``ProviderConfig`` door and refused there; this module's
job is to accept exactly five names, refuse everything else, and name the exact
file in every refusal so an operator can find what they wrote.

The accepted key set is DERIVED from ``ProviderConfig._FIELDS`` rather than
retyped, so a field added to the durable config cannot silently become an
undocumented operator key or silently disappear from this surface.
"""
from __future__ import annotations

import json

import pytest

from conductor import server
from conductor.command.adapters.provider import ProviderConfig
from conductor.command.operator_config import (
    PROVIDER_CONFIG_FILENAME,
    OperatorConfigError,
    load_provider_configs,
)
from conductor.command.providers import PROVIDER_CATALOG

from tests.test_store import good_lane, write_project


PROTOCOL = "fake-claude-jsonl-v1"
#: Stands in for whatever an operator really wrote. A refusal is read by a person
#: and may be logged, so it names the file and the key -- never a pinned value.
SENTINEL = "SECRET-VALUE-THAT-MUST-NOT-BE-ECHOED"
#: Names an open-ended configuration surface would have carried. None is a
#: ProviderConfig field, so each must be refused rather than stored or ignored.
FORBIDDEN_KEYS = (
    "argv", "args", "cmd", "command", "shell", "cwd", "env", "api_key",
    "token", "secret", "install", "path_scan",
)


def a_document(**changes):
    """One well-formed operator document with a single pinned provider row."""
    row = {
        "provider_id": "claude-code",
        "executable": "/opt/claude/bin/claude",
        "protocol": PROTOCOL,
    }
    row.update(changes)
    return {"schema_version": 1, "providers": [row]}


def write_config(tmp_path, document, *, name=PROVIDER_CONFIG_FILENAME):
    path = tmp_path / name
    path.write_text(
        document if isinstance(document, str) else json.dumps(document),
        encoding="utf-8", newline="\n")
    return path


# -- what the surface accepts --


def test_a_pinned_row_becomes_exactly_the_provider_config_the_door_admits(tmp_path):
    path = write_config(tmp_path, a_document(
        entrypoint="/opt/claude/lib/main.js", env_allow=["CLAUDE_API_KEY"]))
    assert load_provider_configs(path) == (
        ProviderConfig(
            provider_id="claude-code", executable="/opt/claude/bin/claude",
            protocol=PROTOCOL, env_allow=("CLAUDE_API_KEY",),
            entrypoint="/opt/claude/lib/main.js"),)


def test_an_absent_file_configures_nothing_and_refuses_nothing(tmp_path):
    assert load_provider_configs(tmp_path / PROVIDER_CONFIG_FILENAME) == ()


def test_the_optional_halves_default_to_the_empty_pin_the_door_reads_as_none(tmp_path):
    config = load_provider_configs(write_config(tmp_path, a_document()))[0]
    assert (config.entrypoint, config.env_allow) == ("", ())


def test_the_operator_surface_is_exactly_the_durable_config_fields(tmp_path):
    """The accepted names are the config's own; nothing extra, nothing missing."""
    path = write_config(tmp_path, a_document(
        entrypoint="/opt/claude/lib/main.js", env_allow=["CLAUDE_API_KEY"]))
    accepted = set(json.loads(path.read_text(encoding="utf-8"))["providers"][0])
    assert accepted == set(ProviderConfig._FIELDS)
    assert set(FORBIDDEN_KEYS).isdisjoint(ProviderConfig._FIELDS)


# -- what the surface refuses, always naming the file --


REFUSED = {
    "not_json": "{ this is not json",
    "top_level_array": [],
    "unknown_top_level_key": {**a_document(), "install": True},
    "missing_providers": {"schema_version": 1},
    "unreviewed_schema_version": {**a_document(), "schema_version": 2},
    "boolean_schema_version": {**a_document(), "schema_version": True},
    "providers_not_a_list": {"schema_version": 1, "providers": {}},
    "row_not_an_object": {"schema_version": 1, "providers": ["claude-code"]},
    "row_missing_executable": {
        "schema_version": 1,
        "providers": [{"provider_id": "claude-code", "protocol": PROTOCOL}]},
    "relative_executable": a_document(executable="claude"),
    "bare_name_executable": a_document(executable="claude.exe"),
    "unreviewed_protocol": a_document(protocol="whatever-v9"),
    "env_allow_carries_values": a_document(env_allow={"CLAUDE_API_KEY": "sk-secret"}),
    "env_allow_repeats_a_name": a_document(env_allow=["A_KEY", "A_KEY"]),
    "relative_entrypoint": a_document(entrypoint="lib/main.js"),
    "duplicate_provider_id": {
        "schema_version": 1,
        "providers": [
            {"provider_id": "claude-code", "executable": "/a/claude",
             "protocol": PROTOCOL},
            {"provider_id": "claude-code", "executable": "/b/claude",
             "protocol": PROTOCOL}]},
}


@pytest.mark.parametrize("name", sorted(REFUSED))
def test_every_refused_document_is_refused_and_names_the_exact_file(tmp_path, name):
    path = write_config(tmp_path, REFUSED[name])
    with pytest.raises(OperatorConfigError) as refusal:
        load_provider_configs(path)
    assert str(path) in str(refusal.value)


@pytest.mark.parametrize("key", FORBIDDEN_KEYS)
def test_no_open_ended_key_survives_the_operator_surface(tmp_path, key):
    path = write_config(tmp_path, a_document(**{key: SENTINEL}))
    with pytest.raises(OperatorConfigError) as refusal:
        load_provider_configs(path)
    assert str(path) in str(refusal.value)
    assert SENTINEL not in str(refusal.value)


@pytest.mark.parametrize("name", sorted(REFUSED))
def test_a_refusal_names_the_file_and_never_repeats_a_value_out_of_it(tmp_path, name):
    """A refusal is read by a person and may be logged; a pinned value is not its business."""
    document = REFUSED[name]
    seeded = (document.replace("json", SENTINEL) if isinstance(document, str)
              else json.loads(json.dumps(document).replace(PROTOCOL, SENTINEL)))
    path = write_config(tmp_path, seeded)
    with pytest.raises(OperatorConfigError) as refusal:
        load_provider_configs(path)
    assert str(path) in str(refusal.value)
    assert SENTINEL not in str(refusal.value)


# -- the seam is reachable from the real `conduct up` --


class _StubServer:
    """Stands in for the bound server so `up` returns instead of serving."""

    def __init__(self) -> None:
        self.server_address = ("127.0.0.1", 7777)

    def serve_forever(self) -> None:
        return None

    def server_close(self) -> None:
        return None


def a_project(tmp_path):
    return write_project(tmp_path, lanes={"claude": good_lane()})


def test_conduct_up_help_names_the_operator_provider_seam(capsys):
    from conductor.__main__ import main

    with pytest.raises(SystemExit) as exited:
        main(["up", "--help"])
    assert exited.value.code == 0
    rendered = capsys.readouterr().out
    assert "--providers" in rendered
    # The help spells the default path out; this holds that spelling to the file
    # the loader really reads, which the behaviour test below drives for real.
    assert f"conductor/{PROVIDER_CONFIG_FILENAME}" in rendered


def test_conduct_up_hands_the_pinned_providers_to_the_server_it_builds(
        tmp_path, monkeypatch):
    from conductor.__main__ import main

    root = a_project(tmp_path)
    write_config(root / "conductor", a_document(executable=str(tmp_path / "claude")))
    captured: dict[str, object] = {}

    def fake_build(built_root, port, **kwargs):
        captured["root"] = built_root
        captured["providers"] = kwargs["providers"]
        return _StubServer()

    monkeypatch.setattr(server, "build", fake_build)
    assert main(["up", "--dir", str(root)]) == 0
    assert captured["providers"] == (
        ProviderConfig(
            provider_id="claude-code", executable=str(tmp_path / "claude"),
            protocol=PROTOCOL, env_allow=(), entrypoint=""),)


def test_conduct_up_refuses_a_broken_operator_file_and_names_it(
        tmp_path, monkeypatch, capsys):
    from conductor.__main__ import main

    root = a_project(tmp_path)
    path = write_config(root / "conductor", "{ not json at all")

    def never_build(*_args, **_kwargs):
        raise AssertionError("a refused operator file must not build a server")

    monkeypatch.setattr(server, "build", never_build)
    assert main(["up", "--dir", str(root)]) == 1
    captured = capsys.readouterr()
    assert str(path) in captured.err and captured.out == ""


# -- the default product is honest about the whole reviewed roster --


def test_the_default_server_catalogues_every_reviewed_provider_as_unconfigured(
        tmp_path):
    root = a_project(tmp_path)
    subject = server.build(root, 0)
    try:
        contracts = subject.command_providers
        assert {row.provider_id for row in contracts} == set(PROVIDER_CATALOG)
        assert {row.availability for row in contracts} == {"unconfigured"}
        # Nothing is spawn-capable: an unconfigured provider owns no adapter.
        assert subject.command_registry.manifests() == ()
    finally:
        subject.server_close()
