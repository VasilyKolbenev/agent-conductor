"""CLI-only dispatch preview: create a run, propose one dispatch, inspect it.

This is the Day-1 control-loop gate. It creates or opens a run with a frozen
config, asks the fixed CommandService for one dispatch ActionProposal bound to a
configured instance, and returns the canonical preview with its preview_digest
for inspection. It prepares nothing, executes nothing, and spawns no process:
the proposal seam is upstream of preparation, and this module never crosses it.

The scenario is fixed and self-contained so the preview is reproducible: the same
frozen config, the same deterministic ids and clock, and the same request every
time, which is what lets a reader trust the printed preview_digest. What a caller
chooses is only the instance (and, to exercise the binding, the adapter it claims
drives that instance) -- and neither is trusted over the frozen config: an unknown
instance or a mismatched adapter is refused by the same seam MAJOR-1 fixed.

The run directory is state too, and it is trusted no further. The preview's run
id is fixed, so a run at that identity may be one this command never created; it
is replayed and checked before a single record is appended, and a run that
disagrees on any point is refused with its history untouched. Three things are
held: the durable envelope and the frozen configuration against the constants
below, and the run's own recorded history against what this preview would have
written into it. That third check is here because the preview's history is
entirely predictable -- nothing yet, or the one immutable proposal this preview
mints -- so anything else in the journal or in `decisions/` is a history the
preview never wrote and must not append to. Reopening the preview's own run
stays free: the proposal is immutable and identical, so the store recognises the
retry and writes nothing.

A fourth thing is held, and it is held over the run's own durable bytes rather
than over any fact the replay states: nothing unjudged may be lying in the run
directory. `RunStore.read` warns instead of repairing -- a journal ending
mid-record keeps those bytes where they lie and they appear in no replayed
record -- so a run can replay as a history this preview is allowed to resume
while still carrying bytes nobody has judged. Appending would send them through
the repairing store, which truncates them: durable bytes this preview never
wrote, deleted by it. So ANY warning refuses the run. No incomplete tail is
adopted as the preview's own, not even one that is a byte prefix of the record
this preview would itself have written, because a tail is evidence of what some
writer intended and never of which writer it was.

A warning is only the half of that the store can see. `read` opens four names --
`run.json`, `config.json`, `records.jsonl` and `decisions/*.json` -- so a
`.records.jsonl.<rand>.tmp`, the residue of a writer that died inside its own
publish, replays as a flawless history with nothing at all to report. Any other
name under the run directory, a symbolic link included, refuses it too, on the
same ground and without a warning to announce it: this preview did not put that
object there and cannot say whether whoever did is finished with it.

The price is real, it is not hidden, and it is not one price. An object the
store does not own is clutter with a name: the run beneath it is whole, so the
refusal names that object, and moving or deleting exactly it -- and nothing else
-- opens the run again holding every record it already held. A run whose own
replay disagrees is the dead end: a foreign envelope, a foreign frozen config, a
history this preview never wrote, or an incomplete tail, which the journal is
not repaired of here. Such a run can never be opened by this preview again, and
what must move is the whole run -- `conductor/runs/preview-run` beneath whatever
`--dir` names, e.g. `mv ./conductor/runs/preview-run ./preview-run.kept` or
`rm -r ./conductor/runs/preview-run` (PowerShell:
`Remove-Item -Recurse .\\conductor\\runs\\preview-run`) -- after which the
preview creates the run afresh. Neither road is mended by waiting or by
rerunning: this preview repairs nothing and promises nothing. The refusal names
the object to move by its full path on both roads for exactly that reason: a
dead end nobody is told about is a bug of its own.
"""
from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .adapters import (
    AdapterContractError,
    AdapterManifest,
    AdapterObservation,
    AdapterRegistry,
)
from .contracts import RunEnvelope, _freeze_json, canonical_json
from .run_store import (
    RecoveredRun,
    RunExists,
    RunStore,
    StoredRecord,
    StoreError,
    snapshot_digest,
)
from .service import CommandService, ServiceError

#: The one frozen configuration the preview run pins. Its instances section is the
#: authority the service derives each instance's adapter from.
FROZEN_CONFIG: Mapping[str, Any] = {
    "cycle": {"id": "preview-orbit", "phases": ["dispatch"]},
    "instances": [
        {"id": "claude-dev", "adapter": "claude-code"},
    ],
}

#: The instance the preview proposes against unless the caller names another.
DEFAULT_INSTANCE = "claude-dev"

#: The frozen configuration in the shape `RunStore` replays a stored one, so a
#: found run's durable configuration can be compared against this module's own
#: constant directly, structure to structure, and not through its digest alone.
_REPLAYED_FROZEN_CONFIG = _freeze_json(dict(FROZEN_CONFIG))

_RUN_ID = "preview-run"
_ATTEMPT_ID = "preview-attempt"
_NOW = "2026-08-11T00:00:00Z"
_ARGUMENTS: Mapping[str, Any] = {"handoff": "preview-packet"}
_SCOPE = ("src",)
_PROPOSED_BY = "preview"
_RATIONALE = "Day-1 preview: propose one dispatch and inspect its canonical form."
_TIMEOUT_SECONDS = 900


def _preview_id(purpose: str) -> str:
    """Mint every id this preview uses; deterministic, so its own history is known."""
    return f"{purpose}-{_RUN_ID}"


#: How `_history` names the one record a completed preview run holds.
_OWN_LINE = f"action_proposal {_preview_id('proposal')!r}"

#: Every history the preview may find in a run it may reopen: nothing appended
#: yet, or exactly the one proposal line this very preview mints. There is no
#: third, because the preview writes nothing else and never runs a gate.
_OWN_HISTORIES: tuple[tuple[str, ...], ...] = ((), (_OWN_LINE,))


class PreviewError(RuntimeError):
    """The preview flow cannot produce a proposal to inspect."""


class _PreviewAdapter:
    """A minimal registered adapter for the preview; it never prepares or executes.

    It exists so the registry can judge the bound adapter's declared capabilities.
    Its prepare/execute/verify seams are present because registration requires
    them, and they refuse outright: the preview never reaches preparation.
    """

    def __init__(self) -> None:
        self.manifest = AdapterManifest(
            adapter_id="claude-code", display_name="Claude Code", vendor="Anthropic",
            version="1", capabilities=("observe", "dispatch"), docs_url="")

    def observe(self, instance_id: str, run_id: str) -> AdapterObservation:
        return AdapterObservation(
            adapter_id="claude-code", instance_id=instance_id, run_id=run_id,
            observed_at=_NOW, health="ready", available_capabilities=("observe", "dispatch"))

    def prepare(self, request: Any) -> Any:
        raise PreviewError("the preview never prepares an action")

    def execute(self, prepared: Any) -> Any:
        raise PreviewError("the preview never executes an action")

    def verify(self, request: Any, result: Any) -> Any:
        raise PreviewError("the preview never verifies an action")


_ABSENT: Any = object()
"""Stands for a key a row does not carry, which `None` cannot stand for."""


def _field_for_message(row: Mapping[str, Any], name: str) -> str:
    """Render one field for the refusal message, saying `absent` when it is missing.

    Unlike `conductor.doctor._shown`, which closes every value it renders, the
    word `absent` is deliberately bare: it is this function speaking about the
    row, not a value quoted out of it, and a stored string `"absent"` renders
    as `'absent'` so the two can never be read for one another.
    """
    value = row.get(name, _ABSENT)
    return "absent" if value is _ABSENT else repr(value)


def _history(records: tuple[StoredRecord, ...]) -> tuple[str, ...]:
    """Name a run's records in durable order, identifying a proposal by its id."""
    return tuple(
        f"{row.kind} {row.value.proposal_id!r}" if row.kind == "action_proposal"
        else row.kind
        for row in records)


#: The only names `RunStore.read` opens directly beneath a run directory.
_STORE_OWNED_FILES = frozenset({"run.json", "config.json", "records.jsonl"})

#: The one directory the store owns, and the only suffix it reads inside it.
_RECEIPTS_DIR, _RECEIPT_SUFFIX = "decisions", ".json"


def _unowned_files(run_path: Path) -> tuple[str, ...]:
    """Name every durable object under the run directory the run store does not own.

    A real directory is not named: it holds no bytes, so an empty one is adopted
    with the run for want of anything to judge, and a file inside one is reached
    by this walk under its own relative name. A symbolic link IS named, whatever
    it points at and whether or not the target is there: `is_file` answers False
    for a link to a directory and for a dangling one, so a walk filtered on it
    would step past the two objects this preview can judge least -- a link leads
    somewhere this command never looked. The `decisions/` check is on the parent
    rather than on the path's first part, so a receipt-looking name nested deeper
    than the store ever writes is still named here.
    """
    receipts = run_path / _RECEIPTS_DIR
    unowned = []
    for path in sorted(run_path.rglob("*")):
        if path.is_dir() and not path.is_symlink():
            continue
        name = path.relative_to(run_path).as_posix()
        owned = (
            name in _STORE_OWNED_FILES
            or (path.parent == receipts and path.suffix == _RECEIPT_SUFFIX))
        if not owned:
            unowned.append(name)
    return tuple(unowned)


def _unowned_entries(unowned: tuple[str, ...]) -> tuple[str, ...]:
    """Name the durable objects that reach this preview without a warning at all.

    `read` opens four names, so a `.records.jsonl.<rand>.tmp` left by a writer
    that crashed inside its own publish replays as a flawless history with
    nothing whatever to report. Each is named on the ground a crash tail is named
    -- this preview did not put it there and cannot say whether whoever did is
    finished with it -- and each differs from a tail in what it costs: the run
    underneath is whole, so lifting exactly these objects out is the whole
    remedy, which is why `_remedy` is told which of them were found.
    """
    return tuple(
        f"files: {name!r} is not a name this run's store writes, so only whoever "
        "put it there can say whether it is finished"
        for name in unowned)


def _remedy(run_path: Path, unowned: tuple[str, ...], irresolvable: bool) -> str:
    """Name the object a human must move or delete, and name only the true one.

    There are two costs here and they are not one cost. An object the store does
    not own is clutter with a name: the run under it is whole, so that object is
    named and moving or deleting exactly it -- and nothing else -- leaves a run
    this preview opens again holding every record it already held. A run the
    replay itself disagrees with is the dead end: a foreign envelope, a foreign
    frozen config, a history this preview never wrote, or a journal ending
    mid-record that nothing in this module repairs. There the object is the whole
    preview run, and only there; charging the first road that price tells a human
    to destroy proposal records nothing ever put in question.

    Deleting is never the only way through. Moving the object aside satisfies
    both roads, and a human is not asked to destroy durable bytes to get moving.
    Neither sentence promises a repair, because there is none to promise: this
    preview mends nothing, so rerunning either road untouched refuses it again.
    """
    if irresolvable:
        return (
            "remedy: nothing here resolves any of those, so this run will never "
            f"open here again; move or delete the whole preview run {run_path} by "
            "hand, then rerun the preview, which creates a fresh one")
    return (
        "remedy: only whoever put them there can resolve those, and this preview "
        f"will not; move or delete exactly {', '.join(map(repr, unowned))} out of "
        f"{run_path} by hand, then rerun the preview, which opens this run again "
        "with every record it already holds")


def _irresolvable_differences(
        found: RecoveredRun, expected: RunEnvelope) -> tuple[str, ...]:
    """Name every fact on which a found run disagrees with the preview's frozen one.

    The authority is the per-field walk over the two serialized envelopes, read
    through the `_ABSENT` sentinel rather than `dict.get`, because `get` answers
    None both for a key that is missing and for a key that holds null — two
    different durable facts, and the contracts keep unknown fields on purpose.
    A field on which the two rows disagree is named, and naming one is what
    refuses the run; there is no separate whole-row equality check, because over
    JSON values it could never disagree with this walk and a check that cannot
    fire is not an authority.

    The fields are not listed here: they are whatever `RunEnvelope` serializes,
    so a field added to the contract is compared without this function learning
    about it. The configuration is compared as well as its digest, because
    "the digest matches" is a statement about sha256 and this is a statement
    about the configuration the service is about to work from. The recorded
    history is compared too: the preview's own is fully predictable, so a run
    holding anything else — a journal line or a `decisions/` receipt this
    preview never minted — is a history it must not append to.

    A warning is a fact of the replay too and is named with them. An incomplete
    journal tail is such a warning -- durable bytes `read` declined to touch and
    left out of what it returned, which is why every fact above can match while
    the run itself is not the one they describe -- and an orphan `decisions/`
    receipt is another, replayed into the records and disagreeing on history as
    well. Every warning counts whatever it says, and every one of them is
    irresolvable where it lies: this module repairs no journal and adopts no
    foreign identity, so no object can be lifted out of such a run to make it the
    preview's own. What `_unowned_entries` adds is the other half -- an object no
    replayed fact can state at all, because `read` never opened it.
    """
    found_row, expected_row = found.envelope.as_dict(), expected.as_dict()
    differences = [
        f"{name}: expected {_field_for_message(expected_row, name)}, "
        f"found {_field_for_message(found_row, name)}"
        for name in sorted(set(expected_row) | set(found_row))
        if expected_row.get(name, _ABSENT) != found_row.get(name, _ABSENT)
    ]
    if found.config != _REPLAYED_FROZEN_CONFIG:
        differences.append("config: the stored configuration is not the frozen one")
    history = _history(found.records)
    if history not in _OWN_HISTORIES:
        differences.append(
            f"history: expected nothing yet or [{_OWN_LINE}], "
            f"found [{', '.join(history)}]")
    differences.extend(f"replay: {warning}" for warning in found.warnings)
    return tuple(differences)


def _run_differences(
        found: RecoveredRun, expected: RunEnvelope, run_path: Path) -> tuple[str, ...]:
    """Name every point on which a found run is not this preview's, and what to do.

    Two kinds, held apart because they cost different things: what the replay
    states, which nothing a human lifts out of the run can settle, and the
    durable objects lying beside it that `read` never opened, which lifting out
    settles entirely. The remedy is chosen from exactly that split, and it is
    appended to every refusal there is -- so the run's full path reaches a reader
    on the road where an object was named and on the road where only the envelope
    disagreed. A dead end nobody is told about is a bug of its own, and until the
    remedy was assembled here only the first road was told about theirs.
    """
    irresolvable = _irresolvable_differences(found, expected)
    unowned = _unowned_files(run_path)
    if not (irresolvable or unowned):
        return ()
    return (
        *irresolvable, *_unowned_entries(unowned),
        _remedy(run_path, unowned, bool(irresolvable)))


def _refusal(differences: tuple[str, ...]) -> str:
    """Say that nothing was proposed, then name each disagreement on its own line.

    The entries are not joined on a separator a found value could contain. One
    side of an entry is a value this preview does not control, rendered with
    `repr`, and `repr` never produces a newline -- so a stored string reading
    `a; mode: expected 1, found 2` is one field's found side and cannot become a
    second entry naming a difference the preview never found. The sentence was
    already truthful to a human, because the value is quoted; this makes it hold
    for a reader that splits the message into entries as well.
    """
    return (
        f"run {_RUN_ID!r} already exists and is not this preview's run, "
        "so nothing was proposed into it:"
        + "".join(f"\n  {entry}" for entry in differences))


def render_dispatch_preview(
        project_root: str, *, instance_id: str = DEFAULT_INSTANCE,
        adapter_id: str | None = None) -> str:
    """Create or open the preview run, propose one dispatch, return its canonical form.

    Args:
        project_root: The directory holding (or to hold) ``conductor/runs``.
        instance_id: The configured instance to propose against.
        adapter_id: An adapter the caller claims drives the instance, cross-checked
            against the frozen config; None trusts the config's binding outright.

    Returns:
        The canonical JSON of the ActionProposal, including its preview_digest.

    Raises:
        PreviewError: The run cannot be created, a run already stands at the
            preview's identity without being the preview's own run, the instance
            is unknown, the claimed adapter mismatches the binding, or the
            capability is not declared by the bound adapter.
    """
    store = RunStore(project_root)
    envelope = RunEnvelope(
        run_id=_RUN_ID, cycle_id="preview-orbit", created_at=_NOW,
        config_digest=snapshot_digest(FROZEN_CONFIG), mode="propose")
    try:
        try:
            store.create_run(envelope, FROZEN_CONFIG)
        except RunExists:
            # A run already at this identity is state the preview FOUND, not state
            # it froze. Replay it read-only and hold its envelope, its frozen config,
            # its recorded history and the replay's own warnings against what this
            # preview would itself have written, BEFORE anything is appended: only
            # the very same preview run may be reopened, and one that is not keeps
            # every durable byte of its directory exactly as it was found.
            differences = _run_differences(
                store.read(_RUN_ID), envelope, store.run_path(_RUN_ID))
            if differences:
                raise PreviewError(_refusal(differences))
        service = CommandService(
            store, AdapterRegistry([_PreviewAdapter()]),
            clock=lambda: _NOW, ids=_preview_id)
        proposal = service.propose(
            run_id=_RUN_ID, instance_id=instance_id, adapter_id=adapter_id,
            attempt_id=_ATTEMPT_ID, capability="dispatch", arguments=_ARGUMENTS,
            scope=_SCOPE, proposed_by=_PROPOSED_BY, rationale=_RATIONALE,
            timeout_seconds=_TIMEOUT_SECONDS)
    except (ServiceError, AdapterContractError, StoreError) as e:
        raise PreviewError(str(e)) from e
    return canonical_json(proposal)
