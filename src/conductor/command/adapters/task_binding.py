"""What the child is asked to do, and the proof it is what a person previewed.

Split out of ``headless_cli`` when that module stood at 796 of 800 lines with
this seam owed. The seam is a subject: ``headless_routing`` holds how a routed
model becomes tokens, ``headless_receipts`` how an observation becomes durable
words, ``headless_values`` the values a spawn is described with -- and this
holds the TASK's own bytes: how they are composed, and whether they are the
bytes the proposal was previewed with.

The second half is the new one. A dispatch resolves its instruction from the
run's journal when a document was published under the step's reference before
the proposal, and otherwise from a FILE under the workspace's instruction
directory. The journal road is immutable by construction: a record is appended
once and the resolution is cut at the proposal. The FILE road is not. A person
reads a preview, the file changes, and the child is handed different words under
an approval given for the old ones -- a matching reference is not matching
content, and only the bytes can say so.

So a proposal may CARRY the digest of the instruction it previewed, and this
refuses the dispatch when the bytes no longer match. It is carried, not
inferred: a build that computed the expected digest itself would be checking its
own reading against itself, which is no check at all.

The field is OPTIONAL and its absence is the old road exactly. Every proposal
written before it exists, and every historical Confirm run replayed from the
journal, carries nothing here and runs as it always did. That is deliberate:
this slice adds a door, and adding a door may not re-judge what walked through
the doorway before it existed.
"""
from __future__ import annotations

import hashlib

from .deep_commands import DeepDispatchArgs
from .deep_contracts import OMITTED
from .headless_values import flagless, purpose_clause


class InstructionChanged(Exception):
    """The previewed instruction is not the instruction standing now."""


#: What a receipt says when the bytes moved. It names neither the path nor one
#: character of either text: the path is operator state and the text is the
#: operator's own words, and a receipt reaches the journal and the API.
CHANGED_DETAIL = (
    "the instruction this action was previewed with is not the instruction "
    "standing now, so no task was spawned; propose the step again")


def promised_bytes(args: DeepDispatchArgs) -> bool:
    """Whether this dispatch promised the bytes of its instruction.

    One question, asked in two places for one reason: the door that READS the
    instruction has to know whether to read it exactly, and the door that JUDGES
    it has to know whether to judge at all. Two spellings of the same test is
    how one of them comes to answer differently from the other.
    """
    return getattr(args, "instruction_digest", OMITTED) is not OMITTED


def content_digest(text: str) -> str:
    """SHA-256 of the EXACT UTF-8 bytes of this text.

    No strip, no newline normalization, no re-encoding through a friendlier
    form: a trailing space is a different instruction to a model, so it is a
    different digest here. Whitespace is the cheapest place for a changed
    instruction to hide, and it is the first place a normalizing digest would
    stop looking.

    This is deliberately NOT ``ArtifactDocument.digest()``, which hashes the
    whole canonical document -- identifiers, refs, media type and provenance
    beside the content. Two documents carrying identical words differ there and
    agree here, and the question this answers is only ever about the words.

    Spelled in the grammar every other digest in this build is spelled in, so
    the same validator judges it and a reader never has to ask which of two
    shapes a digest field holds.
    """
    return f"sha256:{hashlib.sha256(text.encode('utf-8')).hexdigest()}"


def composed_task_text(args: DeepDispatchArgs, instruction: str,
                       tool_noun: str, error) -> str:
    """A code-owned frame, then the MATERIALIZED instruction the user asked for.

    The frame is written here from identifiers the request validated, and it
    stands FIRST so that no byte of the instruction can occupy a launcher's flag
    position; ``flagless`` proves that at the argv boundary anyway. The
    instruction itself is the task, read by the workspace door from one
    contained file -- a dispatch that could not read it never reaches this
    function, because a sentence built from the reference alone is not the
    user's task and dispatching it would be a lie about what the child was
    asked to do.
    """
    refs = " ".join(args.artifact_refs) or "none"
    return flagless(
        f"conduct work item {args.work_item_id} under the {args.profile} "
        f"profile over artifacts {refs}.{purpose_clause(args)} instruction "
        f"{args.instruction_ref} reads:\n{instruction}",
        "task text", f"{tool_noun} launcher", error)


class InstructionBinding:
    """Judge the resolved instruction against the digest its proposal carried.

    Mixed into the transport rather than written inside it, for the reason the
    other mixins here exist: the class that dispatches is at its line cap, and a
    rule with its own subject reads better beside its own docstring than as
    three lines in the middle of a spawn road.

    What this needs from the class it is mixed into is stated rather than
    assumed: ``_instruction_text``, which every transport already has and which
    the durable road overrides.
    """

    def _bound_instruction(self, request, args: DeepDispatchArgs) -> str:
        """The instruction to run, or a refusal if it is not the previewed one.

        Called where the dispatch already resolved its instruction, which is
        BEFORE the sweep, the version preflight and the spawn -- so a changed
        instruction costs no child, no home and no vendor call. The refusal
        travels as an exception because the road it interrupts returns a receipt
        from one funnel and a second return path there would be a second answer
        to the same question.

        An absent digest is not a failure to check: it is a proposal that never
        promised these bytes, and it runs exactly as it did before this door.
        """
        instruction = self._instruction_text(request, args)
        if not promised_bytes(args):
            return instruction
        if content_digest(instruction) != args.instruction_digest:
            raise InstructionChanged(CHANGED_DETAIL)
        return instruction
