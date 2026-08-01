"""Prompt vending — deterministic instruction text for agents, no LLM involved.

Two pure string builders: `bootstrap_prompt` tells an agent how to create
`conductor/map.toml`; `role_prompt` tells a role-holding agent how to keep
its lane file and which finding ids still owe it a verdict. The templates
are verbatim spec excerpts (PROTOCOL.md §2 and §3).
"""
from __future__ import annotations

from conductor import merge


class UnknownRole(Exception):
    """Raised when `role_prompt` is asked for a role id the cycle does not declare."""


_MAP_EXAMPLE = '''schema_version = 1
project = "voice-app"

[[nodes]]
id = "backend"          # unique, referenced by lanes
label = "backend build"
kind = "artifact"       # free-form: artifact | gate | component | doc | …
row = 0                 # optional; layout falls back to topological layering
depends_on = ["models"]

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

# PROTOCOL.md §3, with the "role" value swapped for a fill-in marker.
_LANE_TEMPLATE = '''{
  "schema_version": 1,
  "author": "claude",            // must equal the filename stem
  "role": "__ROLE__",            // a cycle.roles id, or absent for observers
  "updated": "2026-07-29T21:20:00+03:00",
  "staleness_after_minutes": 360,   // optional; default 360
  "now": { "task": "fixing gate D", "since": "2026-07-29T20:00:00+03:00",
           "phase": "implement" },   // optional; must be a cycle.phases value
  "map_status": { "backend": "pass", "smoke": "fail" },
  "findings": [
    {
      "id": "D-2",               // globally unique across lanes
      "title": "STT model missing from the bundle",
      "severity": "blocker",     // blocker | major | minor | note
      "claim": "defect",         // the author's own assessment (free-form label)
      "detail": "…",
      "evidence": "path/to/log or a reproduced command",
      "refs": ["smoke"]          // map node ids this finding touches
    }
  ],
  "verdicts": {
    "D-1": { "disposition": "confirmed", "note": "reproduced at …" }
  },
  "waits_on_human": [
    { "id": "w-whisper", "kind": "decision",
      "title": "Bundle the STT model (+461 MB) or download on first run?",
      "why": "Determines what D-2's fix looks like.", "blocks": ["D-2"] }
  ],
  "invariants": [ { "id": "main-untouched", "ok": true } ]
}'''

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
        f"{_MAP_EXAMPLE}\n"
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


def role_prompt(state: dict, role_id: str) -> str:
    """Render the state-aware working prompt for one cycle role.

    Args:
        state: A `state.json` dict as produced by `merge.merge()`.
        role_id: The cycle role the prompt is vended for.

    Returns:
        A deterministic English prompt: mission line, lane-file contract with
        the spec's lane template (role pre-filled), closed vocabularies, the
        current map node ids, and — last — the finding ids still awaiting
        this role's verdict.

    Raises:
        UnknownRole: If `role_id` names no `state["cycle"]["roles"]` entry.
    """
    role = next((r for r in state["cycle"]["roles"] if r["id"] == role_id), None)
    if role is None:
        raise UnknownRole(f"role {role_id!r} is not declared in cycle.roles")
    reviews = role.get("reviews", [])
    reviewed = ", ".join(reviews) if reviews else "no other roles"
    node_ids = ", ".join(n["id"] for n in state["map"]["nodes"]) or "(none)"
    pending = merge.pending_verdicts(state).get(role_id, [])
    pending_lines = "\n".join(f"- {fid}" for fid in pending) or "(none)"
    return (
        f'You hold the "{role_id}" role in this project\'s Conduct cycle; '
        f"you review findings from: {reviewed}.\n"
        "\n"
        "Maintain your lane file at conductor/lanes/<author>.json, where <author>\n"
        'is your agent name and must equal the file\'s "author" field. Rewrite the\n'
        "whole file on every update (write a temp file, then rename). Template\n"
        "(your role is pre-filled):\n"
        "\n"
        "```jsonc\n"
        f'{_LANE_TEMPLATE.replace("__ROLE__", role_id)}\n'
        "```\n"
        "\n"
        f"{_VOCABULARIES}\n"
        "\n"
        f"Current map node ids: {node_ids}\n"
        "\n"
        "The following finding ids are awaiting your verdict:\n"
        f"{pending_lines}\n"
    )
