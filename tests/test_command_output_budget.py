"""The output budget a plan names, and the bytes a child is actually allowed.

`output_limit_profile` was the release verdict's own named example of what not
to build: a field declared on every dispatch, validated against a closed
vocabulary, carried in every shipped starter, projected into the panel -- and
read by nothing. `headless_cli._spawn` handed the runner a constant, so `small`
and `normal` produced identical spawns and a step that asked for a smaller
budget got the same one.

`deep_commands.to_runner_spec` still spends a constant, and that is left alone
deliberately: it serves `_DeepAdapter`, the fake-protocol lifecycle fixture, and
no catalogued provider reaches it. Every real transport -- all five -- extends
`ArtifactAwareTransport` -> `HeadlessCliTransport`, which is the road below.

Nothing new was added to close that. The whole chain already existed:

    template node `arguments` -> materialize -> GraphNode.arguments
      -> the proposal the Human confirms -> DeepDispatchArgs (closed schema)
      -> `_dispatch` -> `_attempt` -> `_spawn` -> CommandSpec.output_limit

Only the last hop was missing. This module holds that hop, and holds the rule
it must follow: a plan may ask for LESS and never for more. `HarnessProfile.
output_limit` is what this build's transport for a vendor was reviewed against,
and a bound a requester could widen is not a bound -- exactly the argument
`timeout_seconds` already makes one layer up.

Driven through Kimi because a road needs a vehicle. The road is shared: all
five catalogued transports extend `ArtifactAwareTransport` -> `HeadlessCli
Transport`, and `bounded_output` belongs to `harness_profile`, not to any
provider.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from conductor.command.adapters.deep_commands import (
    OUTPUT_LIMIT_BYTES,
    OUTPUT_LIMIT_PROFILES,
)
from conductor.command.adapters.harness_profile import OUTPUT_LIMIT, bounded_output
from conductor.command.adapters.kimi_code import INSTRUCTION_DIR, KimiCodeAdapter, kimi_pin

from tests.test_command_kimi_transport import (
    INSTRUCTION_BODY,
    NOW,
    _Ids,
    _RecordingRunner,
    _executable,
    a_request,
    run_once,
)

#: What each profile is worth, written here rather than imported from the table
#: under test. The numbers are the independent expectation: a table that changed
#: and a test that followed it would agree about nothing.
EXPECTED_BYTES = {"small": 4 * 1024, "normal": 16 * 1024}


def _bench(tmp_path: Path):
    """One adapter over a recording runner, with an instruction on disk."""
    exe = _executable(tmp_path)
    root = tmp_path / "root"
    root.mkdir()
    (root / INSTRUCTION_DIR).mkdir()
    (root / INSTRUCTION_DIR / "instr-001.md").write_text(
        INSTRUCTION_BODY, encoding="utf-8", newline="\n")
    runner = _RecordingRunner(root)
    adapter = KimiCodeAdapter(
        kimi_pin(str(exe)), runner, root=root, clock=lambda: NOW, ids=_Ids())
    return adapter, runner


def _task_limit(runner) -> int:
    """The budget of the TASK spawn, not the version probe that precedes it.

    The preflight spawns first and names no profile, so reading `specs[0]` would
    measure the probe and pass no matter what a plan asked for.
    """
    assert len(runner.specs) == 2, [tuple(s.argv) for s in runner.specs]
    return runner.specs[1].output_limit


def test_every_profile_the_schema_admits_has_a_byte_count():
    """A word the schema takes and the spawn cannot honour is the defect itself.

    Both directions. The vocabulary is DERIVED from the table now, so this reads
    as a tautology on the current source -- and it is not one on any source
    where somebody spells the vocabulary a second time, which is how the two
    came apart in the first place.
    """
    assert set(OUTPUT_LIMIT_PROFILES) == set(EXPECTED_BYTES)
    assert dict(OUTPUT_LIMIT_BYTES) == EXPECTED_BYTES


@pytest.mark.parametrize("profile", sorted(EXPECTED_BYTES))
def test_the_profile_a_plan_names_reaches_the_child_as_bytes(tmp_path, profile):
    """The hop that was missing, measured on the spec the runner was handed.

    Read off the CommandSpec because that is the only place the number exists
    before a child sees it -- a receipt reports a byte count, not a ceiling, and
    a child cannot report a limit it was never told.
    """
    adapter, runner = _bench(tmp_path)

    receipt = run_once(adapter, a_request(arguments={
        "work_item_id": "work-001", "instruction_ref": "instr-001",
        "profile": "implement", "artifact_refs": [],
        "output_limit_profile": profile}))

    assert receipt.outcome in {"succeeded", "unknown", "failed"}, receipt.outcome
    assert _task_limit(runner) == EXPECTED_BYTES[profile]


def test_the_two_profiles_do_not_produce_the_same_spawn(tmp_path):
    """The defect stated as an equality, so a constant cannot pass this module.

    Every other test here would still pass against a build that answered one
    number for both words, as long as that number happened to match. This one
    cannot: it asks whether naming a different profile changes anything at all.
    """
    limits = {}
    for profile in ("small", "normal"):
        adapter, runner = _bench(tmp_path / profile)
        run_once(adapter, a_request(arguments={
            "work_item_id": "work-001", "instruction_ref": "instr-001",
            "profile": "implement", "artifact_refs": [],
            "output_limit_profile": profile}))
        limits[profile] = _task_limit(runner)

    assert limits["small"] < limits["normal"], limits


def test_a_plan_may_ask_for_less_and_never_for_more():
    """The ceiling rule, on the function that decides it.

    `HarnessProfile.output_limit` is what this build's transport for a vendor
    was reviewed against. A plan asking for more must not get it, or the reviewed
    bound belongs to whoever writes the workflow.
    """
    class _Profile:
        output_limit = OUTPUT_LIMIT

    profile = _Profile()
    assert bounded_output(profile, OUTPUT_LIMIT // 4) == OUTPUT_LIMIT // 4
    assert bounded_output(profile, OUTPUT_LIMIT * 99) == OUTPUT_LIMIT
    assert bounded_output(profile, OUTPUT_LIMIT) == OUTPUT_LIMIT


def test_a_spawn_no_plan_spoke_for_keeps_the_providers_own_limit():
    """The over-correction control, and it is the reason `None` is a value.

    A review, a version probe and every other spawn name no profile. They must
    behave exactly as they did before a profile meant anything -- a rewrite that
    made the plan's budget mandatory would silently re-bound roads no plan is
    talking about.
    """
    class _Profile:
        output_limit = 12345

    assert bounded_output(_Profile(), None) == 12345


def test_the_version_probe_is_not_bounded_by_the_task_budget(tmp_path):
    """The preflight runs before any task and answers to the provider alone.

    A plan naming `small` must not shrink the buffer the version probe reads
    the vendor's own version string into: the two spawns are different questions
    and only one of them is the plan's business.
    """
    adapter, runner = _bench(tmp_path)

    run_once(adapter, a_request(arguments={
        "work_item_id": "work-001", "instruction_ref": "instr-001",
        "profile": "implement", "artifact_refs": [],
        "output_limit_profile": "small"}))

    assert runner.specs[0].output_limit == OUTPUT_LIMIT
    assert runner.specs[1].output_limit == EXPECTED_BYTES["small"]
