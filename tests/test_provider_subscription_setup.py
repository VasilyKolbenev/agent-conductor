"""A Studio card's project-scoped Windows handoff, with local packages and fake logins."""
from __future__ import annotations

from dataclasses import replace
import json

import pytest

from conductor import provider_setup, store
from conductor.__main__ import main
from conductor.command.adapters.local_test_plan import inventory_digest
from conductor.command.providers import PROVIDER_CATALOG
from conductor.ownership import acquire_owner
from conductor.ownership_transition import activate
from tests import relay_credentials as fake
from tests.test_grok_relay import _document


@pytest.fixture
def project(tmp_path):
    root = tmp_path.resolve() / "project"
    assert main(["init", "--dir", str(root)]) == 0
    activate(root, legacy_writers_stopped=True)
    return root


def card(root, kind):
    return main(["providers", "--dir", str(root), "--subscription", kind])


def test_card_command_requires_the_owner_terminal(project, monkeypatch, capsys):
    monkeypatch.setattr(provider_setup, "_interactive", lambda: False)
    assert card(project, "grok-build") == 1
    assert "needs a terminal" in capsys.readouterr().err


def test_cli_offers_only_transports_with_reviewed_packages(project, monkeypatch, capsys):
    adapter = PROVIDER_CATALOG["codex"].adapter_class
    monkeypatch.setattr(adapter, "windows_subscription", None, raising=False)
    for value in ("codex", "marker-never-disclose"):
        with pytest.raises(SystemExit) as exit_info:
            card(project, value)
        assert exit_info.value.code == 2
        error = capsys.readouterr().err
        assert "select a reviewed subscription card: grok-build" in error
        assert value not in error


def test_unrelated_cli_commands_do_not_load_subscription_transports():
    from pathlib import Path
    import subprocess
    import sys
    source = Path(__file__).resolve().parents[1] / "src"
    script = """
import sys
sys.path.insert(0, sys.argv[1])
from conductor.__main__ import _build_parser
_build_parser().parse_args(["validate"])
print("conductor.command.adapters" in sys.modules)
"""
    checked = subprocess.run([sys.executable, "-I", "-B", "-c", script, str(source)],
                             capture_output=True, check=True, text=True, timeout=30)
    assert checked.stdout.strip() == "False"


@pytest.fixture
def machine(tmp_path, monkeypatch):
    from conductor import provider_subscription_setup as setup
    product = tmp_path.resolve() / "DecemberCommand"
    product.mkdir()
    monkeypatch.setattr(setup, "_product", lambda: product)
    monkeypatch.setattr(setup, "WINDOWS", True)
    monkeypatch.setattr(setup, "_login_acl", lambda path: None)
    monkeypatch.setattr(setup.provider_install_security, "verify_install", lambda *args: None)
    monkeypatch.setattr(setup, "_now", lambda: fake.NOW)
    monkeypatch.setattr(provider_setup, "_interactive", lambda: True)
    return setup, product


def fixture_install(machine, kind, monkeypatch):
    _, product = machine
    adapter = PROVIDER_CATALOG[kind].adapter_class
    reviewed = adapter.windows_subscription
    directory = product / "harnesses" / kind / adapter.profile.reviewed_version
    filepath = directory / reviewed.executable
    filepath.parent.mkdir(parents=True)
    filepath.write_bytes(b"synthetic package, never executed")
    monkeypatch.setattr(adapter, "windows_subscription",
                        replace(reviewed, inventory=inventory_digest(directory)))
    return directory, filepath


@pytest.mark.parametrize("kind,home_var,login_words", [
    ("codex", "CODEX_HOME", "cli_auth_credentials_store"),
    ("grok-build", "GROK_HOME", "--no-auto-update login"),
])
def test_real_cli_takes_vendor_handoff_checks_file_saves_only_pin_and_preserves_peers(
        machine, project, kind, home_var, login_words, monkeypatch, capsys):
    setup, product = machine
    _, executable = fixture_install(machine, kind, monkeypatch)
    login = product / "logins" / kind
    config = store.conductor_dir(project) / "providers.json"
    peer = {"provider_id": "deepseek-harness",
            "protocol": PROVIDER_CATALOG["deepseek-harness"].protocol,
            "executable": str(executable), "entrypoint": str(executable)}
    config.write_text(json.dumps({"schema_version": 1, "providers": [peer]}), encoding="utf-8")
    prompts = []
    def owner(prompt):
        prompts.append(prompt)
        if "finished" in prompt:
            assert not (login / "auth.json").exists()
            data = fake.codex_leaf() if kind == "codex" else _document()
            (login / "auth.json").write_text(json.dumps(data), encoding="utf-8")
        return "y"
    monkeypatch.setattr(provider_setup, "_console_ask", owner)
    assert card(project, kind) == 0
    said = capsys.readouterr().err
    assert home_var in said and login_words in said
    assert "restart" in said.lower()
    provider_file = config.read_text(encoding="utf-8")
    rows = {r["provider_id"]: r for r in json.loads(provider_file)["providers"]}
    assert set(rows) == {"deepseek-harness", kind}
    assert rows[kind]["auth"] == "subscription" and rows[kind]["auth_home"] == str(login)
    assert rows[kind]["executable"] == str(executable)
    assert len(prompts) == 2
    assert "fake-grok-access" not in said + provider_file
    assert fake.CODEX_REFRESH not in said + provider_file


def test_edited_package_refused_before_signin_and_write(machine, project, monkeypatch, capsys):
    setup, _ = machine
    install, _ = fixture_install(machine, "grok-build", monkeypatch)
    (install / "unexpected.exe").write_bytes(b"unexpected")
    monkeypatch.setattr(provider_setup, "_console_ask", lambda prompt: pytest.fail(prompt))
    assert card(project, "grok-build") == 1
    assert "installation" in capsys.readouterr().err
    assert not (store.conductor_dir(project) / "providers.json").exists()


def test_running_studio_refused_before_login_or_prompt(machine, project, monkeypatch):
    _, product = machine
    monkeypatch.setattr(provider_setup, "_console_ask", lambda prompt: pytest.fail(prompt))
    with acquire_owner(project):
        assert card(project, "codex") == 1
    assert not (product / "logins").exists()


@pytest.mark.parametrize("kind,extra,accept", [
    ("codex", "empty config", True), ("codex", "marketplace", False),
    ("codex", "auth.json.lock", False), ("codex", "memtrace", False),
    ("grok-build", "marketplace", True), ("grok-build", "auth.json.lock", True),
    ("grok-build", "memtrace", True), ("grok-build", "unreviewed", False),
])
def test_each_card_admits_only_its_reviewed_login_material(
        machine, project, kind, extra, accept, monkeypatch):
    _, product = machine
    fixture_install(machine, kind, monkeypatch)
    home = product / "logins" / kind
    fake.put(home, "auth.json", fake.codex_leaf() if kind == "codex" else _document())
    if extra in ("marketplace", "empty config"):
        content = ""
        if extra == "marketplace":
            content = "[marketplace]\ndefault_skills_installs_purged = true\n"
        (home / "config.toml").write_text(content, encoding="utf-8")
    elif extra == "memtrace":
        (home / extra).mkdir()
    else:
        (home / extra).write_bytes(b"")
    prompts = []
    def owner(prompt):
        prompts.append(prompt)
        return "y"
    monkeypatch.setattr(provider_setup, "_console_ask", owner)
    assert card(project, kind) == (0 if accept else 1)
    assert (store.conductor_dir(project) / "providers.json").exists() == accept
    assert len(prompts) == int(accept)


@pytest.mark.parametrize("kind", ["codex", "grok-build"])
def test_expired_dedicated_login_renews_once_under_lease(machine, project, kind, monkeypatch):
    setup, product = machine
    fixture_install(machine, kind, monkeypatch)
    home = product / "logins" / kind
    expired = (fake.codex_leaf(access_token=fake.jwt({"exp": 1})) if kind == "codex"
               else _document(expires_at="2025-01-01T00:00:00Z"))
    fake.put(home, "auth.json", expired)
    prompts = []
    def owner(prompt):
        prompts.append(prompt)
        if "finished" in prompt:
            assert len(list(home.parent.glob(".conduct-login-*/active.json"))) == 1
            fake.put(home, "auth.json", fake.codex_leaf() if kind == "codex" else _document())
        return "y"
    monkeypatch.setattr(provider_setup, "_console_ask", owner)
    assert card(project, kind) == 0
    assert len(prompts) == 2
    assert not list(home.parent.glob(".conduct-login-*/active.json"))


@pytest.mark.parametrize("case", ["not-signed-in", "malformed", "config", "refused", "cancel"])
def test_no_unverified_or_declined_pin_is_saved(machine, project, case, monkeypatch, capsys):
    setup, product = machine
    fixture_install(machine, "grok-build", monkeypatch)
    home = product / "logins" / "grok-build"
    if case == "malformed":
        fake.put(home, "auth.json", {"foreign": "marker-never-disclose"})
    if case == "config":
        fake.put(home, "auth.json", _document())
        (home / "config.toml").write_text('command = "marker-never-disclose"', encoding="utf-8")
    if case == "refused":
        monkeypatch.setattr(setup, "_login_acl", lambda path: "private permissions required")
    def owner(prompt):
        if case == "cancel":
            if "finished" in prompt:
                fake.put(home, "auth.json", _document())
                return "y"
            return "n"
        if case == "not-signed-in":
            return "y"
        pytest.fail("The rejected profile must not prompt for sign-in or saving.")
    monkeypatch.setattr(provider_setup, "_console_ask", owner)
    assert card(project, "grok-build") == 1
    assert "marker-never-disclose" not in capsys.readouterr().err
    assert not (store.conductor_dir(project) / "providers.json").exists()
    assert not list(home.parent.glob(".conduct-login-*/active.json"))


def test_native_leaf_cannot_grant_another_user_read_on_a_private_profile(tmp_path):
    import os
    if os.name != "nt":
        pytest.skip("Requires Windows security descriptors.")
    from conductor import provider_install_security as security
    from conductor.command.adapters import _winlaunch as native
    from conductor.ownership_native import NativeHold
    logins = tmp_path / "logins"
    logins.mkdir()
    owner = native.current_user_sid()
    acl = f"O:{owner}D:P(A;OICI;FA;;;SY)(A;OICI;FA;;;{owner})"
    handle = NativeHold(logins, directory=True, grants=True)
    try:
        native.acl_set(handle, acl, protected=True)
    finally:
        handle.close()
    home = logins / "codex"
    fake.put(home, "auth.json", {"local-test": True})
    security.verify_login_directory(home)
    handle = NativeHold(home / "auth.json", grants=True)
    try:
        native.acl_set(handle, acl + "(A;;FR;;;BU)", protected=True)
    finally:
        handle.close()
    with pytest.raises(OSError, match="entry in the dedicated login"):
        security.verify_login_directory(home)


def test_windows_acl_distinguishes_inheritance_replacement_and_foreign_access():
    from conductor.provider_install_security import acl_allows
    owner = "S-1-5-21-123"
    allowed = {owner, "SY", "BA"}
    def facts(acl):
        return ("O:" + owner + "D:P(A;OICI;FA;;;SY)" + acl, True, owner)
    assert acl_allows(facts("(A;;LC;;;AU)"), allowed, ancestor=True)
    assert not acl_allows(facts("(A;;DT;;;AU)"), allowed, ancestor=True)
    assert not acl_allows(facts("(A;;GW;;;BU)"), allowed)
    assert not acl_allows(facts("(A;OICIIO;FR;;;BU)"), allowed, private=True)
    assert not acl_allows(("O:" + owner + "D:", True, owner), allowed)


@pytest.mark.parametrize("kind,machine_input,outcome", [
    ("codex", "config.toml", "external"),
    ("codex", "requirements.toml", "external"),
    ("codex", "policy key", "external"),
    ("codex", "unreadable key", "unreadable"),
    ("codex", "absent", "inventory"),
    ("grok-build", "config.toml", "inventory"),
    ("grok-build", "unreadable key", "inventory"),
])
def test_card_checks_its_declared_machine_inputs_before_signin(
        tmp_path, kind, machine_input, outcome, monkeypatch):
    from contextlib import nullcontext
    import sys
    from types import SimpleNamespace
    from conductor import provider_install_security as security
    from conductor import provider_subscription_setup as setup
    from conductor.command import adapters

    product = tmp_path / "product"
    version = PROVIDER_CATALOG[kind].adapter_class.profile.reviewed_version
    (product / "harnesses" / kind / version).mkdir(parents=True)
    # Use a deliberately incomplete installation. Reaching inventory proves that
    # no external input was admitted as a matching install or used for a login.
    machine = tmp_path / "ProgramData"
    (machine / "OpenAI" / "Codex").mkdir(parents=True)
    monkeypatch.setenv("ProgramData", str(machine))
    if machine_input.endswith(".toml"):
        (machine / "OpenAI" / "Codex" / machine_input).write_bytes(b"")
    monkeypatch.setattr(adapters, "_winlaunch", SimpleNamespace(current_user_sid=lambda: "BA"),
                        raising=False)
    facts = ("O:BAD:P(A;;FA;;;BA)", True, "BA")
    monkeypatch.setattr(security, "_acl_of", lambda *args, **kw: facts)
    queries = []
    def open_key(hive, key, *, access):
        queries.append((hive, key, access))
        if machine_input == "policy key":
            return nullcontext()
        if machine_input == "unreadable key":
            raise PermissionError("cannot read test key")
        raise FileNotFoundError()
    monkeypatch.setitem(sys.modules, "winreg", SimpleNamespace(
        HKEY_LOCAL_MACHINE=1, KEY_READ=2, KEY_WOW64_64KEY=4, OpenKey=open_key))
    if outcome == "external":
        with pytest.raises(OSError, match="External Codex machine configuration"):
            setup._installation(product, kind)
    elif outcome == "unreadable":
        with pytest.raises(PermissionError, match="cannot read test key"):
            setup._installation(product, kind)
    else:
        with pytest.raises(provider_setup.SetupError, match="complete Windows package"):
            setup._installation(product, kind)
    expected = [(1, r"SOFTWARE\Policies\OpenAI\Codex", 6)]
    assert queries == (expected if kind == "codex" and not machine_input.endswith(".toml") else [])
    assert not (product / "logins").exists()
