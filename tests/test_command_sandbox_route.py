"""What a step demands of the machine that runs it, and who finally reads it.

A `sandbox` resource has been storable since graphs existed and was spent by
nobody: a plan could name any route-shaped word and the run proceeded exactly
as if it had named none. That is the lie this closes, and the shape of the
closing is chosen so that nothing already written becomes unreadable.

Four claims carry it:

- **one word, and it names what this build really enforces.** `project-root`
  is the boundary `containment.assess_cwd_route` anchors its walk to, not the
  directory a child stands in -- the child's cwd is `work/<work_item_id>`,
  chosen from the capability's own argument. What the demand buys is the walk:
  `os.lstat`, refusing a symlink, a junction, a reparse point, a hard link, a
  `..` segment, or anything not strictly beneath the root.
- **the refusal is before the spawn, at two doors, in two sentences.** Opening
  a run on such a plan is refused where a run is created; authorizing an
  attempt is refused where an attempt is authorized. Each witness below asks
  for its own door's words, because two doors saying one sentence is one door
  wearing two names -- the lesson the failure-policy slice paid for.
- **the contract is untouched.** `GraphResource` still admits any id-shaped
  name, so no shipped document moves a byte and a journal already carrying an
  unprovidable route still REPLAYS. It simply authorizes nothing. Refusing in
  the contract would turn a plan this build cannot honour into a journal nobody
  can read, which is a worse answer to the same problem.
- **only `sandbox` is judged.** The other five kinds are recorded and consumed
  by nothing, so they accept any name and refuse nobody. Refusing a name
  nothing reads would be inventing a promise about it. The asymmetry is held in
  both directions, because a build that judged all six would look identical on
  every test that only ever tried a sandbox row.
"""
from __future__ import annotations

import json

import pytest

from conductor.command.containment import (
    SANDBOX_KIND,
    SANDBOX_ROUTES,
    RouteViolationCode,
    unprovidable_sandboxes,
)
from conductor.command.graph_definition import (
    RESOURCE_KINDS,
    GraphDefinition,
    GraphNode,
    GraphResource,
)
from conductor.command.graph_schedule import schedule
from conductor.command.run_store import RunStore, snapshot_digest
from tests.test_command_run_store import CONFIG, a_run

NOW = "2026-09-01T10:00:00Z"
RUN_ID = "run-001"
#: The run id `tests.test_command_run_routes` opens through the real HTTP
#: boundary. Imported by value rather than re-spelled would be better; it
#: is a module constant there and this is the one fact this file needs.
STUDIO_RUN = "run-studio-001"
#: Every attachment kind this build records and does nothing with.
INERT_KINDS = tuple(sorted(RESOURCE_KINDS - {SANDBOX_KIND}))
#: Names no list in this build carries. An inert kind takes them; a sandbox
#: row does not.
STRANGE_NAMES = ("docker", "firejail", "project-root.old", "none", "seccomp")


def a_node(*, resources=(), node_id="check") -> GraphNode:
    return GraphNode(
        node_id=node_id, kind="task", title="Check it",
        instance_id="claude-dev", capability="review",
        arguments={"work_item_id": "work-1",
                   "target_artifact_refs": ["artifact-brief"],
                   "result_artifact_ref": "artifact-verdict",
                   "review_profile": "quality"},
        resources=tuple(resources))


def a_plan(*, resources=()) -> GraphDefinition:
    return GraphDefinition(
        graph_id="graph-route", run_id=RUN_ID, created_at=NOW,
        nodes=(a_node(resources=resources),), edges=())


def sandbox(name: str) -> GraphResource:
    return GraphResource(kind=SANDBOX_KIND, name=name)


# -- 1. the vocabulary, and what it names -------------------------------------


def test_the_vocabulary_is_one_route_and_it_is_the_one_the_walk_anchors_to():
    """Both directions. A word LEAVING would make every plan that names it
    unrunnable; a word ARRIVING would promise a route nothing provides."""
    assert SANDBOX_ROUTES == frozenset({"project-root"})
    assert SANDBOX_KIND == "sandbox" and SANDBOX_KIND in RESOURCE_KINDS


def test_the_route_this_word_names_is_the_boundary_the_walk_refuses_to_leave():
    """The name is not decoration: `assess_cwd_route` really is anchored at the
    project root, and really does refuse each way out of it.

    Asked of the enforcing function rather than of a comment, and asked in both
    directions, so a build whose walk stopped refusing would red here even
    though the vocabulary above still read correctly.
    """
    from conductor.command.containment import assess_cwd_route

    root = __import__("pathlib").Path(r"C:\project").resolve()
    inside, ok = assess_cwd_route(root, "work/item-1")
    assert ok is None or ok.code is RouteViolationCode.MISSING, ok
    assert str(inside).startswith(str(root))

    _, escaped = assess_cwd_route(root, "..")
    assert escaped is not None
    assert escaped.code in {RouteViolationCode.OUTSIDE_ROOT,
                            RouteViolationCode.PARENT_TRAVERSAL}
    _, itself = assess_cwd_route(root, ".")
    assert itself is not None
    assert itself.code is RouteViolationCode.ROOT_NOT_DESCENDANT


# -- 2. the reading, and the asymmetry between the kinds ----------------------


def test_the_route_this_build_provides_is_demanded_freely():
    assert unprovidable_sandboxes((sandbox("project-root"),)) == ()
    assert unprovidable_sandboxes(()) == ()


@pytest.mark.parametrize("name", STRANGE_NAMES)
def test_a_route_this_build_cannot_give_is_named_as_unprovidable(name):
    assert unprovidable_sandboxes((sandbox(name),)) == (name,)


def test_every_unprovidable_route_is_named_once_in_the_order_declared():
    """A person fixing a step wants their own list back, not a set.

    The routes are declared in an order that is NOT their sorted one. A first
    draft used `docker, project-root, firejail, docker`, whose answer is
    `(docker, firejail)` sorted or unsorted -- so a build that sorted its
    answer survived it. The second slice in a row to make that mistake, and the
    lesson is the same one: a fixture whose order is accidentally sorted proves
    nothing about order.
    """
    demanded = (sandbox("zebra"), sandbox("project-root"),
                sandbox("alpha"), sandbox("zebra"))

    assert unprovidable_sandboxes(demanded) == ("zebra", "alpha")


@pytest.mark.parametrize("kind", INERT_KINDS)
@pytest.mark.parametrize("name", ["docker", "sonnet", "anything-at-all"])
def test_a_kind_this_build_does_not_spend_accepts_any_name(kind, name):
    """The first half of the asymmetry: five kinds are recorded and inert, so
    they are judged by nobody. A build that judged all six would pass every
    test above and refuse a `model: sonnet` row nothing reads."""
    assert unprovidable_sandboxes((GraphResource(kind=kind, name=name),)) == ()


def test_the_asymmetry_holds_on_one_step_carrying_both():
    """And the second half, on one node, so this is about the KIND rather than
    about which fixture was reached for."""
    mixed = (GraphResource(kind="model", name="docker"),
             GraphResource(kind="filesystem", name="docker"),
             sandbox("docker"))

    assert unprovidable_sandboxes(mixed) == ("docker",)
    # The same word under three kinds, and exactly one of them is refused.
    assert a_node(resources=mixed).resources == mixed


# -- 3. the contract is untouched ---------------------------------------------


@pytest.mark.parametrize("name", STRANGE_NAMES)
def test_the_node_contract_still_stores_a_route_it_cannot_provide(name):
    """The design's own load-bearing choice, stated as a witness.

    A contract refusal would be stronger and is deliberately not taken: it
    would make an existing journal carrying such a row UNREADABLE, turning a
    plan this build cannot honour into a run nobody can open at all. The row is
    stored, replays, and is refused where an attempt would be made.
    """
    node = a_node(resources=(sandbox(name),))

    assert node.resources[0].name == name
    assert node.as_dict()["resources"] == [{"kind": "sandbox", "name": name}]
    assert GraphNode.from_dict(node.as_dict()) == node


@pytest.mark.parametrize("starter", ["dalio-v1", "dalio-v2", "dalio-v3"])
def test_the_shipped_starters_demand_only_the_route_this_build_provides(starter):
    """The compatibility measurement, on the bytes that really ship."""
    from conductor.command.graph_template import load_template

    template = load_template(starter)
    for node in template.nodes:
        assert unprovidable_sandboxes(node.resources) == (), node.node_id


def test_the_shipped_dalio_really_does_carry_one_and_this_is_not_vacuous():
    """The control on the measurement above: a starter with no sandbox row at
    all would satisfy it while proving nothing."""
    from conductor.command.graph_template import load_template

    rows = [row for node in load_template("dalio-v3").nodes
            for row in node.resources if row.kind == SANDBOX_KIND]

    assert [row.name for row in rows] == ["project-root"]


def test_a_route_demand_changes_no_schedule_and_no_digest():
    """It is a demand on the MACHINE, not on the plan's shape: the step stands
    where it stood, and a plan naming the providable route digests as one
    naming none plus that row and nothing else."""
    bare, demanding = a_plan(), a_plan(resources=(sandbox("project-root"),))

    assert schedule(bare, ()).state_of("check") == "runnable"
    assert schedule(demanding, ()).state_of("check") == "runnable"
    assert schedule(bare, ()).run_state == schedule(demanding, ()).run_state
    assert bare.digest() != demanding.digest()
    assert [{k: v for k, v in row.items() if k != "resources"}
            for row in demanding.as_dict()["nodes"]] == [
        {k: v for k, v in row.items() if k != "resources"}
        for row in bare.as_dict()["nodes"]]


# -- 4. the first door: a run is not opened on a plan this build cannot honour -


def _a_workflow_demanding(name: str) -> dict:
    """The publishable fixture document, with the `do` step's route changed.

    The title moves with the route, and it has to: the publish road refuses a
    revision whose bytes are the one already standing, and the fixture's own
    `do` step already demands `project-root`. Without this the control below
    would be refused for saying nothing new -- a true refusal about a different
    rule, which would have looked exactly like the one under test.
    """
    from tests.test_command_workflow_draft import a_document

    document = a_document(title=f"Route {name}")
    for node in document["nodes"]:
        if node["node_id"] == "do":
            node["resources"] = [{"kind": SANDBOX_KIND, "name": name}]
    return document


def _opened(tmp_path, document: dict):
    """Publish that workflow and try to open a run on it."""
    from tests.test_command_run_routes import a_project
    from tests.test_command_run_routes import a_run as a_body
    from tests.test_command_workflow_draft import WORKFLOW
    from tests.test_command_workflow_routes import post

    subject, store, _templates, events = a_project(tmp_path)
    published = post(subject, f"/command/workflows/{WORKFLOW}/revisions",
                     {"revision": 2, "document": document})
    assert published.status in {200, 201}, published.payload
    answered = post(subject, "/command/runs", a_body(revision=2))
    return answered, store, events


def test_opening_a_run_on_an_unprovidable_route_is_refused_and_writes_nothing(
        tmp_path):
    """The FIRST door, in its own words, and it is the earliest one there is.

    Nothing is created, so there is no run to explain afterwards and no receipt
    that has to describe a step that was never attempted. The refusal names the
    STEP and the routes, both of which came out of the caller's own document.
    """
    from conductor.command.api_contracts import ERROR_STATUS

    answered, store, events = _opened(tmp_path, _a_workflow_demanding("docker"))

    assert answered.status == ERROR_STATUS["service_refused"]
    error = answered.payload["error"]
    assert error["code"] == "service_refused"
    # Its OWN sentence. The authorize door's words are asserted ABSENT, because
    # two doors answering in one sentence is one door wearing two names.
    assert "demands sandbox route" in error["message"], error
    assert "docker" in error["message"], error
    assert "this build does not provide" in error["message"], error
    assert "no attempt may be authorized" not in error["message"], error
    assert error["detail"]["node_id"] == "do"
    # ONE route, not a list: a refusal detail is a reviewed fact -- a safe id
    # or a counting number -- because it is rendered into a browser. The
    # boundary refuses a list-valued detail at construction, which is what
    # decided this shape.
    assert error["detail"]["sandbox"] == "docker"
    assert events == []
    with pytest.raises(Exception):
        store.read(STUDIO_RUN)


def test_the_same_road_opens_the_run_when_the_route_is_one_this_build_gives(
        tmp_path):
    """The discriminating control, one edit away: the SAME document with the
    providable route opens normally. Without it every assertion above would
    also pass on a build that refused every run carrying any sandbox row."""
    answered, store, events = _opened(
        tmp_path, _a_workflow_demanding("project-root"))

    assert answered.status == 201, answered.payload
    assert events == [STUDIO_RUN]
    assert [row.kind for row in store.read(STUDIO_RUN).records] == [
        "graph_definition"]


# -- 5. the second door: an attempt is not authorized on one either -----------


def _run_following(tmp_path, plan: GraphDefinition):
    store = RunStore(tmp_path)
    store.create_run(
        a_run(run_id=RUN_ID, mode="confirm",
              config_digest=snapshot_digest(CONFIG)), CONFIG)
    store.append(plan)
    return store


class _As:
    """The one fact the eligibility holds read off a proposal."""

    def __init__(self, node_id: str) -> None:
        self.node_id = node_id


def test_authorizing_an_attempt_on_an_unprovidable_route_is_refused(tmp_path):
    """The SECOND door, in ITS own words.

    It exists for the runs the first door cannot reach: a run opened before
    this rule, or a plan written onto a run by another road. This drives
    exactly that -- the plan is appended to a store directly, so no run-open
    refusal ever ran, and the attempt is still refused.
    """
    from conductor.command.authorize_holds import _hold_node_sandbox_is_provided
    from conductor.command.runtime_values import AuthorizationError

    store = _run_following(tmp_path, a_plan(resources=(sandbox("docker"),)))

    with pytest.raises(AuthorizationError) as refusal:
        _hold_node_sandbox_is_provided(_As("check"), store.read(RUN_ID))

    said = str(refusal.value)
    assert "demands sandbox route(s)" in said and "docker" in said, said
    # The authorize door answers about EVERY unprovidable route at once. It is
    # not a browser-rendered detail -- it is an authorization refusal a caller
    # reads whole -- so it has no reason to answer one at a time, and the two
    # doors differing here is a fact about where each one is read.
    # Its OWN half of the sentence, which the run-open door does not say.
    assert "no attempt may be authorized for it" in said, said
    assert "step 'check'" in said, said


def test_the_same_door_authorizes_the_route_this_build_provides(tmp_path):
    """The control on the second door, on the same journal shape."""
    from conductor.command.authorize_holds import _hold_node_sandbox_is_provided

    store = _run_following(tmp_path,
                           a_plan(resources=(sandbox("project-root"),)))

    assert _hold_node_sandbox_is_provided(
        _As("check"), store.read(RUN_ID)) is None


@pytest.mark.parametrize("kind", INERT_KINDS)
def test_neither_door_refuses_a_kind_this_build_does_not_spend(kind, tmp_path):
    """The asymmetry at the doors, which is where it would be felt.

    A `model: docker` row is stored, materialized, and refused by nobody. A
    build that judged all six kinds would refuse this run while every assertion
    about `sandbox` above went on passing.
    """
    from conductor.command.authorize_holds import _hold_node_sandbox_is_provided

    store = _run_following(tmp_path, a_plan(
        resources=(GraphResource(kind=kind, name="docker"),)))

    assert _hold_node_sandbox_is_provided(
        _As("check"), store.read(RUN_ID)) is None


# -- 6. the forged journal, whose two halves are deliberately different -------


def _demanding_docker(line: str) -> str:
    """One journal line with every sandbox demand in it rewritten, canonically."""
    row = json.loads(line)
    rows = (row["record"]["nodes"]
            if row["record_type"] == "graph_definition" else ())
    for res in (res for node in rows for res in node.get("resources", [])):
        if res["kind"] == SANDBOX_KIND:
            res["name"] = "docker"
    return json.dumps(row, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"))


def test_a_forged_plan_naming_an_unprovidable_route_still_replays(tmp_path):
    """The half this design chose, and the half it deliberately did not.

    A journal forged to demand a route this build cannot give is READABLE. That
    is the point: the contract admits any id-shaped name, so the run opens, the
    records replay, and the plan is exactly what was written. Refusing here
    would turn a plan this build cannot honour into a journal nobody can read,
    and a person whose run is already open would lose the ability to look at it
    at all.
    """
    store = _run_following(tmp_path,
                           a_plan(resources=(sandbox("project-root"),)))
    path = store.run_path(RUN_ID) / "records.jsonl"
    forged = [_demanding_docker(line)
              for line in path.read_text(encoding="utf-8").splitlines()]
    path.write_text("\n".join(forged) + "\n", encoding="utf-8", newline="\n")

    recovered = RunStore(tmp_path).read(RUN_ID)

    assert recovered.warnings == (), recovered.warnings
    assert [row.kind for row in recovered.records] == ["graph_definition"]
    demanded = recovered.records[0].value.nodes[0].resources
    assert [row.name for row in demanded] == ["docker"]


def test_and_the_forged_run_then_authorizes_nothing_at_all(tmp_path):
    """The other half, and it is where the refusal was moved to.

    Replaying is not honouring. The very journal the test above proves readable
    authorizes no attempt for the step that demands the route, which is what
    "refused before the spawn" means once the contract is left alone.
    """
    from conductor.command.authorize_holds import _hold_node_sandbox_is_provided
    from conductor.command.runtime_values import AuthorizationError

    store = _run_following(tmp_path, a_plan(resources=(sandbox("docker"),)))
    recovered = RunStore(tmp_path).read(RUN_ID)

    assert recovered.warnings == ()
    with pytest.raises(AuthorizationError, match="does not provide"):
        _hold_node_sandbox_is_provided(_As("check"), recovered)


def test_the_second_door_is_asked_on_the_road_that_authorizes_an_attempt(
        tmp_path):
    """WRITTEN AGAINST A GREEN SURVIVOR: the hold, through its caller.

    Every witness above calls `_hold_node_sandbox_is_provided` directly, so
    deleting its CALL SITE left them all green while no attempt was ever judged
    -- a rule that is perfect and unreachable. `_hold_plan_admits` is the one
    place the plan's holds are asked, and this asks through it.
    """
    from conductor.command.authorize_holds import _hold_plan_admits
    from conductor.command.runtime_values import AuthorizationError

    store = _run_following(tmp_path, a_plan(resources=(sandbox("docker"),)))

    with pytest.raises(AuthorizationError, match="does not provide"):
        _hold_plan_admits(_As("check"), store.read(RUN_ID))


def test_a_run_that_follows_no_plan_is_judged_by_neither_door(tmp_path):
    """The early return, which nothing above reached.

    Runs without a graph existed before graphs did and they still do: there is
    no plan to carry a demand, so there is nothing to refuse. The mutation that
    removed this arm crashed on `None` and every sandbox witness stayed green,
    because all of them hand it a plan.
    """
    from conductor.command.authorize_holds import _hold_node_sandbox_is_provided

    store = RunStore(tmp_path)
    store.create_run(
        a_run(run_id=RUN_ID, mode="confirm",
              config_digest=snapshot_digest(CONFIG)), CONFIG)

    assert _hold_node_sandbox_is_provided(
        _As("check"), store.read(RUN_ID)) is None


def test_a_proposal_naming_no_step_is_judged_by_neither_door(tmp_path):
    """The other half of that arm, on a run that DOES follow a plan.

    Whether an unbound proposal may be made at all is `_hold_node_is_eligible`'s
    question and it answers it; this door has no opinion, because a demand
    belongs to a step and this proposal names none. Refusing here would be a
    second, differently-worded answer to somebody else's question.
    """
    from conductor.command.authorize_holds import _hold_node_sandbox_is_provided

    store = _run_following(tmp_path, a_plan(resources=(sandbox("docker"),)))

    assert _hold_node_sandbox_is_provided(
        _As(None), store.read(RUN_ID)) is None


def test_a_proposal_naming_a_step_this_plan_does_not_draw_is_left_alone(
        tmp_path):
    """And the third way this door can be asked about nothing.

    A stranger's id is `_hold_node_is_eligible`'s refusal to make -- it calls
    such a step `unreachable` and says which steps are runnable. This door
    passes over it rather than inventing a second sentence about it.
    """
    from conductor.command.authorize_holds import _hold_node_sandbox_is_provided

    store = _run_following(tmp_path, a_plan(resources=(sandbox("docker"),)))

    assert _hold_node_sandbox_is_provided(
        _As("no-such-step"), store.read(RUN_ID)) is None
