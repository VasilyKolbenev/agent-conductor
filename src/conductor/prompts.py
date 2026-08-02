"""Prompt vending — deterministic instruction text for agents, no LLM involved.

Two pure string builders: `bootstrap_prompt` tells an agent how to create
`conductor/map.toml`; `role_prompt` tells a role-holding agent how to keep
its lane file and which findings still owe it a verdict. The map example is
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


# PROTOCOL.md §2. Public: `conduct init` writes this text as the map.toml stub —
# ONE sync point for the spec's map example.
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

[[cycle.roles]]
id = "reviewer"
harness = "codex"
reviews = ["implementer"]

[cycle]
phases = ["plan", "implement", "review", "human-gate"]

[[invariants]]
id = "main-untouched"
text = "main branch is never committed to directly"'''

# The fill-in author for prompts vended without --author. Doubles as the lane
# filename stem in the prose, so both stay in sync.
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
  with kind "ok" and the closed id in its ref.
- Run `conduct validate` before finishing a work session.'''

_VOCABULARIES = '''Closed vocabularies:
- verdicts.*.disposition: confirmed | refuted | partial
- map_status values: pass | fail | blocked | running | idle
- waits_on_human.kind: decision | action | review
- blocks entries and event ref values hold finding ids or map node ids'''


def bootstrap_prompt() -> str:
    """Return the fixed instruction block for bootstrapping `conductor/map.toml`.

    Returns:
        A deterministic English prompt: read the project docs, write the map
        (full commented example embedded), obey the validation rules, then
        run `conduct validate`.
    """
    return (
        "You are bootstrapping Conduct for this project.\n"
        "\n"
        "1. Read the project's roadmap, plan, and architecture documents.\n"
        "2. Produce `conductor/map.toml`: the project map — nodes plus an optional\n"
        "   review cycle. A fully commented example:\n"
        "\n"
        "```toml\n"
        f"{MAP_EXAMPLE}\n"
        "```\n"
        "\n"
        "Validation rules your map must satisfy:\n"
        "- schema_version == 1\n"
        "- node ids are unique\n"
        "- depends_on and reviews reference existing ids\n"
        "- at least one node\n"
        "Everything else is optional — a map with only nodes is valid.\n"
        "\n"
        "3. Run `conduct validate` to check the map before you finish.\n"
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


def role_prompt(state: dict, role_id: str, author: str | None = None) -> str:
    """Render the state-aware working prompt for one cycle role.

    Args:
        state: A `state.json` dict as produced by `merge.merge()`.
        role_id: The cycle role the prompt is vended for.
        author: The agent's lane author id (`conductor/lanes/<author>.json`);
            None renders an author-agnostic prompt with fill-in placeholders.

    Returns:
        A deterministic English prompt: mission line, lane-file contract with
        a copy-safe strict-JSON starter (role and author pre-filled), the
        lifecycle rules, closed vocabularies, the current map node ids, and —
        last — the enriched findings still awaiting this role's verdict.

    Raises:
        UnknownRole: If `role_id` names no `state["cycle"]["roles"]` entry.
    """
    role = next((r for r in state["cycle"]["roles"] if r["id"] == role_id), None)
    if role is None:
        known = ", ".join(r["id"] for r in state["cycle"]["roles"]) or "none declared"
        raise UnknownRole(
            f"role {role_id!r} is not declared in cycle.roles (known roles: {known})")
    reviews = role.get("reviews", [])
    reviewed = ", ".join(reviews) if reviews else "no other roles"
    node_ids = ", ".join(n["id"] for n in state["map"]["nodes"]) or "(none)"
    stem = author if author is not None else _AUTHOR_PLACEHOLDER
    return (
        f'You hold the "{role_id}" role in this project\'s Conduct cycle; '
        f"you review findings from: {reviewed}.\n"
        "\n"
        f"Your lane file is conductor/lanes/{stem}.json; its \"author\" field\n"
        "must equal the filename stem. Start from this template (STRICT JSON —\n"
        "no comments, copy it verbatim):\n"
        "\n"
        "```json\n"
        f"{_starter_template(role_id, author)}\n"
        "```\n"
        "\n"
        f'Replace the "updated" value ({_UPDATED_PLACEHOLDER}) with the\n'
        "current UTC ISO-8601 time on every write. map_status keys must be ids\n"
        "from the current map, listed below — never invent node ids.\n"
        "\n"
        f"{_LIFECYCLE}\n"
        "\n"
        f"{_VOCABULARIES}\n"
        "\n"
        f"Current map node ids: {node_ids}\n"
        "\n"
        "The following findings are awaiting your verdict:\n"
        f"{_pending_block(state, role_id)}\n"
    )
