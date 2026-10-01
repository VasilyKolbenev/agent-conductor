"""Focused GitHub clone boundary witnesses; no real gh, git or browser."""
import io
import json
from pathlib import Path

import pytest

from conductor import tool_pins
from conductor.hub import clone, events, operations, project_targets, registry
from conductor.hub.refusals import HubRefusal
from tests.test_hub_http_surface import stack  # noqa: F401


class Finished:
    def __init__(self, stderr=b""):
        self.stdout, self.stderr = io.BytesIO(b""), io.BytesIO(stderr)
        self.returncode = 0

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        return self.returncode


class Group:
    def __init__(self, proc):
        self.terminated = False

    def terminate(self):
        self.terminated = True

    def retired(self, *, timeout):
        return self.terminated

    def close(self):
        pass


@pytest.fixture
def bound(tmp_path_factory, monkeypatch):
    tmp_path = tmp_path_factory.mktemp("hclone")
    home, personal = tmp_path / "hub", tmp_path / "personal"
    home.mkdir()
    personal.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda _cls: personal))
    gh = tool_pins.ToolPin("gh", str(tmp_path / "gh"), "2.70.0")
    git = tool_pins.ToolPin("git", str(tmp_path / "git"), "2.45.0")
    monkeypatch.setattr(tool_pins, "load_pins", lambda _home: tool_pins.ToolPins(gh=gh, git=git))
    monkeypatch.setattr(tool_pins, "verify_pin", lambda tool, **_kwargs: gh if tool == "gh" else git)
    return home, project_targets.ticket(home, "app")


def test_clone_uses_pinned_gh_clean_env_and_keeps_successful_owner_tree(bound):
    home, ticket = bound
    spawned = []
    def launch(argv, **options):
        spawned.append((argv, options))
        (ticket.path / ".git").mkdir()
        return Finished()
    cloner = clone.Clones(home, source={"GH_TOKEN": "secret", "GH_HOST": "foreign"},
                          popen=launch, make_group=Group)
    ident = "operation-" + "a" * 32
    path, made_home = cloner.clone(ident, "owner/app", ticket)
    assert path == ticket.path and made_home and (path / ".git").is_dir()
    argv, options = spawned[0]
    assert argv[1:] == ["repo", "clone", "owner/app", str(path), "--", "--no-recurse-submodules"]
    assert "GH_TOKEN" not in options["env"] and "GH_HOST" not in options["env"]
    assert options["env"]["GIT_CONFIG_KEY_0"] == "core.hooksPath"
    record = json.loads((home / "clone-attempts" / f"{ident}.json").read_text())
    assert record["phase"] == "cloned" and record["target_identity"] is not None


def test_cancel_before_spawn_removes_only_owned_empty_target(bound):
    home, ticket = bound
    cloner = clone.Clones(home, popen=lambda *_args, **_kwargs: pytest.fail("gh spawned"))
    ident = "operation-" + "b" * 32
    cloner.cancel(ident)
    with pytest.raises(clone.CloneFailed, match="cancelled"):
        cloner.clone(ident, "owner/app", ticket)
    assert not ticket.path.exists()
    assert json.loads((home / "clone-attempts" / f"{ident}.json").read_text())["phase"] == "cleaned"


def test_hardlink_in_clone_refuses_cleanup_and_preserves_foreign_bytes(bound, tmp_path):
    home, ticket = bound
    foreign = tmp_path / "foreign"
    foreign.write_bytes(b"keep")
    cloner = clone.Clones(home)
    def failed(_ident, _repo, path, _row):
        import os
        os.link(foreign, path / "alias")
        raise clone.CloneFailed("clone_failed")
    cloner._run = failed
    ident = "operation-" + "c" * 32
    with pytest.raises(clone.CloneFailed, match="clone_cleanup_incomplete"):
        cloner.clone(ident, "owner/app", ticket)
    assert foreign.read_bytes() == b"keep" and ticket.path.exists()


def test_replaced_target_identity_is_not_deleted(bound):
    home, ticket = bound
    cloner = clone.Clones(home)
    def changed(_ident, _repo, path, _row):
        path.rename(path.with_name("moved-owned"))
        path.mkdir()
        (path / "foreign").write_bytes(b"keep")
        raise clone.CloneFailed("clone_failed")
    cloner._run = changed
    with pytest.raises(clone.CloneFailed, match="clone_cleanup_incomplete"):
        cloner.clone("operation-" + "8" * 32, "owner/app", ticket)
    assert (ticket.path / "foreign").read_bytes() == b"keep"


def test_http_github_body_reaches_clone_operation_without_a_web_path(stack, tmp_path_factory,
                                                                      monkeypatch):
    home = stack.service._home
    registry.set_projects_home(str(tmp_path_factory.mktemp("github-home")), home)
    monkeypatch.setattr(stack.service, "_tool", lambda _tool: {"state": "pinned"})
    calls = []
    monkeypatch.setattr(stack.service._operations, "begin", lambda *args, **kwargs:
                        calls.append((args, kwargs)) or "operation-" + "d" * 32)
    body = {"source": "github", "repo": "owner/app", "folder": "app", "name": "My app"}
    answer = stack.post("/hub/projects", body)
    assert answer.status == 202 and calls[0][1]["repo"] == "owner/app"
    assert calls[0][1]["source"] == "github" and callable(calls[0][1]["prepare"])
    assert not (Path(registry.load(home).projects_home) / "app").exists()
    for bad in ("--help/app", "owner/../app", "owner/app\n--flag"):
        answer = stack.post("/hub/projects", {**body, "repo": bad})
        assert answer.status == 422 and answer.json()["error"]["code"] == "repo_invalid"


def test_cancel_route_accepts_only_live_clone_step(stack):
    ident = "operation-" + "e" * 32
    rows = stack.service._operations._rows
    rows[ident] = {"source": "github", "state": "running", "step": "clone"}
    calls = []
    stack.service._operations._clone_cancel = calls.append
    assert stack.post(f"/hub/operations/{ident}/cancel", {}).status == 202
    assert calls == [ident]
    rows[ident]["step"] = "admit"
    response = stack.post(f"/hub/operations/{ident}/cancel", {})
    assert response.status == 409 and response.json()["error"]["code"] == "operation_not_cancellable"


def test_successful_clone_remains_visible_when_projects_add_refuses(bound):
    home, ticket = bound
    ident = "operation-" + "f" * 32
    manager = operations.Operations(home, events.EventBus(), start=lambda _ident: None,
                                    status=lambda _ident: ("running", None))
    manager._rows[ident] = {"operation_id": ident, "kind": "add", "source": "github",
                            "state": "running", "step": "clone", "project_id": None,
                            "code": None, "result": None}
    manager._cli = lambda *_args, **_kwargs: (None, "tracks_product_dir")
    manager._run(ident, operations.FolderPick(str(ticket.path), "none"), "My app", True,
                 source="github", repo="owner/app",
                 prepare=lambda _ident: (ticket.path, False))
    row = manager.get(ident)
    assert row["state"] == "failed" and row["code"] == "tracks_product_dir"
    assert row["result"] == {"folder": "app", "cloned": True,
                             "projects_home_created": False}


def test_setup_exposes_only_an_operation_id_for_unresolved_cleanup(stack):
    ident = "operation-" + "9" * 32
    stack.service._clone_recovery = (ident,)
    recovery = stack.get("/hub/setup").json()["clone_recovery"]
    assert recovery == [{"operation_id": ident, "code": "clone_cleanup_incomplete"}]
    assert "clone-attempts" not in json.dumps(recovery)
