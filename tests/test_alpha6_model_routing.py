"""One chain: role-implementer -> claude-dev -> claude-opus-5, end to end.

A model is a DEPLOYMENT fact. It is not in the reusable cycle -- a template that
named one would make a durable demand of every machine that ever ran it, and
`templates/README.md` says why -- and it is not in the runtime, which holds no
model id, no default and no opinion. It lives on the instance in the run's
frozen configuration, beside the adapter binding, which is the other fact of
exactly that kind.

So the chain has three joints and each is a different document:

1. the TEMPLATE binds a role. `role-implementer` is all the shipped cycle says;
2. the run's BINDING assigns that role an instance -- `claude-dev` -- and the
   run's frozen CONFIGURATION says which adapter drives it and which model it
   pins;
3. the ADAPTER puts the vendor's own flag and that value on a command line.

Every one of the three is asserted here against the thing that really carries
it, and the last one against a real spawn's real argv.

**The seam is provider-neutral, and that is tested rather than described.** The
transport joins a flag its PROFILE declares to a value the CONFIGURATION pinned;
it knows no vendor and no model. Two providers spell the flag today, a third --
GLM -- is the next to declare one, and a provider that declares none does not
silently drop the routing: it refuses the action, because a run that used a
model an operator did not configure is worse than a run that did not happen.
"""
from __future__ import annotations

import json

import pytest

from conductor.command.adapters import AdapterRegistry
from conductor.command.adapters.claude_code import (
    MODEL_FLAG,
    PERMISSION_MODE_ARGV,
)
from conductor.command.adapters.base import PreparedAction
from conductor.command.artifacts import ArtifactDocument
from conductor.command.contract_values import ContractError
from conductor.command.contracts import (
    ActionProposal,
    ActionRequest,
    RunEnvelope,
    frozen_config_models,
)
from conductor.command.graph_template import load_template
from conductor.command.http_api import CommandApi, PRODUCT_COMMAND_BUDGET
from conductor.command.http_transport import CommandSession
from conductor.command.run_store import RunStore, snapshot_digest
from conductor.command.runtime import (
    AttemptState,
    Budget,
    Confirmation,
    ControlRuntime,
)

from tests import _fakeclaude, _fakekimi
from tests.test_command_claude_review import _Ids
from tests.test_command_claude_transport import NOW, a_harness
from tests.test_command_http_api import PORT, TOKEN
from tests.test_command_kimi_transport import a_harness as kimi_harness
from tests.test_command_kimi_transport import a_request as _a_kimi_request

RUN_ID = "run-model-routing"
#: The instance the shipped cycle's implementer role is assigned to, and the
#: model this deployment pins for it. Both are the CONFIGURATION's words.
INSTANCE_ID = "claude-dev"
#: The exact id, and a FULL NAME rather than an alias: an alias is defined as
#: "the latest model", so a configuration that said `opus` would mean a
#: different model next release while the journal recorded the same word.
PINNED_MODEL = "claude-opus-5"
IMPLEMENTER_ROLE = "role-implementer"
CONFIG = {
    "cycle": {"id": "default-orbit", "phases": ["do"]},
    "instances": [
        {"id": INSTANCE_ID, "adapter": "claude-code", "model": PINNED_MODEL},
    ],
}
#: The same deployment with the model taken away, so the two are one edit apart
#: and every difference below is that edit's.
UNPINNED = {
    "cycle": CONFIG["cycle"],
    "instances": [{"id": INSTANCE_ID, "adapter": "claude-code"}],
}
ARGUMENTS = {
    "work_item_id": "work-001",
    "instruction_ref": "instr-001",
    "profile": "implement",
    "artifact_refs": [],
    "output_limit_profile": "normal",
}


def _a_dispatch_request() -> ActionRequest:
    """The action the forgery test drives, built once and used twice."""
    return ActionRequest(
        action_id="action-forge", run_id=RUN_ID, attempt_id="attempt-do",
        instance_id=INSTANCE_ID, capability="dispatch", arguments=ARGUMENTS,
        scope=("work",), requested_by="tester", requested_at=NOW,
        idempotency_key="idem-forge", timeout_seconds=60,
        preview_digest="sha256:" + "a" * 64, mode="confirm")



def _dispatch(tmp_path, config=CONFIG, **knobs: str):
    """One real dispatch through the ordinary Confirm runtime.

    The child writes one file, because a dispatch that changed nothing has
    no independent evidence to verify and this module is about the argv it
    was spawned with -- not about what an unverifiable attempt reports.
    """
    values = {_fakeclaude.WRITE_FILE: "implemented.py:routed change", **knobs}
    adapter, root, log = a_harness(tmp_path, **values)
    store = RunStore(root)
    store.create_run(
        RunEnvelope(
            run_id=RUN_ID, cycle_id="default-orbit", created_at=NOW,
            config_digest=snapshot_digest(config), mode="confirm"),
        config)
    proposal = ActionProposal(
        proposal_id="proposal-do", run_id=RUN_ID, attempt_id="attempt-do",
        instance_id=INSTANCE_ID, capability="dispatch", arguments=ARGUMENTS,
        scope=("work",), proposed_by="lane", proposed_at=NOW,
        timeout_seconds=60, rationale="carry out the plan",
        config_digest=snapshot_digest(config))
    store.append(proposal)
    runtime = ControlRuntime(
        store, AdapterRegistry([adapter]), clock=lambda: NOW, ids=_Ids())
    attempt = runtime.execute(runtime.authorize(
        Confirmation(
            confirmation_id="confirmation-do", run_id=RUN_ID,
            proposal_id=proposal.proposal_id,
            preview_digest=proposal.preview_digest, capability="dispatch",
            scope=("work",), config_digest=proposal.config_digest,
            confirmed_by="release-owner", confirmed_at=NOW),
        budget=Budget(max_actions=8, max_action_seconds=3600,
                      max_confirmation_age_seconds=3600)))
    return attempt, store, log


# -- joint 1: the template says a ROLE and nothing about a deployment ----------


def test_the_shipped_cycle_names_a_role_and_carries_no_model_anywhere():
    """The template end of the chain, asserted as an ABSENCE over the document.

    A resource row is `{kind, name}` and `model` is one of the kinds the graph
    contract admits, so nothing structural stops a template from carrying one.
    What stops it is this claim, and it is made over the whole shipped document
    rather than over the rows a reader thought to look at -- a model that
    appeared under some future node would be a durable demand nobody noticed.
    """
    template = load_template("dalio-v2")

    assert IMPLEMENTER_ROLE in template.roles
    acting = [node for node in template.steps()
              if node.capability == "dispatch"]
    assert [node.role_id for node in acting] == [IMPLEMENTER_ROLE]
    for node in template.steps():
        assert all(row.kind != "model" for row in node.resources), node.node_id
    assert "model" not in json.dumps(template.as_dict())


# -- joint 2: the configuration pins it, and absence is not a default ----------


def test_an_explicit_null_model_is_refused_while_an_absent_key_is_not():
    """Optional is not nullable, and this build has paid for the difference.

    An instance that omits `model` is a configuration that said nothing about
    one. An instance that writes `"model": null` is a configuration that chose a
    value, and the value it chose is not a model id. Reading the second as the
    first means a file naming a model WRONGLY runs on whatever the provider's
    own configuration decides, and reports nothing about having done so.

    The same distinction is already burned into `result_artifact_ref`, where an
    omitted field becomes an `OMITTED` sentinel and an explicit null reaches the
    field's own validator and is refused. This is that rule, applied where the
    same shortcut was taken again.

    The WIRE fact is the opposite direction and stays: `/controls` projects an
    instance that pinned none as an explicit `"model": null`, because a consumer
    must be able to tell "pinned none" from "this server cannot say". Refusing a
    null on the way IN and answering one on the way OUT are not in tension --
    one is a configuration a person wrote, the other is a projection this build
    computed.
    """
    absent = {
        "cycle": CONFIG["cycle"],
        "instances": [{"id": INSTANCE_ID, "adapter": "claude-code"}],
    }
    explicit_null = {
        "cycle": CONFIG["cycle"],
        "instances": [
            {"id": INSTANCE_ID, "adapter": "claude-code", "model": None}],
    }

    assert frozen_config_models(absent) == {}
    with pytest.raises(ContractError, match="configured model id"):
        frozen_config_models(explicit_null)


def test_the_frozen_configuration_is_where_a_model_is_pinned():
    """Read off the same snapshot the adapter binding is read off.

    An instance that pins none is ABSENT from the answer rather than present
    with a None: a mapping that carried an entry for every instance would make
    "pins nothing" and "pins the empty string" the same shape to a caller.
    """
    assert frozen_config_models(CONFIG) == {INSTANCE_ID: PINNED_MODEL}
    assert frozen_config_models(UNPINNED) == {}


# -- joint 3: it reaches the vendor's own command line -------------------------


def test_the_pinned_model_reaches_the_claude_cli_as_its_own_flag(tmp_path):
    """The whole point, asserted on a real spawn's real argv.

    The flag and the value stand ADJACENT and in that order, which is what makes
    them one argument rather than two tokens that happen to be present; a test
    asserting only membership would pass a build that sent the value somewhere
    else entirely.
    """
    attempt, _store, log = _dispatch(tmp_path)

    assert attempt.state is AttemptState.SUCCEEDED, attempt.receipt.detail
    spawned = _fakeclaude.prompt_spawns(log)
    assert len(spawned) == 1
    argv = spawned[0]["argv"]
    assert MODEL_FLAG in argv
    assert argv[argv.index(MODEL_FLAG) + 1] == PINNED_MODEL
    # And it stands before the permission mode, where this provider puts it.
    assert argv.index(MODEL_FLAG) < argv.index(PERMISSION_MODE_ARGV[0])


def test_the_version_preflight_is_never_asked_to_load_a_model(tmp_path):
    """A preflight prints a version; a model there would be a model loaded.

    The preflight hands a READY argv rather than a builder, so this is
    structural -- but it is the kind of structure a refactor breaks silently, so
    it is asserted against the spawn that really happened.
    """
    _attempt, _store, log = _dispatch(tmp_path)

    versions = [row for row in _fakeclaude.spawns(log)
                if row["argv"][:1] == ["--version"]]
    assert len(versions) == 1
    assert MODEL_FLAG not in versions[0]["argv"]
    assert PINNED_MODEL not in versions[0]["argv"]


def test_an_unpinned_instance_sends_no_model_flag_at_all(tmp_path):
    """Absence renders as absence. The negative control for every case above.

    Without this, `--model` could be hardcoded in the argv builder and every
    assertion above would still pass.
    """
    attempt, _store, log = _dispatch(tmp_path, config=UNPINNED)

    assert attempt.state is AttemptState.SUCCEEDED, attempt.receipt.detail
    argv = _fakeclaude.prompt_spawns(log)[0]["argv"]
    assert MODEL_FLAG not in argv
    assert PINNED_MODEL not in argv


def test_the_model_is_the_configurations_and_never_the_requests(tmp_path):
    """A model in an action's arguments is not a model this build will send.

    The routing value comes from the run's frozen configuration through the
    registry, and the adapter is handed a request that says nothing about a
    model. A payload that named one would be a caller choosing what an
    operator's configuration is for -- so it reaches no command line, and the
    configuration's own value is what does.
    """
    arguments = dict(ARGUMENTS, profile="implement")
    assert "model" not in arguments
    attempt, _store, log = _dispatch(tmp_path)

    assert attempt.state is AttemptState.SUCCEEDED
    argv = _fakeclaude.prompt_spawns(log)[0]["argv"]
    assert argv.count(MODEL_FLAG) == 1
    assert argv[argv.index(MODEL_FLAG) + 1] == PINNED_MODEL

# -- the seam is neutral, and neutral is not "every vendor is claimed" ---------


def test_a_provider_with_no_reviewed_flag_refuses_rather_than_dropping_it(
        tmp_path):
    """The half of provider-neutrality that costs something.

    Kimi Code declares no `model_flag`, because no reviewed material this build
    read names one. A configuration that pins a model for an instance bound to
    it therefore cannot be honoured, and the honest answer is a refusal BEFORE
    anything is minted, claimed or spawned -- not a run that quietly used
    whatever the vendor's own configuration chose while an operator's file named
    something else.

    The receipt says the product and never the model id: the id is operator
    configuration and this sentence reaches a receipt, the journal and the API.
    """
    adapter, _root, log = kimi_harness(tmp_path)
    assert adapter.profile.model_flag == ""

    receipt = adapter.execute(PreparedAction(
        adapter_id=adapter.manifest.adapter_id,
        request=_a_kimi_request(), adapter_payload=ARGUMENTS,
        model=PINNED_MODEL))

    assert receipt.outcome == "failed"
    assert "no reviewed flag" in receipt.detail
    assert PINNED_MODEL not in receipt.detail
    assert _fakekimi.spawns(log) == [], "NOTHING_MAY_BE_SPAWNED"


def test_the_same_provider_runs_normally_when_no_model_is_pinned(tmp_path):
    """The positive control: the refusal is about the ROUTING, not the provider.

    Without this, a Kimi transport that refused every action at all would pass
    the claim above and look like a working guard.
    """
    adapter, _root, log = kimi_harness(tmp_path)

    receipt = adapter.execute(PreparedAction(
        adapter_id=adapter.manifest.adapter_id,
        request=_a_kimi_request(), adapter_payload=ARGUMENTS))

    assert receipt.outcome != "failed" or "no reviewed flag" not in receipt.detail
    assert _fakekimi.spawns(log) != [], "the unrouted action really ran"

# -- the value is the configuration's, and the routing reaches both roads -----


def test_an_adapter_cannot_name_the_model_it_will_be_run_with(tmp_path):
    """The registry writes this field; a provider only receives it.

    An adapter is arbitrary third-party code from this package's point of view,
    and choosing a model is the one thing an operator's configuration exists
    for. So `prepare` hands the adapter a request that says nothing about a
    model, and whatever the adapter puts in its answer is discarded and
    replaced by the value the caller resolved.

    A forged model would otherwise be free: the adapter builds the
    `PreparedAction` that `execute` is later handed.
    """
    class _Forging:
        manifest = None

        def __init__(self, inner):
            self._inner = inner
            self.manifest = inner.manifest

        def observe(self, instance_id, run_id):
            return self._inner.observe(instance_id, run_id)

        def prepare(self, request):
            answered = self._inner.prepare(request)
            return PreparedAction(
                adapter_id=answered.adapter_id, request=answered.request,
                adapter_payload=answered.adapter_payload,
                model="forged-by-the-adapter")

        def execute(self, prepared):
            return self._inner.execute(prepared)

        def verify(self, request, result):
            return self._inner.verify(request, result)

    adapter, _root, log = a_harness(
        tmp_path, **{_fakeclaude.WRITE_FILE: "implemented.py:routed change"})
    _Forging.argument_schemas = type(adapter).argument_schemas
    registry = AdapterRegistry([_Forging(adapter)])
    request = _a_dispatch_request()

    prepared = registry.prepare(
        adapter.manifest.adapter_id, request, model=PINNED_MODEL)
    registry.execute(adapter.manifest.adapter_id, prepared)

    assert prepared.model == PINNED_MODEL, "the adapter's forgery survived"
    argv = _fakeclaude.prompt_spawns(log)[0]["argv"]
    assert "forged-by-the-adapter" not in argv
    assert argv[argv.index(MODEL_FLAG) + 1] == PINNED_MODEL


def test_a_routed_model_reaches_the_review_road_as_well(tmp_path):
    """Both halves of one cycle run on the model one configuration named.

    Routing that stopped at the dispatch road would leave a reviewer running on
    whatever its provider's own configuration chose, while a single operator
    file described the whole deployment.
    """
    adapter, root, log = a_harness(
        tmp_path, **{_fakeclaude.EMIT_REVIEW: "enabled-review-output"})
    store = RunStore(root)
    store.create_run(
        RunEnvelope(
            run_id=RUN_ID, cycle_id="default-orbit", created_at=NOW,
            config_digest=snapshot_digest(CONFIG), mode="confirm"),
        CONFIG)
    store.append(ArtifactDocument(
        artifact_id="artifact-seed-1", artifact_ref="artifact-brief",
        run_id=RUN_ID, created_at=NOW, media_type="text/markdown",
        content="# Brief\n\nReview this."))
    review_arguments = {
        "work_item_id": "work-001",
        "target_artifact_refs": ["artifact-brief"],
        "result_artifact_ref": "artifact-goal",
        "review_profile": "quality",
    }
    proposal = ActionProposal(
        proposal_id="proposal-review", run_id=RUN_ID,
        attempt_id="attempt-review", instance_id=INSTANCE_ID,
        capability="review", arguments=review_arguments, scope=("work",),
        proposed_by="lane", proposed_at=NOW, timeout_seconds=60,
        rationale="review the brief", config_digest=snapshot_digest(CONFIG))
    store.append(proposal)
    runtime = ControlRuntime(
        store, AdapterRegistry([adapter]), clock=lambda: NOW, ids=_Ids())
    attempt = runtime.execute(runtime.authorize(
        Confirmation(
            confirmation_id="confirmation-review", run_id=RUN_ID,
            proposal_id=proposal.proposal_id,
            preview_digest=proposal.preview_digest, capability="review",
            scope=("work",), config_digest=proposal.config_digest,
            confirmed_by="release-owner", confirmed_at=NOW),
        budget=Budget(max_actions=8, max_action_seconds=3600,
                      max_confirmation_age_seconds=3600)))

    assert attempt.state is AttemptState.SUCCEEDED, attempt.receipt.detail
    argv = _fakeclaude.prompt_spawns(log)[0]["argv"]
    assert argv[argv.index(MODEL_FLAG) + 1] == PINNED_MODEL
    # And it is the READ-ONLY road it reached: the review mode, not acceptEdits.
    assert "plan" in argv and "acceptEdits" not in argv


# -- the Cockpit's one door to the fact ---------------------------------------


def test_the_controls_route_reports_the_model_an_instance_pins(tmp_path):
    """The route a browser joins by identity, answering both states.

    `model` sits beside `adapter_id` because it is the same KIND of fact -- what
    the configuration says about a deployment -- and it appears in no graph
    document, where a plan names roles.

    Both states are driven from ONE run, because a route that answered
    correctly for a pinned model and wrongly for an unpinned one would pass a
    test that only asked about the first.
    """
    config = {
        "cycle": CONFIG["cycle"],
        "instances": [
            {"id": INSTANCE_ID, "adapter": "claude-code",
             "model": PINNED_MODEL},
            {"id": "codex-review", "adapter": "codex"},
        ],
    }
    store = RunStore(tmp_path)
    store.create_run(
        RunEnvelope(
            run_id=RUN_ID, cycle_id="default-orbit", created_at=NOW,
            config_digest=snapshot_digest(config), mode="confirm"),
        config)
    subject = CommandApi(
        store, AdapterRegistry([]), session=CommandSession(PORT, TOKEN),
        budget=PRODUCT_COMMAND_BUDGET, clock=lambda: NOW, ids=_Ids(),
        publish_run=lambda _run_id: None)

    answered = subject.handle(
        "GET", f"/command/runs/{RUN_ID}/controls", (("Host", f"127.0.0.1:{PORT}"),))

    rows = {row["instance_id"]: row for row in answered.payload["instances"]}
    assert rows[INSTANCE_ID]["model"] == PINNED_MODEL
    assert rows[INSTANCE_ID]["adapter_id"] == "claude-code"
    # Pinned NONE, and the key is present with a null rather than absent: an
    # absent key is a server too old to answer, which is a different fact.
    assert rows["codex-review"]["model"] is None
    assert "model" in rows["codex-review"]
