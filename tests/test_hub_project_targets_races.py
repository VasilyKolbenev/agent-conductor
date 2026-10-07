"""An accepted scratch target cannot be redirected before its operation starts."""
from pathlib import Path

import pytest

from conductor.hub import project_targets, registry
from conductor.hub.refusals import HubRefusal


@pytest.fixture
def places(tmp_path_factory, monkeypatch):
    base = tmp_path_factory.mktemp("target")
    hub, personal = base / "hub", base / "personal"
    hub.mkdir()
    personal.mkdir()
    monkeypatch.setenv("CONDUCT_HOME", str(hub))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: personal))
    return hub, personal


def test_ticket_rejects_home_changed_after_add_was_accepted(places):
    hub, personal = places
    first, second = personal / "first", personal / "second"
    first.mkdir()
    second.mkdir()
    registry.set_projects_home(str(first), hub)
    expected = project_targets.ticket(hub, "new-app")
    registry.set_projects_home(str(second), hub)
    with pytest.raises(HubRefusal, match="projects_home_invalid"):
        project_targets.create(hub, "new-app", expected=expected)
    assert not (first / "new-app").exists()
    assert not (second / "new-app").exists()


def test_ticket_rejects_replaced_ancestor_before_mkdir(places):
    hub, personal = places
    parent, moved = personal / "chosen", personal / "moved"
    parent.mkdir()
    registry.set_projects_home(str(parent), hub)
    expected = project_targets.ticket(hub, "new-app")
    parent.rename(moved)
    parent.mkdir()
    with pytest.raises(HubRefusal, match="projects_home_invalid"):
        project_targets.create(hub, "new-app", expected=expected)
    assert not (parent / "new-app").exists()
    assert not (moved / "new-app").exists()


def test_default_missing_parent_ticket_keeps_its_existing_ancestor(places):
    hub, personal = places
    expected = project_targets.ticket(hub, "new-app")
    assert expected.path == personal / "ConductProjects" / "new-app"
    assert expected.ancestors[-1][0] == personal
    target, made_home = project_targets.create(hub, "new-app", expected=expected)
    assert target == expected.path and made_home
    assert target.is_dir()
