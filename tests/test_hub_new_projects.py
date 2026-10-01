"""Creating a scratch project uses admitted directories and the same terminal admission door."""
import json
from pathlib import Path

import pytest

from conductor import ownership_records
from conductor.hub import dialogs, events, operations, project_targets, registry
from conductor.hub.refusals import HubRefusal
from tests.test_hub_dialogs import settled as picked
from tests.test_hub_http_surface import stack  # noqa: F401


@pytest.fixture
def places(tmp_path_factory, monkeypatch):
    base = tmp_path_factory.mktemp("hubnew")
    hub, personal = base / "h", base / "u"
    hub.mkdir()
    personal.mkdir()
    monkeypatch.setenv("CONDUCT_HOME", str(hub))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: personal))
    return hub, personal


def test_default_parent_read_is_pure_and_creation_is_exclusive(places):
    hub, personal = places
    destination = project_targets.target(hub, "new-app")
    assert destination == personal / "ConductProjects" / "new-app"
    assert not destination.parent.exists()
    made, parent_created = project_targets.create(hub, "new-app")
    assert made == destination and parent_created and list(made.iterdir()) == []
    (made / "owner.txt").write_text("keep", encoding="utf-8")
    with pytest.raises(HubRefusal, match="folder_exists"):
        project_targets.create(hub, "new-app")
    assert (made / "owner.txt").read_text(encoding="utf-8") == "keep"


@pytest.mark.parametrize("name", ["../outside", "bad/name", "", "a" * 41])
def test_invalid_child_name_does_not_create_any_directory(places, name):
    hub, personal = places
    with pytest.raises(HubRefusal, match="folder_invalid"):
        project_targets.create(hub, name)
    assert list(personal.iterdir()) == []


def test_parent_cannot_be_inside_project_or_hub(places):
    hub, personal = places
    project = personal / "project"
    child = project / "new-projects"
    child.mkdir(parents=True)
    (project / ".conduct").mkdir()
    for path in (child, hub):
        with pytest.raises(HubRefusal, match="projects_home_invalid"):
            project_targets.admit_home(path, hub)


def test_projects_home_picker_cannot_be_reused_as_a_project_pick(places):
    hub, personal = places
    parent = personal / "chosen"
    parent.mkdir()
    manager = dialogs.Dialogs(hub, events.EventBus(), available=lambda: True)
    manager._choose = lambda _ident: {"path": str(parent)}
    ident = manager.begin("projects_home")
    result = picked(manager, ident)
    assert result["state"] == "picked" and result["project"] is None
    assert str(parent) not in json.dumps(result)
    assert manager.resolve(ident) is None and manager.resolve_home(ident) == str(parent)
    manager.consume(ident)
    assert manager.resolve_home(ident) is None


def test_scratch_operation_runs_real_cli_and_keeps_origin_without_git(places):
    hub, personal = places
    starts = []
    manager = operations.Operations(hub, events.EventBus(), start=starts.append,
        status=lambda _ident: ("running", None))
    target = project_targets.target(hub, "scratch")
    ident = manager.begin(operations.FolderPick(str(target), "none"), "New project", True,
        source="scratch", prepare=lambda: project_targets.create(hub, "scratch"))
    # CLI is a real subprocess; the test only substitutes the subsequent server start.
    import time
    deadline = time.monotonic() + 15
    while manager.get(ident)["state"] == "running" and time.monotonic() < deadline:
        time.sleep(.02)
    row = manager.get(ident)
    assert row["state"] == "succeeded", row
    saved = registry.load(hub).projects[0]
    assert saved.source == "scratch" and saved.repo is None
    assert starts == [saved.project_id]
    assert row["result"]["projects_home_created"] is True
    assert "root" not in row["result"] and str(target) not in json.dumps(row)
    assert ownership_records.state(target)[1]["nonce"] == saved.project_id
    assert not (target / ".git").exists()


def test_http_scratch_requires_review_profile_before_creating_a_folder(stack, tmp_path_factory,
                                                                    monkeypatch):
    from conductor.command import operator_config
    from tests.test_provider_profile import config
    parent = tmp_path_factory.mktemp("scratch")
    hub = stack.service._home
    registry.set_projects_home(str(parent), hub)
    monkeypatch.setenv("CONDUCT_HOME", str(hub))
    monkeypatch.setattr(stack.service, "_tool", lambda _tool: {"state": "pinned"})
    body = {"source": "scratch", "folder": "fresh", "name": "Fresh"}
    answer = stack.post("/hub/projects", body)
    assert answer.status == 409 and answer.json()["error"]["code"] == "review_harness_missing"
    assert not (parent / "fresh").exists()
    operator_config.save_profile_configs(hub / "providers.json", [config(parent)])
    calls = []
    def begin(pick, name, confirmed, **options):
        calls.append((pick, name, confirmed, options))
        return "operation-" + "e" * 32
    monkeypatch.setattr(stack.service._operations, "begin", begin)
    answer = stack.post("/hub/projects", body)
    assert answer.status == 202
    assert calls[0][2] is True and calls[0][3]["source"] == "scratch"
    assert not (parent / "fresh").exists()  # preflight never creates; accepted operation owns mkdir


def test_http_home_setting_consumes_only_its_own_native_pick(stack, tmp_path_factory, monkeypatch):
    parent = tmp_path_factory.mktemp("chosen")
    hub = stack.service._home
    monkeypatch.setenv("CONDUCT_HOME", str(hub))
    manager = stack.service._dialogs
    manager._available = lambda: True
    manager._choose = lambda _ident: {"path": str(parent)}
    ident = manager.begin("projects_home")
    assert picked(manager, ident)["state"] == "picked"
    response = stack.post("/hub/setup/projects-home", {"pick_id": ident})
    assert response.status == 200 and str(parent) not in str(response.json())
    assert registry.load(hub).projects_home == str(parent)
    assert stack.post("/hub/setup/projects-home", {"pick_id": ident}).status == 409
    assert stack.post("/hub/setup/projects-home", {"default": True}).status == 200
    assert registry.load(hub).projects_home is None


def test_parent_setting_does_not_change_a_running_add(stack):
    stack.service._operations._rows["operation-" + "f" * 32] = {"state": "running"}
    before = registry.load(stack.service._home).projects_home
    response = stack.post("/hub/setup/projects-home", {"default": True})
    assert response.status == 409 and response.json()["error"]["code"] == "operation_busy"
    assert registry.load(stack.service._home).projects_home == before


@pytest.mark.parametrize("source", [[], {}, "folder"])
def test_source_specific_shapes_are_refused_as_contracts(stack, source):
    answer = stack.post("/hub/projects", {"source": source, "folder": "x", "name": "X"})
    assert answer.status == 422 and answer.json()["error"]["code"] == "contract_invalid"
