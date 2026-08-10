"""Prompt vending — deterministic instruction text for agents, no LLM involved.

Two pure string builders: `bootstrap_prompt` tells an agent how to fill in the
`conductor/map.toml` that `conduct init` has already written; `role_prompt`
tells a role-holding agent how to keep its lane file and which findings still
owe it a verdict. The map example is
taken from the spec (PROTOCOL.md §2); the lane starter vended by
`role_prompt` is deliberately NOT the commented §3 excerpt — that one stays
in PROTOCOL.md as an illustration, while the vended template is a separate,
copy-safe strict-JSON artifact an agent can write verbatim.
"""
from __future__ import annotations

import json

from conductor import merge


class UnknownRole(Exception):
    """Raised when `role_prompt` is asked for a role id the cycle does not declare."""


# PROTOCOL.md §2 — ONE sync point for the spec's map example. Public, with a
# single reader: `templates` vends it verbatim as the `minimal` template. It is
# neither what `conduct init` writes by default (that is
# `templates.get(templates.DEFAULT)`) nor part of `bootstrap_prompt` any more —
# a prompt that embeds a whole map invites an agent to replace the one already
# on disk. Note it ends without a trailing newline; `templates` adds the one a
# file needs.
#
# It is a COPY of the spec's fenced block, not an import of it, so the copy is
# what has to be held: tests/test_templates.py::
# test_the_minimal_template_is_the_protocol_spec_section_2_block_byte_for_byte
# reads that block out of spec/PROTOCOL.md and requires this text back. Edit
# one of the two and that guard names the other.
MAP_EXAMPLE = '''schema_version = 1
project = "web-app"

[[nodes]]
id = "schemas"
label = "shared contracts"
kind = "artifact"

[[nodes]]
id = "api"              # unique, referenced by lanes
label = "api build"
kind = "artifact"       # free-form: artifact | gate | component | doc | …
depends_on = ["schemas"]

[[cycle.roles]]
id = "implementer"
harness = "claude-code"  # informational
reviews = []             # role ids whose findings this role must verdict
stage = "implement"      # optional; one cycle.phases value

[[cycle.roles]]
id = "reviewer"
harness = "codex"
reviews = ["implementer"]
stage = "review"

[cycle]
phases = ["plan", "implement", "review", "human-gate"]
# Phases are labels; a "human gate" is simply a phase name. Dedicated
# human-gate objects were considered and cut (YAGNI): the human queue is
# built from lanes' waits_on_human, not from the map.
# `stage` says which phase a role works in, so a consumer can draw the cycle
# from the map alone, before any lane reports. It is presentation and handoff
# metadata: no §6 merge rule reads it, and it changes no computed value.

[[invariants]]
id = "main-untouched"
text = "main branch is never committed to directly"'''

# The fill-in author for prompts vended without --author. Doubles as the lane
# filename stem in the prose, so both stay in sync. The angle brackets are
# load-bearing: they can never match store.AUTHOR_RE, so a verbatim copy that
# keeps the placeholder is rejected instead of silently becoming a real lane.
_AUTHOR_PLACEHOLDER = "<your-author-id>"

# The literal `updated` value in the starter template; the agent must swap it
# for the current UTC ISO-8601 time on every write.
_UPDATED_PLACEHOLDER = "REPLACE-WITH-CURRENT-UTC-ISO8601"

_LIFECYCLE = '''Lifecycle:
- Read the map and the other agents' lanes before acting.
- NEVER edit another agent's lane file.
- Update your own lane after each significant step.
- Rewrite the whole file on every update: write a temp file, then rename it
  over the lane path.
- Remove a finding only after its fix is confirmed.
- Remove a wait only after the human's answer is received.
- When you close a finding or a wait, append a line to conductor/events.jsonl
  with kind "ok" and the closed id in its ref — required shape (readers skip
  malformed event lines silently):
  {"ts": "<UTC ISO-8601>", "author": "<you>", "kind": "ok", "text": "closed D-2", "ref": "D-2"}
- Run `conduct validate` before finishing a work session.'''

# Who the stage hands off to. `deliver` ends the Run, so its recipient is the
# human accepting it, not another stage — a shared header would be false there.
_HANDOFF = "What the next stage is entitled to receive from you:"
_HANDOFF_HUMAN = "What the human accepting this Run is entitled to receive from you:"

# The Default Orbit's five stages: guiding question, handoff header, and the
# contract owed (docs/specs/2026-08-03-product-direction.md §3). Keyed by stage
# name; a role staged onto a project's own phase name simply misses this table
# and gets no block — never a guessed one.
#
# Every line must be performable by the role that receives it: an imperative
# only another role can carry out is worse than no imperative, because the
# prompt already forbids editing another agent's lane.
#
# `goal` is unreachable from all three vended templates, which leave that stage
# human-owned on purpose. It is kept for projects that do staff it — the
# register is a human's, not an agent's, and that is not a defect to fix by
# staffing goal in the default.
_STAGE_CONTRACTS: dict[str, tuple[str, str, tuple[str, ...]]] = {
    "goal": (
        "What are we trying to achieve, and who owns the decision?",
        _HANDOFF,
        ("State the intended outcome and the scope of this pass.",
         "State what is explicitly out of scope.",
         "List the constraints and the acceptance criteria.",
         "List the risks you already know about.",
         "Name the map nodes the work touches.",
         "Name who owns the decision: a goal nobody owns is not a goal."),
    ),
    "detect": (
        "What is actually true right now?",
        _HANDOFF,
        ("Report what you observe as findings, each with a severity.",
         "Attach evidence to every one: a path, a log, or a reproduced command.",
         "Name the affected components in refs, using map node ids only.",
         "Say whether the finding reproduces, and how.",
         "List your unknowns honestly, rather than rounding them off.",
         "Call a finding you cannot evidence unverified, and leave it there: never "
         "raise your confidence in place of the evidence."),
    ),
    "diagnose": (
        "Why is it happening?",
        _HANDOFF,
        ("Record a verdict on every finding you owe one: confirmed, refuted or partial.",
         "Separate the root cause from the symptoms it produces.",
         "Give the evidence and the reproduction behind each verdict.",
         "Say which hypotheses you ruled out, not only the surviving one.",
         "List the questions still open."),
    ),
    "design": (
        "What do we intend to change, and how will we know it worked?",
        _HANDOFF,
        ("Write the implementation plan and its architectural impact.",
         "Name the affected components and files.",
         "State the test strategy, the migration path and the rollback path.",
         "State the risks, with the alternatives you considered and rejected.",
         "State the evidence the delivery is expected to produce."),
    ),
    "deliver": (
        "What changed, what was checked, and is it safe to accept?",
        _HANDOFF_HUMAN,
        ("Describe what changed.",
         "List the checks you ran and attach their evidence.",
         "Name the role that owes your findings a verdict — it is named above. If no "
         "role does, ask for a human review with a waits_on_human entry of kind "
         "review; your own verdict on your own finding is excluded from every "
         "computation, so it can never stand in for one.",
         "Leave findings that are still open in your lane: never close them silently.",
         "Say why the result is ready.",
         "Raise, as a waits_on_human entry, the decision that accepts it."),
    ),
}

_VOCABULARIES = '''Closed vocabularies:
- verdicts.*.disposition: confirmed | refuted | partial
- map_status values: pass | fail | blocked | running | idle
- waits_on_human.kind: decision | action | review
- blocks entries and event ref values hold finding ids or map node ids'''


#: Where the map lives, relative to the project root, when no caller says
#: otherwise. `conduct init` passes the path it actually wrote.
DEFAULT_MAP_PATH = "conductor/map.toml"

#: Every line of prose a person reads in a terminal folds to this — the prompts
#: below, hand-wrapped, and `conduct init`'s dialogue, folded at render time.
#: Narrow enough to survive a split terminal, and the width the pins enforce:
#: the sentences that matter most are the longest, which is exactly why
#: hand-wrapping them regressed.
WIDTH = 72

# The one table the bootstrapping agent edits. A field reference, deliberately
# NOT a document to reproduce: `conduct init` has already written a valid map,
# so an example map here would invite the agent to replace it — and with it
# every answer the person gave during setup.
_NODE_FIELDS = '''  id          unique, and the only name a lane may use: a lane may
              report a status only for ids declared here, and
              anything else is warned about and ignored
  label       the human name the panel shows
  kind        free-form (artifact | check | component | doc | …);
              the panel prints it, no rule computes on it
  depends_on  ids declared in this same file. The panel draws the
              graph from them; status does NOT propagate along
              them, so a failing dependency never marks its
              dependents failing by itself.'''


def bootstrap_prompt(map_path: str = DEFAULT_MAP_PATH) -> str:
    """Return the instruction block for filling in an already-written map.

    Args:
        map_path: The map the agent must edit, named the way the person
            handing this over sees it.

    Returns:
        A deterministic English prompt, self-contained enough to be redirected
        to a file and handed over on its own: what the map already decides,
        what the agent must replace, the field reference for the one table it
        edits, what must still hold afterwards, and the command that checks it.
    """
    return (
        "You are setting up Conduct for this project. The map you must fill\n"
        "in is:\n"
        "\n"
        # On its own line, and never interpolated into a sentence: an absolute
        # path under `--dir` is long and unwrappable, and folding prose around
        # it pushed these lines past 130 columns.
        f"    {map_path}\n"
        "\n"
        "It already exists and it already validates. Your job is to make it\n"
        "describe THIS project — not to write a new one. The cycle, its\n"
        "phases, and every [[cycle.roles]] block's id, harness, stage and\n"
        "reviews value were chosen when the project was set up. They are\n"
        "answers, not suggestions.\n"
        "\n"
        "1. Read the project's roadmap, plan, and architecture documents.\n"
        "\n"
        "2. Open that file. Every [[nodes]] block in it is a placeholder.\n"
        "   Replace them with the real components of this project, and add\n"
        "   one [[nodes]] block per further component you want reported on:\n"
        "\n"
        f"{_NODE_FIELDS}\n"
        "\n"
        "3. Change nothing else. If the cycle is genuinely wrong for this\n"
        "   project, say so and stop — do not restructure it on your own\n"
        "   initiative.\n"
        "\n"
        "What must still be true when you are done:\n"
        "- schema_version == 1\n"
        "- node ids are unique, and there is at least one node\n"
        "- every depends_on entry names a node declared in this file\n"
        "- every reviews entry names a role declared in this file\n"
        "- every role's stage, where it has one, names one of cycle.phases\n"
        "\n"
        "4. Run `conduct validate` and fix anything it reports before you finish.\n"
    )


def _starter_template(role_id: str, author: str | None) -> str:
    """Serialize the copy-safe strict-JSON lane starter for one role.

    Args:
        role_id: The cycle role pre-filled into the template.
        author: The lane author, or None to emit the fill-in placeholder.

    Returns:
        A `json.dumps(..., indent=2)` lane skeleton that passes
        `schema.validate_lane` once `updated` is swapped for a real time.
    """
    return json.dumps({
        "schema_version": 1,
        "author": author if author is not None else _AUTHOR_PLACEHOLDER,
        "role": role_id,
        "updated": _UPDATED_PLACEHOLDER,
        "map_status": {},
        "findings": [],
        "verdicts": {},
        "waits_on_human": [],
    }, indent=2)


def _stage_block(stage: str | None) -> str:
    """Render the Default Orbit contract for one stage, or nothing.

    Args:
        stage: The role's `stage` value from the map, or None when it has none.

    Returns:
        The stage's guiding question and the contract it owes, or `""` for an
        absent stage and for any name outside the Orbit's five — a project may
        declare its own phases, and a wrong contract is worse than none.
    """
    contract = _STAGE_CONTRACTS.get(stage) if isinstance(stage, str) else None
    if contract is None:
        return ""
    question, handoff, owed = contract
    lines = [f"Stage: {stage} - {question}", handoff]
    lines.extend(f"- {line}" for line in owed)
    return "\n".join(lines)


def _pending_block(state: dict, role_id: str) -> str:
    """Render the enriched awaiting-verdict entries for one role.

    Args:
        state: A `state.json` dict as produced by `merge.merge()`.
        role_id: The reviewing role whose owed findings are rendered.

    Returns:
        One block per pending finding — id, title, severity, author, refs,
        evidence — or `(none)` when the role owes nothing.
    """
    pending = merge.pending_verdicts(state).get(role_id, [])
    if not pending:
        return "(none)"
    by_id = {f["id"]: f for f in state["findings"]}
    lines: list[str] = []
    for fid in pending:
        f = by_id[fid]
        refs = ", ".join(f["refs"]) or "(none)"
        lines.append(f"- {fid}: {f['title']}")
        lines.append(f"  severity: {f['severity']} | author: {f['author']} | refs: {refs}")
        lines.append(f"  evidence: {f['evidence'] or '(none)'}")
    return "\n".join(lines)


def _review_directions(state: dict, role: dict) -> tuple[str, str]:
    """Render both review edges of one role for the prompt's mission lines.

    Args:
        state: A `state.json` dict as produced by `merge.merge()`.
        role: The `state["cycle"]["roles"]` entry the prompt is vended for.

    Returns:
        `(reviewed, reviewed_by)` — whose findings this role owes verdicts on,
        and which roles owe verdicts on this role's findings. The reverse edge
        is what makes the `deliver` contract's "name the role that owes your
        findings a verdict" answerable from the prompt rather than guessed.
    """
    reviews = role.get("reviews", [])
    reviewers = [r["id"] for r in state["cycle"]["roles"]
                 if role["id"] in r.get("reviews", [])]
    return (", ".join(reviews) if reviews else "no other roles",
            ", ".join(reviewers) if reviewers
            else "no role — nobody owes your findings a verdict")


def role_prompt(state: dict, role_id: str, author: str | None = None) -> str:
    """Render the state-aware working prompt for one cycle role.

    Args:
        state: A `state.json` dict as produced by `merge.merge()`.
        role_id: The cycle role the prompt is vended for.
        author: The agent's lane author id (`conductor/lanes/<author>.json`);
            None renders an author-agnostic prompt with fill-in placeholders.

    Returns:
        A deterministic English prompt: mission lines naming both review
        directions, the lane-file contract with a copy-safe strict-JSON
        starter (role and author pre-filled), the lifecycle rules, the
        contract of the role's Orbit stage when it has one, closed
        vocabularies, the current map node ids, and — last — the enriched
        findings still awaiting this role's verdict.

    Raises:
        UnknownRole: If `role_id` names no `state["cycle"]["roles"]` entry.
    """
    role = next((r for r in state["cycle"]["roles"] if r["id"] == role_id), None)
    if role is None:
        known = ", ".join(r["id"] for r in state["cycle"]["roles"]) or "none declared"
        raise UnknownRole(
            f"role {role_id!r} is not declared in cycle.roles (known roles: {known})")
    reviewed, reviewed_by = _review_directions(state, role)
    node_ids = ", ".join(n["id"] for n in state["map"]["nodes"]) or "(none)"
    stem = author if author is not None else _AUTHOR_PLACEHOLDER
    stage_block = _stage_block(role.get("stage"))
    lifecycle = f"{_LIFECYCLE}\n\n{stage_block}" if stage_block else _LIFECYCLE
    swap = (f'Replace the "updated" value ({_UPDATED_PLACEHOLDER}) with the\n'
            "current UTC ISO-8601 time on every write.")
    if author is None:
        swap += (f"\nReplace {_AUTHOR_PLACEHOLDER} with your author id — in the\n"
                 "lane file name too, not just the JSON.")
    return (
        f'You hold the "{role_id}" role in this project\'s Conduct cycle; '
        f"you review findings from: {reviewed}.\n"
        f"Your own findings are reviewed by: {reviewed_by}.\n"
        "\n"
        f"Your lane file is conductor/lanes/{stem}.json; its \"author\" field\n"
        "must equal the filename stem. Start from this template (STRICT JSON —\n"
        "no comments, copy it verbatim):\n"
        "\n"
        "```json\n"
        f"{_starter_template(role_id, author)}\n"
        "```\n"
        "\n"
        f"{swap}\n"
        "map_status keys must be ids from the current map, listed below —\n"
        "never invent node ids.\n"
        "\n"
        f"{lifecycle}\n"
        "\n"
        f"{_VOCABULARIES}\n"
        "\n"
        f"Current map node ids: {node_ids}\n"
        "\n"
        "The following findings are awaiting your verdict:\n"
        f"{_pending_block(state, role_id)}\n"
    )
