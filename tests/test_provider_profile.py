"""The shared CLI profile uses the ordinary writer; applying it only copies configuration.

The parser, dialogue, ownership dispatch, stores and write guard are real. Only terminal
answers are scripted. Login files contain fixture bytes and no harness or login is run.
"""
from __future__ import annotations

import io
import json
from contextlib import contextmanager
from pathlib import Path

import pytest

from conductor import ownership, provider_profile, provider_setup
from conductor.__main__ import main
from conductor.command import operator_config
from conductor.command.adapters.provider import ProviderConfig
from conductor.command.providers import PROVIDER_CATALOG
from tests.test_project_ownership import activated
from tests.test_provider_setup import menu_choice, scripted


@pytest.fixture
def profile_home(tmp_path, monkeypatch):
    folder = tmp_path / "shared-profile"
    monkeypatch.setenv("CONDUCT_HOME", str(folder))
    return folder


def tree(root):
    root = Path(root)
    # Windows holds the owner's file with an exclusive byte lock. Its identity is
    # checked through owner.check(); do not try to read locked bytes in the snapshot.
    return {path.relative_to(root).as_posix(): None if path.is_dir() else path.read_bytes()
            for path in sorted(root.rglob("*"))
            if path.name != ".conduct-owner"} if root.exists() else {}


def config(tmp_path, provider="claude-code", *, label="pin", login=None):
    values = {"provider_id": provider, "executable": str(tmp_path / f"{provider}-{label}"),
              "protocol": PROVIDER_CATALOG[provider].protocol, "env_allow": ["FIXTURE_AUTH_NAME"]}
    if login is not None:
        values.update(auth="subscription", auth_home=str(login))
    return ProviderConfig(**values)


def project_at(path):
    path.mkdir()
    return activated(path)


def project_path(root):
    return operator_config.provider_config_path(ownership.data_root(root))


def save_project(root, rows):
    with ownership.acquire_owner(root):
        operator_config.save_provider_configs(project_path(root), rows, project_root=root)


def no_questions(_prompt):
    pytest.fail("this profile path must not ask a terminal question")


@pytest.mark.parametrize("flags", [
    ["--profile", "--dir", "."], ["--dir", ".", "--profile"]])
def test_profile_and_explicit_project_directory_are_mutually_exclusive(
        tmp_path, profile_home, monkeypatch, flags):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(provider_setup, "_console_ask", no_questions)
    with pytest.raises(SystemExit) as refusal:
        main(["providers", *flags])
    assert refusal.value.code == 2
    assert not profile_home.exists() and tree(tmp_path) == {}


def test_profile_creation_without_a_terminal_refuses_without_creating_the_home(
        tmp_path, profile_home, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(provider_setup.sys, "stdin", io.StringIO())
    monkeypatch.setattr(provider_setup, "_console_ask", no_questions)
    assert main(["providers", "--profile"]) == 1
    assert "needs a terminal" in capsys.readouterr().err
    assert not profile_home.exists() and tree(tmp_path) == {}


def test_profile_and_from_profile_together_refuse_before_any_question_or_write(
        tmp_path, profile_home, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(provider_setup, "_console_ask", no_questions)
    assert main(["providers", "--profile", "--from-profile"]) == 1
    assert "cannot be used together" in capsys.readouterr().err
    assert not profile_home.exists() and tree(tmp_path) == {}


def test_profile_from_an_owned_cwd_uses_the_unchanged_guard_without_acquiring_the_project(
        tmp_path, profile_home, monkeypatch):
    root = project_at(tmp_path / "project")
    executable = tmp_path / "fixture-harness"
    executable.write_bytes(b"not executable; only a pinned fixture path")
    monkeypatch.chdir(root)
    monkeypatch.setattr(provider_setup, "_interactive", lambda: True)
    monkeypatch.setattr(provider_setup, "_console_ask", scripted(
        menu_choice("claude-code"), str(executable), "2", "FIXTURE_AUTH_NAME", "y"))
    guards, acquisitions = [], []
    real_guard, real_acquire = ownership.provider_write_guard, ownership.acquire_owner

    @contextmanager
    def guard(target, project_root):
        guards.append((Path(target), project_root))
        with real_guard(target, project_root):
            yield

    def acquire(*args, **kwargs):
        acquisitions.append(args)
        return real_acquire(*args, **kwargs)

    with real_acquire(root) as owner:
        before = tree(root)
        monkeypatch.setattr(ownership, "provider_write_guard", guard)
        monkeypatch.setattr(ownership, "acquire_owner", acquire)
        assert main(["providers", "--profile"]) == 0
        target = profile_home / "providers.json"
        rows = operator_config.load_provider_configs(target)
        assert len(rows) == 1 and rows[0].provider_id == "claude-code"
        assert rows[0].executable == str(executable) and rows[0].env_allow == ("FIXTURE_AUTH_NAME",)
        assert guards == [(target, None)] and acquisitions == []
        assert tree(root) == before
        # The same guard still refuses an owned target without project context: profile
        # writing added no exemption for activated project files.
        with pytest.raises(operator_config.OperatorConfigError, match="project_context_required"):
            operator_config.save_provider_configs(project_path(root), rows)
        assert tree(root) == before
        owner.check()


@pytest.mark.parametrize("relation,code", [
    ("inside", "login_home_in_conduct_home"),
    ("equal", "conduct_home_overlaps_login"),
    ("ancestor", "conduct_home_overlaps_login")])
def test_a_profile_refuses_overlap_with_login_data_before_writing(
        tmp_path, profile_home, relation, code):
    login = {"inside": profile_home / "login", "equal": profile_home,
             "ancestor": profile_home.parent}[relation]
    login.mkdir(parents=True, exist_ok=True)
    (login / "login-fixture.json").write_text('{"fixture":true}\n', encoding="utf-8")
    before = tree(tmp_path)
    with pytest.raises(operator_config.OperatorConfigError, match=code):
        operator_config.save_profile_configs(profile_home / "providers.json",
                                             [config(tmp_path, login=login)])
    assert tree(tmp_path) == before


def test_a_profile_home_inside_an_activated_project_is_refused_even_with_its_owner(
        tmp_path, monkeypatch):
    root = project_at(tmp_path / "project")
    home = root / "nested" / "profile"
    monkeypatch.setenv("CONDUCT_HOME", str(home))
    with ownership.acquire_owner(root):
        before = tree(root)
        with pytest.raises(operator_config.OperatorConfigError, match="conduct_home_invalid"):
            operator_config.save_profile_configs(home / "providers.json", [config(tmp_path)])
        assert tree(root) == before and not home.exists()


def test_from_profile_merges_by_id_once_without_prompts_or_copying_login_files(
        tmp_path, profile_home, monkeypatch):
    root = project_at(tmp_path / "project")
    logins = [tmp_path / name for name in ("old-login", "shared-login", "project-login")]
    for login in logins:
        login.mkdir()
        (login / "login-fixture.json").write_text('{"fixture":true}\n', encoding="utf-8")
    old = config(tmp_path, label="old", login=logins[0])
    kept = config(tmp_path, "codex", label="project", login=logins[2])
    replacement = config(tmp_path, label="shared", login=logins[1])
    added = config(tmp_path, "kimi-code", label="shared")
    save_project(root, [old, kept])
    profile = profile_home / "providers.json"
    operator_config.save_profile_configs(profile, [replacement, added])
    profile_before, login_before = profile.read_bytes(), [tree(login) for login in logins]
    monkeypatch.setattr(provider_setup, "_interactive", lambda: False)
    monkeypatch.setattr(provider_setup, "_console_ask", no_questions)
    writes, real_replace = [], operator_config._replace_bytes

    def replace(target, payload):
        writes.append((Path(target), payload))
        return real_replace(target, payload)

    monkeypatch.setattr(operator_config, "_replace_bytes", replace)
    assert main(["providers", "--dir", str(root), "--from-profile"]) == 0
    assert operator_config.load_provider_configs(project_path(root)) == (replacement, kept, added)
    assert len(writes) == 1 and writes[0][0] == project_path(root)
    assert json.loads(writes[0][1])["providers"][0]["auth_home"] == str(logins[1])
    assert profile.read_bytes() == profile_before and [tree(login) for login in logins] == login_before
    assert not any(path.name == "login-fixture.json" for path in root.rglob("*"))


@pytest.mark.parametrize("kind", ["absent", "malformed", "invalid_second_row", "duplicate"])
def test_a_missing_or_corrupt_profile_never_partially_changes_the_project_config(
        tmp_path, profile_home, monkeypatch, capsys, kind):
    root = tmp_path / "project"
    target = root / "conductor" / "providers.json"
    target.parent.mkdir(parents=True)
    operator_config.save_provider_configs(target, [config(tmp_path, label="standing")])
    profile = profile_home / "providers.json"
    if kind != "absent":
        profile_home.mkdir()
        row = config(tmp_path, label="incoming").as_dict()
        document = ("{broken" if kind == "malformed" else json.dumps({
            "schema_version": 1, "providers": [row, row if kind == "duplicate" else
                                                  {**row, "provider_id": "codex", "executable": "relative"}]}))
        profile.write_text(document, encoding="utf-8")
    before = tree(tmp_path)
    monkeypatch.setattr(provider_setup, "_console_ask", no_questions)
    assert main(["providers", "--dir", str(root), "--from-profile"]) == 1
    message = capsys.readouterr().err
    assert ("profile_absent" if kind == "absent" else "profile_invalid") in message
    assert str(profile) in message and tree(tmp_path) == before


def test_an_unreadable_standing_profile_is_not_replaced_by_interactive_configuration(
        tmp_path, profile_home, monkeypatch, capsys):
    profile_home.mkdir()
    profile = profile_home / "providers.json"
    profile.write_bytes(b"{broken")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(provider_setup, "_interactive", lambda: True)
    monkeypatch.setattr(provider_setup, "_console_ask", no_questions)
    assert main(["providers", "--profile"]) == 1
    assert "profile_invalid" in capsys.readouterr().err and profile.read_bytes() == b"{broken"


@pytest.mark.parametrize("kind", ["missing_project", "corrupt_target"])
def test_applying_to_an_invalid_target_changes_neither_profile_nor_target(
        tmp_path, profile_home, monkeypatch, kind):
    operator_config.save_profile_configs(profile_home / "providers.json", [config(tmp_path)])
    root = tmp_path / "project"
    if kind == "corrupt_target":
        target = root / "conductor" / "providers.json"
        target.parent.mkdir(parents=True)
        target.write_bytes(b"{broken")
    before = tree(tmp_path)
    monkeypatch.setattr(provider_setup, "_console_ask", no_questions)
    assert main(["providers", "--dir", str(root), "--from-profile"]) == 1
    assert tree(tmp_path) == before


def test_save_profile_refuses_any_other_target_before_creating_its_home(tmp_path, profile_home):
    other = tmp_path / "other.json"
    other.write_bytes(b"owner bytes")
    with pytest.raises(operator_config.OperatorConfigError, match="profile_target_invalid"):
        operator_config.save_profile_configs(other, [config(tmp_path)])
    assert other.read_bytes() == b"owner bytes" and not profile_home.exists()


@pytest.mark.parametrize("flags", [[], ["--from-profile"]])
def test_only_profile_creation_bypasses_project_ownership_and_busy_project_writes_refuse(
        tmp_path, profile_home, monkeypatch, capsys, flags):
    root = project_at(tmp_path / "project")
    operator_config.save_profile_configs(profile_home / "providers.json", [config(tmp_path)])
    monkeypatch.setattr(provider_setup, "_console_ask", no_questions)
    with ownership.acquire_owner(root) as owner:
        before, profile_before = tree(root), tree(profile_home)
        assert main(["providers", "--dir", str(root), *flags]) == 1
        assert "owner_busy" in capsys.readouterr().err
        assert tree(root) == before and tree(profile_home) == profile_before
        owner.check()
