"""The project's pinned cycle (spec 7.10): one file the human writes with one button.

`data_root/project-cycle.json` says which workflow the project's next task starts on, who pinned
it and when. It is the first thing the wizard's preselection reads, so a one-off cycle never
becomes the project's by being the last one run. Judged here without a route: the store on a
real folder, and the two handlers that `flow_routes` gives the routes. What the routes add
(the allowlist, the freezes, the transport) is held with the route-canon commit.
"""
import os

import pytest

from conductor.command import project_cycle, run_files
from conductor.command.api_contracts import ApiRefusal, refusal_from_exception
from conductor.command.contracts import canonical_json
from conductor.command.flow_routes import pin_project_cycle, read_project_cycle
from conductor.command.graph_template import GraphTemplate, load_template
from conductor.command.project_cycle import CorruptPin, PinRecord, ProjectCycleStore
from conductor.command.store_errors import StoreError
from conductor.command.template_store import RouteNotOwned, TemplateStore

ACTOR = "Вы: Василий"
WORKFLOW = "cycle-7c1e5a90"
FIRST, LATER = "2026-09-28T13:50:00Z", "2026-09-28T16:50:00Z"


class Clock:
    def __init__(self, now=FIRST):
        self.now = now

    def __call__(self):
        return self.now


class Project:
    def __init__(self, root):
        self.root = root
        self.pins, self.templates = ProjectCycleStore(root), TemplateStore(root)
        self.clock = Clock()

    def publish(self, workflow_id=WORKFLOW, revision=1):
        document = load_template("desk-short").as_dict()
        self.templates.save(GraphTemplate.from_dict(
            {**document, "template_id": workflow_id, "revision": revision}))

    def pin(self, workflow_id=WORKFLOW, actor=ACTOR):
        return pin_project_cycle(self.pins, self.templates,
                                 {"workflow_id": workflow_id, "actor": actor}, self.clock)

    def read(self):
        status, payload = read_project_cycle(self.pins, self.templates)
        assert status == 200
        return payload

    @property
    def file(self):
        return self.pins.path

    def bytes(self):
        return self.file.read_bytes() if self.file.exists() else None


@pytest.fixture
def project(tmp_path):
    return Project(tmp_path / "project")


def refused_code(call):
    """The word the boundary would say for what the call raised, as `CommandApi.handle` does."""
    with pytest.raises(Exception) as caught:
        call()
    error = caught.value
    return (error if isinstance(error, ApiRefusal) else refusal_from_exception(error)).code


# --- reading -------------------------------------------------------------------------------------


def test_the_pin_read_names_no_pin_when_no_file_stands(project):
    assert project.read() == {"pinned": None}
    assert project.bytes() is None, "a read creates nothing"


def test_the_pin_read_carries_the_workflow_its_latest_revision_the_actor_and_the_time(project):
    project.publish()
    assert project.pin() == (200, {"pinned": {
        "workflow_id": WORKFLOW, "latest_revision": 1, "set_by": ACTOR, "set_at": FIRST}})
    assert list(project.read()["pinned"]) == ["workflow_id", "latest_revision", "set_by", "set_at"]


def test_the_latest_revision_is_read_when_asked_and_a_new_one_moves_no_byte(project):
    project.publish()
    project.pin()
    before = project.bytes()
    project.publish(revision=2)
    assert project.read()["pinned"]["latest_revision"] == 2
    assert project.bytes() == before


def test_a_pin_whose_workflow_has_no_revision_reads_with_a_null_latest_revision(project):
    project.publish()
    project.pin()
    project.file.write_bytes(project.bytes().replace(WORKFLOW.encode(), b"cycle-gone"))
    assert project.read()["pinned"]["latest_revision"] is None


# --- pinning -------------------------------------------------------------------------------------


def test_pin_requires_a_published_workflow_and_null_unpins(project):
    assert refused_code(lambda: project.pin("cycle-none")) == "contract_invalid"
    assert project.bytes() is None, "a refused pin writes nothing"
    project.publish()
    project.pin()
    assert project.read()["pinned"]["workflow_id"] == WORKFLOW
    project.clock.now = LATER
    assert project.pin(None) == (200, {"pinned": None})
    assert project.read() == {"pinned": None}
    unpinned = {"schema_version": 1, "workflow_id": None, "set_by": ACTOR, "set_at": LATER}
    assert project.bytes() == (canonical_json(unpinned) + "\n").encode()


def test_pin_repeat_writes_nothing_and_records_the_actor(project):
    project.publish()
    project.pin()
    before = project.bytes()
    project.clock.now = LATER
    assert project.pin() == (200, {"pinned": {
        "workflow_id": WORKFLOW, "latest_revision": 1, "set_by": ACTOR, "set_at": FIRST}})
    assert project.bytes() == before, "the same pin by the same person moves nothing"
    assert b'"set_by":"' + ACTOR.encode() in before


def test_a_pin_by_another_actor_rewrites_the_record(project):
    project.publish()
    project.pin()
    project.clock.now = LATER
    assert project.pin(actor="Вы: Анна")[1]["pinned"]["set_by"] == "Вы: Анна"
    assert project.read()["pinned"]["set_at"] == LATER


def test_pinning_another_workflow_replaces_the_pin(project):
    project.publish()
    project.publish("cycle-other")
    project.pin()
    project.pin("cycle-other")
    assert project.read()["pinned"]["workflow_id"] == "cycle-other"


def test_unpinning_when_nothing_is_pinned_writes_no_file(project):
    assert project.pin(None) == (200, {"pinned": None})
    assert project.bytes() is None


def test_unpinning_twice_writes_once(project):
    project.publish()
    project.pin()
    project.pin(None)
    before = project.bytes()
    project.clock.now = LATER
    project.pin(None, actor="Вы: Анна")
    assert project.bytes() == before


@pytest.mark.parametrize("body", [
    {}, {"workflow_id": WORKFLOW}, {"actor": ACTOR},
    {"workflow_id": WORKFLOW, "actor": ACTOR, "extra": 1},
    {"workflow_id": 5, "actor": ACTOR}, {"workflow_id": "not an id", "actor": ACTOR},
    {"workflow_id": "", "actor": ACTOR}, {"workflow_id": WORKFLOW, "actor": ""},
    {"workflow_id": WORKFLOW, "actor": "   "}, {"workflow_id": WORKFLOW, "actor": 7},
    {"workflow_id": WORKFLOW, "actor": "a\x00b"}, {"workflow_id": WORKFLOW, "actor": "\ud800"},
    {"workflow_id": None}, [], "text", None])
def test_a_pin_body_is_closed_and_its_actor_is_a_human_identity(project, body):
    project.publish()
    with pytest.raises(ApiRefusal) as refused:
        pin_project_cycle(project.pins, project.templates, body, project.clock)
    assert refused.value.code == "contract_invalid"
    assert project.bytes() is None


# --- the file ------------------------------------------------------------------------------------


def test_the_pin_file_is_canonical_bytes_replaced_atomically_with_no_temporary_left(
        project, monkeypatch):
    replaced = []
    real = os.replace
    monkeypatch.setattr(run_files.os, "replace", lambda a, b: (replaced.append(b), real(a, b))[1])
    project.publish()
    project.pin()
    project.clock.now = LATER
    project.pin(actor="Вы: Анна")
    assert replaced == [project.file, project.file]
    assert project.bytes() == (canonical_json({
        "schema_version": 1, "workflow_id": WORKFLOW, "set_by": "Вы: Анна", "set_at": LATER})
        + "\n").encode("utf-8")
    assert sorted(entry.name for entry in project.file.parent.iterdir()
                  if entry.name.startswith(".") or entry.suffix == ".tmp") == []


def test_the_pin_survives_a_new_store_on_the_same_root(project):
    project.publish()
    project.pin()
    again = Project(project.root)
    assert again.read()["pinned"]["set_by"] == ACTOR


@pytest.mark.parametrize("content", [
    b"not json", b"[]", b'{"schema_version": 1}',
    b'{"schema_version": 2, "workflow_id": null, "set_by": "x", "set_at": "2026-09-28T13:50:00Z"}',
    b'{"schema_version": 1, "workflow_id": "bad id", "set_by": "x",'
    b' "set_at": "2026-09-28T13:50:00Z"}',
    b'{"schema_version": 1, "workflow_id": null, "set_by": "", "set_at": "2026-09-28T13:50:00Z"}',
    b'{"schema_version": 1, "workflow_id": null, "set_by": "x", "set_at": "yesterday"}',
    b'{"schema_version": 1, "workflow_id": null, "set_by": "x", "set_at": "2026-09-28T13:50:00Z",'
    b' "extra": 1}'])
def test_a_corrupt_pin_file_is_a_store_error_naming_no_path(project, content):
    project.publish()
    project.file.parent.mkdir(parents=True, exist_ok=True)
    project.file.write_bytes(content)
    with pytest.raises(CorruptPin) as corrupt:
        project.read()
    assert isinstance(corrupt.value, StoreError) and str(project.file) not in str(corrupt.value)
    assert refusal_from_exception(corrupt.value).code == "store_error"
    assert refused_code(lambda: project.pin()) == "store_error"
    assert project.bytes() == content, "a pin never overwrites a file it cannot read"


def test_a_pin_file_that_is_a_symbolic_link_is_refused_and_its_target_untouched(project, tmp_path):
    project.publish()
    target = tmp_path / "elsewhere.json"
    target.write_bytes(b"{}")
    project.file.parent.mkdir(parents=True, exist_ok=True)
    try:
        project.file.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("this machine will not make a symbolic link")
    with pytest.raises(RouteNotOwned):
        project.read()
    with pytest.raises(RouteNotOwned):
        project.pin()
    assert target.read_bytes() == b"{}"
    assert refused_code(lambda: project.pin()) == "route_unsafe"


def test_a_pin_file_that_is_a_folder_is_refused(project):
    project.file.mkdir(parents=True)
    with pytest.raises(RouteNotOwned):
        project.read()


def test_the_record_is_closed_and_round_trips():
    record = PinRecord(WORKFLOW, ACTOR, FIRST)
    assert PinRecord.from_dict(record.as_dict()) == record
    assert list(record.as_dict()) == ["schema_version", "workflow_id", "set_by", "set_at"]
    with pytest.raises(Exception):
        PinRecord.from_dict({**record.as_dict(), "extra": 1})
