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
name under the run directory, a symbolic link or a directory junction included,
refuses it too, on the same ground and without a warning to announce it: this
preview did not put that object there and cannot say whether whoever did is
finished with it.

Refusing that found state follows one narrowed contract (owner decision,
2026-08-12), which covers every refusal that declines a run directory this
preview found or failed to read, and every store-level creation failure --
the service's own refusals of an unknown instance or a mismatched adapter
speak in the service's words, upstream of it. Each such refusal exits 1 with
an empty stdout and changes nothing: a found run directory is left byte for
byte and structurally as it was found -- journal, receipts, links and nested
objects included, because every check above works by reading alone -- and a
failed creation leaves the exact preview-run path unchanged. The message
names what was reliably detected, the exact path of the preview's run
directory, and the exact path of every foreign object the ownership walk
itself saw; it states in so many words
that the preview changed nothing in the run directory; and it advises nothing
-- no object is proposed for deletion or moving, and no minimal remediation is
promised, because this module cannot know what a foreign object is to whoever
wrote it. Accuracy over pseudo-actionability. When the store cannot safely
replay what stands at the identity at all -- a StoreError or CorruptRun in
place of a replayed run -- no fact about the directory's objects can be safely
established, so the message enumerates none; it names the run path and states
the limit directly: no safe automatic remediation is defined; preserve the run
directory and investigate it separately.
"""
from __future__ import annotations

import stat
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


#: A junction's reparse tag. The constant lives in `stat` on every platform;
#: the `st_reparse_tag` attribute exists only on Windows, so elsewhere the
#: getattr in `_points_elsewhere` answers 0 and no path ever carries the tag.
_JUNCTION_TAG = getattr(stat, "IO_REPARSE_TAG_MOUNT_POINT", 0xA0000003)


def _points_elsewhere(path: Path) -> bool:
    """A symbolic link or an NTFS junction: a name whose content lies elsewhere.

    `is_symlink` alone is not the test: a junction answers `is_dir()` True and
    -- on the interpreters this project runs -- `is_symlink()` False, so a walk
    keeping only that filter adopts one as a plain directory and recurses
    through it into a tree the run directory does not hold. The reparse tag is
    the junction's own durable mark, read from `lstat` without following
    anything, and it survives the target's disappearance.
    """
    return (path.is_symlink()
            or getattr(path.lstat(), "st_reparse_tag", 0) == _JUNCTION_TAG)


def _unowned_files(run_path: Path) -> tuple[str, ...]:
    """Name every durable object under the run directory the run store does not own.

    A plain directory is not named: it holds no bytes, so an empty one is
    adopted with the run for want of anything to judge, and a file inside one
    is reached by this walk under its own relative name. A symbolic link and a
    junction ARE named, whatever they point at and whether or not the target is
    there, and the walk never steps through one: what lies behind such a name
    lies outside the run, so entering it would judge -- and name -- objects
    this refusal has no standing over. The `decisions/` check is on the parent
    rather than on the path's first part, so a receipt-looking name nested
    deeper than the store ever writes is still named here.
    """
    receipts = run_path / _RECEIPTS_DIR
    unowned: list[str] = []
    stack = [run_path]
    while stack:
        for path in sorted(stack.pop().iterdir()):
            if _points_elsewhere(path):
                unowned.append(path.relative_to(run_path).as_posix())
                continue
            if path.is_dir():
                stack.append(path)
                continue
            name = path.relative_to(run_path).as_posix()
            owned = (
                name in _STORE_OWNED_FILES
                or (path.parent == receipts and path.suffix == _RECEIPT_SUFFIX))
            if not owned:
                unowned.append(name)
    return tuple(sorted(unowned))


def _unowned_entries(run_path: Path, unowned: tuple[str, ...]) -> tuple[str, ...]:
    """Name the durable objects that reach this preview without a warning at all.

    `read` opens four names, so a `.records.jsonl.<rand>.tmp` left by a writer
    that crashed inside its own publish replays as a flawless history with
    nothing whatever to report; only the walk above can see it. Each object is
    named by the exact path it stands at -- the walk reliably established
    exactly that much -- and nothing more is said about it: this preview cannot
    know what the object is to whoever put it there, so it does not advise
    anyone to touch it.
    """
    return tuple(
        f"files: {str(run_path / name)!r} is not an object this run's store writes"
        for name in unowned)


def _contract_facts(run_path: Path) -> tuple[str, str]:
    """The two facts every refusal of a found run carries, whichever road raised it.

    The exact run path, so a reader knows where the refused state stands, and
    the statement that nothing in it was changed -- true on every road, because
    everything a refusal knows was learned by reading alone, and held from the
    outside by a snapshot test that walks bytes, structure and link targets.
    """
    return (
        f"run directory: {str(run_path)!r}",
        "the preview changed nothing in the run directory: every byte, every "
        "entry and every link is exactly as it was found")


#: What a refusal says when the store itself could not safely replay the state:
#: the owner's stated limit, in place of any guess about the directory's objects.
_DIAGNOSTIC_LIMIT = (
    "no safe automatic remediation is defined; preserve the run directory and "
    "investigate it separately")


def _replay_differences(
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
    well. Every warning counts whatever it says: this module repairs no journal
    and adopts no foreign identity. What `_unowned_entries` adds is the other
    half -- an object no replayed fact can state at all, because `read` never
    opened it.
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
    """Name every reliably established point on which a found run is not this preview's.

    Two kinds: the facts the replay states -- envelope fields, the frozen
    configuration, the recorded history, the replay's own warnings -- and the
    durable objects lying beside them that `read` never opened, each named by
    its exact path. Either kind alone refuses the run, and every refusal closes
    on the same two contract facts: the run directory's exact path, and the
    statement that nothing in it was changed. No remedy is appended anywhere,
    because none is promised: this preview cannot know what any of those
    objects is to whoever wrote it, and a guessed instruction would trade
    accuracy for pseudo-actionability.
    """
    replay = _replay_differences(found, expected)
    unowned = _unowned_files(run_path)
    if not (replay or unowned):
        return ()
    return (
        *replay, *_unowned_entries(run_path, unowned), *_contract_facts(run_path))


def _refusal(header: str, entries: tuple[str, ...]) -> str:
    """Open with the header sentence, then name each entry on a line of its own.

    The guarantee here is narrower than entry-forgery being impossible, and it
    holds only for the values and paths the specific calling code actually
    passes through `repr`, which never produces a newline, so a stored string
    reading `a; mode: expected 1, found 2` stays one field's quoted found
    side. Replay warnings are human-readable store prose and are outside this
    guarantee. Unknown envelope field NAMES are
    interpolated into their entry as-is, and a foreign key that itself holds a
    newline therefore lays out across lines the way a further entry would.
    stderr is human-readable diagnostics, not a machine protocol of entries: a
    reader may trust the repr-quoted values, not the line structure around a
    key it does not know.
    """
    return header + "".join(f"\n  {entry}" for entry in entries)


def _unreplayable_refusal(run_path: Path, error: StoreError) -> str:
    """Refuse an identity the store cannot safely replay, naming the stated limit.

    A StoreError or CorruptRun in place of a replayed run means nothing can
    safely establish what any object in the directory is, so no object is
    enumerated and nothing is guessed. What IS reliably established is named:
    the store's own complaint where a directory stands at the path, or -- where
    none does -- the fact that the path is claimed by something the store
    cannot replay. The store's sentence for that second case is `does not
    exist`, the exact opposite of what `create_run` just proved by refusing the
    name, so it is not repeated here.
    """
    if run_path.is_dir():
        detected = f"detected: {str(error)!r}"
    else:
        detected = (
            "detected: the run's path is already claimed, but what stands at it "
            "is not a run directory the store can replay")
    return _refusal(
        f"run {_RUN_ID!r} already exists and cannot be safely replayed, "
        "so nothing was proposed into it:",
        (detected, *_contract_facts(run_path), _DIAGNOSTIC_LIMIT))


def _uncreatable_refusal(run_path: Path, error: Exception) -> str:
    """Refuse when the store cannot create the run at all.

    Reached when `create_run` fails below `RunExists` -- for example something
    other than a directory standing at `conductor/runs`. The call may have
    made parent directories before it failed, so the message does not claim
    the preview created nothing at all; the claim owed and stated is exact and
    narrower: the path the run would occupy, and that nothing in the run
    directory at that path was changed.
    """
    return _refusal(
        f"run {_RUN_ID!r} cannot be created, so nothing was proposed:",
        (f"detected: {str(error)!r}",
         f"run directory: {str(run_path)!r}",
         "the preview changed nothing in the run directory"))


def _check_found_run(store: RunStore, envelope: RunEnvelope) -> None:
    """Adopt the found run only if it is provably this preview's own; else refuse.

    A run already at this identity is state the preview FOUND, not state it
    froze. It is replayed read-only and held -- envelope, frozen config,
    recorded history, replay warnings, and the durable objects beside them --
    against what this preview would itself have written, BEFORE anything is
    appended: only the very same preview run may be reopened, and one that is
    not keeps every durable byte of its directory exactly as it was found. A
    replay the store itself refuses is a refusal too, on the narrower facts
    that are still reliable; caught here, because the module-level catch in
    `render_dispatch_preview` would surface the bare StoreError without the
    run path, without the changed-nothing statement, and -- for a file
    standing at the run's path -- claiming the run does not exist.
    """
    run_path = store.run_path(_RUN_ID)
    try:
        found = store.read(_RUN_ID)
    except StoreError as e:
        raise PreviewError(_unreplayable_refusal(run_path, e)) from e
    differences = _run_differences(found, envelope, run_path)
    if differences:
        raise PreviewError(_refusal(
            f"run {_RUN_ID!r} already exists and is not this preview's run, "
            "so nothing was proposed into it:", differences))


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
            preview's identity without being provably the preview's own run --
            or without being safely replayable at all -- the instance is
            unknown, the claimed adapter mismatches the binding, or the
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
            # Found state, not frozen state: see _check_found_run.
            _check_found_run(store, envelope)
        except (StoreError, OSError) as e:
            # A store-level creation failure -- e.g. a FILE at conductor/runs --
            # is a refusal through the contract diagnostics, not a bare error
            # or a traceback: the message names the exact run path.
            raise PreviewError(_uncreatable_refusal(store.run_path(_RUN_ID), e)) from e
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
