"""Focused terminal witnesses for the existing-folder path of spec 8.2."""
from __future__ import annotations

import json
import shutil
import subprocess

import pytest

from conductor import ownership, ownership_records, ownership_transition, tool_pins
from conductor.command import operator_config
from conductor.hub import cli, registry
from tests.test_provider_profile import config


def _lines(capsys):
    out, err = capsys.readouterr()
    return [json.loads(line) for line in out.splitlines()], err


def test_new_folder_needs_explicit_activation_then_retries_without_rewriting(tmp_path, monkeypatch,
                                                                              capsys):
    home = tmp_path / "hub-home"
    monkeypatch.setenv("CONDUCT_HOME", str(home))
    project = tmp_path / "project"
    project.mkdir()
    original = project / "notes.txt"
    original.write_bytes(b"owned bytes\r\n")

    assert cli.projects_add(str(project)) == 1
    lines, err = _lines(capsys)
    assert lines == [{"step": "admit"}, {"step": "git"}, {"step": "init"}]
    assert "legacy_writers_must_stop" in err
    assert original.read_bytes() == b"owned bytes\r\n"
    assert not registry.registry_file(home).exists()

    assert cli.projects_add(str(project), legacy_writers_stopped=True) == 0
    lines, err = _lines(capsys)
    assert [next(iter(line)) for line in lines] == ["step"] * 8 + ["result"]
    assert [line["step"] for line in lines[:-1]] == list((
        "admit", "git", "init", "activate", "providers", "exclude", "instructions", "register"))
    first = lines[-1]["result"]
    assert first["registered"] == "new" and first["activated"] == "new"
    assert first["git"] == "not_git" and first["providers"] == "absent"
    assert first["project_id"] == registry.load(home).projects[0].project_id
    assert original.read_bytes() == b"owned bytes\r\n"

    assert cli.projects_add(str(project)) == 0
    repeated, _err = _lines(capsys)
    assert repeated[-1]["result"]["registered"] == "existing"
    assert repeated[-1]["result"]["activated"] == "existing"
    assert len(registry.load(home).projects) == 1


def test_relative_root_refuses_before_any_write(tmp_path, monkeypatch, capsys):
    home = tmp_path / "hub-home"
    monkeypatch.setenv("CONDUCT_HOME", str(home))
    assert cli.projects_add("relative-folder", legacy_writers_stopped=True) == 1
    lines, err = _lines(capsys)
    assert lines == [] and "refused root_invalid" in err
    assert not home.exists()


@pytest.mark.parametrize("source,repo", [("scratch", None), ("github", "octocat/app")])
def test_project_origin_is_kept_in_registry(tmp_path, monkeypatch, capsys, source, repo):
    home, project = tmp_path / "hub-home", tmp_path / "project"
    project.mkdir()
    monkeypatch.setenv("CONDUCT_HOME", str(home))
    assert cli.projects_add(str(project), source=source, repo=repo,
                            legacy_writers_stopped=True) == 0
    _lines(capsys)
    saved = registry.load(home).projects[0]
    assert (saved.source, saved.repo) == (source, repo)
    assert not (project / ".git").exists()  # source metadata never initializes Git


@pytest.mark.parametrize("source,repo", [("github", None), ("github", "--evil/x"),
                                        ("scratch", "a/b"), ("folder", "a/b")])
def test_invalid_origin_refuses_before_scaffold(tmp_path, monkeypatch, capsys, source, repo):
    home, project = tmp_path / "hub-home", tmp_path / "project"
    project.mkdir()
    monkeypatch.setenv("CONDUCT_HOME", str(home))
    assert cli.projects_add(str(project), source=source, repo=repo,
                            legacy_writers_stopped=True) == 1
    lines, error = _lines(capsys)
    assert lines == [] and "repo_invalid" in error
    assert list(project.iterdir()) == [] and not home.exists()


def test_nested_root_refuses_before_any_write(tmp_path, monkeypatch, capsys):
    home = tmp_path / "hub-home"
    monkeypatch.setenv("CONDUCT_HOME", str(home))
    outer = tmp_path / "parent"
    child = outer / "child"
    child.mkdir(parents=True)
    (outer / ".conduct").mkdir()
    assert cli.projects_add(str(child), legacy_writers_stopped=True) == 1
    lines, err = _lines(capsys)
    assert lines == [] and "refused root_nested" in err
    assert tuple(child.iterdir()) == ()


def test_new_folder_copies_shared_provider_configuration_without_login_files(
        tmp_path, monkeypatch, capsys):
    home = tmp_path / "hub-home"
    monkeypatch.setenv("CONDUCT_HOME", str(home))
    project = tmp_path / "project"
    project.mkdir()
    profile = home / "providers.json"
    row = config(tmp_path)
    operator_config.save_profile_configs(profile, [row])
    assert cli.projects_add(str(project), legacy_writers_stopped=True) == 0
    lines, _err = _lines(capsys)
    assert lines[-1]["result"]["providers"] == "copied"
    assert operator_config.load_provider_configs(project / "conductor.v3" / "providers.json") == (row,)
    assert not any(path.name == "login-fixture.json" for path in project.rglob("*"))


def test_tracked_product_directory_refuses_before_project_writes(tmp_path, monkeypatch, capsys):
    git = shutil.which("git")
    if git is None:
        pytest.skip("git is unavailable on this test machine")
    home = tmp_path / "hub-home"
    monkeypatch.setenv("CONDUCT_HOME", str(home))
    project = tmp_path / "project"
    project.mkdir()
    subprocess.run([git, "init", "-q", str(project)], check=True)
    owned = project / "work" / "owner.txt"
    owned.parent.mkdir()
    owned.write_bytes(b"owner bytes\n")
    subprocess.run([git, "-C", str(project), "add", "work/owner.txt"], check=True)
    tool_pins.pin_tool("git", git, folder=home)
    assert cli.projects_add(str(project), legacy_writers_stopped=True) == 1
    lines, err = _lines(capsys)
    assert lines == [{"step": "admit"}]
    assert "refused tracks_product_dir" in err
    assert owned.read_bytes() == b"owner bytes\n"
    assert not (project / "conductor").exists()
    assert not registry.registry_file(home).exists()


def test_a_link_in_the_supplied_route_refuses_before_resolving_it(tmp_path, monkeypatch, capsys):
    home = tmp_path / "hub-home"
    monkeypatch.setenv("CONDUCT_HOME", str(home))
    parent = tmp_path / "actual"
    project = parent / "project"
    project.mkdir(parents=True)
    alias = tmp_path / "alias"
    try:
        alias.symlink_to(parent, target_is_directory=True)
    except OSError:
        pytest.skip("this Windows account cannot create directory symlinks")
    assert cli.projects_add(str(alias / "project"), legacy_writers_stopped=True) == 1
    lines, err = _lines(capsys)
    assert lines == [] and "refused root_invalid" in err
    assert tuple(project.iterdir()) == () and not home.exists()


def test_interrupted_activation_resumes_only_after_explicit_confirmation(
        tmp_path, monkeypatch, capsys):
    home = tmp_path / "hub-home"
    monkeypatch.setenv("CONDUCT_HOME", str(home))
    project = tmp_path / "project"
    project.mkdir()
    real_finish = ownership_transition._finish_activation

    def interrupted(*_args):
        raise ownership_records.OwnerRefused("recovery_required", "simulated interruption")

    monkeypatch.setattr(ownership_transition, "_finish_activation", interrupted)
    assert cli.projects_add(str(project), legacy_writers_stopped=True) == 1
    lines, err = _lines(capsys)
    assert [line["step"] for line in lines] == ["admit", "git", "init"]
    assert "refused recovery_required" in err
    assert ownership_records.chain(project)["phase"] == "moved"

    monkeypatch.setattr(ownership_transition, "_finish_activation", real_finish)
    assert cli.projects_add(str(project)) == 1
    lines, err = _lines(capsys)
    assert [line["step"] for line in lines] == ["admit", "git", "init"]
    assert "refused legacy_writers_must_stop" in err
    assert ownership_records.chain(project)["phase"] == "moved"
    assert cli.projects_add(str(project), legacy_writers_stopped=True) == 0
    lines, _err = _lines(capsys)
    assert lines[-1]["result"]["activated"] == "new"
    assert ownership_records.state(project)[1]["phase"] in {"active", "closed"}


def test_corrupt_registered_provider_file_blocks_unprovable_login_admission(
        tmp_path, monkeypatch, capsys):
    home = tmp_path / "hub-home"
    monkeypatch.setenv("CONDUCT_HOME", str(home))
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    assert cli.projects_add(str(first), legacy_writers_stopped=True) == 0
    _lines(capsys)
    with ownership.acquire_owner(first):
        (first / "conductor.v3" / "providers.json").write_bytes(b"{broken")
    assert cli.projects_add(str(second), legacy_writers_stopped=True) == 1
    lines, err = _lines(capsys)
    assert lines == [] and "refused root_in_login_home" in err
    assert tuple(second.iterdir()) == ()
