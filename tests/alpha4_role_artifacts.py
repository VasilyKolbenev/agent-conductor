"""Derive the frozen ALPHA-4 role artifacts the Fable UI lane consumes.

Nothing here is hand-written. Every document is produced BY the production
contracts -- the shipped template file, `GraphTemplate`, `RunBinding`,
`materialize` -- so a document that survives this module is one the contracts
accept, and a contract change that would have rejected it reds here rather
than in a browser.

Three documents, because a role-aware Cockpit has three different jobs:

- **the template**, as an editor renders and submits it. Roles and work; no
  provider, no instance, no run.
- **two bindings**, because the whole point of a role is that the same cycle
  runs on more than one deployment. One spreads four roles over two instances;
  the other gives all four to a single instance, which is what a small
  install looks like.
- **the materialized definitions and their digests**, which is what the run
  read will answer with once each binding has been used. Same topology, two
  different records, and the digests prove they are different records.

The digest is computed over each definition, never stored beside it, for the
reason `graph_definition` gives: a written-down digest of oneself can come to
disagree with oneself.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from conductor.command.graph_dalio import is_dalio_template
from conductor.command.graph_template import (
    GraphTemplate,
    RunBinding,
    load_template,
    materialize,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"
ARTIFACTS = ("alpha4_dalio_template", "alpha4_run_bindings",
             "alpha4_materialized_runs")

#: Fixed so the derived documents are reproducible: the same build twice is the
#: same bytes, which is what makes an equality pin meaningful.
CREATED_AT = "2026-08-20T12:00:00Z"
TEMPLATE_NAME = "dalio-v1"

#: One deployment with two instances of two different harnesses, and one with a
#: single instance doing everything. Both are frozen configuration snapshots as
#: a run replays them: the instance is what a plan names, the adapter behind it
#: is the configuration's business and appears in no plan.
SPREAD_CONFIG: dict[str, Any] = {"instances": [
    {"id": "claude-dev", "adapter": "claude-code"},
    {"id": "codex-review", "adapter": "codex"},
]}
SOLO_CONFIG: dict[str, Any] = {"instances": [
    {"id": "solo-node", "adapter": "claude-code"},
]}
_SPREAD = {"role-thinker": "codex-review", "role-diagnostician": "codex-review",
           "role-designer": "codex-review", "role-implementer": "claude-dev"}


def _binding_rows(template: GraphTemplate) -> tuple[dict[str, Any], ...]:
    solo = {role: "solo-node" for role in template.roles}
    return (
        {"name": "two-instances", "config": SPREAD_CONFIG,
         "graph_id": "graph-dalio-spread", "run_id": "run-spread",
         "binding": RunBinding(assignments=_SPREAD)},
        {"name": "one-instance", "config": SOLO_CONFIG,
         "graph_id": "graph-dalio-solo", "run_id": "run-solo",
         "binding": RunBinding(assignments=solo)},
    )


def derive_all() -> dict[str, Any]:
    """Build every artifact through the production contracts, in one pass."""
    template = load_template(TEMPLATE_NAME)
    rows = _binding_rows(template)
    runs = []
    for row in rows:
        definition = materialize(
            template, row["binding"], row["config"],
            graph_id=row["graph_id"], run_id=row["run_id"],
            created_at=CREATED_AT)
        assert is_dalio_template(definition), row["name"]
        runs.append({
            "name": row["name"],
            "assignments": dict(sorted(row["binding"].assignments.items())),
            "instances": list(row["binding"].instances),
            "definition": definition.as_dict(),
            "definition_digest": definition.digest(),
        })
    digests = {run["definition_digest"] for run in runs}
    assert len(digests) == len(runs), "two bindings produced one record"
    return {
        "alpha4_dalio_template": {
            "template": template.as_dict(),
            "roles": list(template.roles),
        },
        "alpha4_run_bindings": {
            "bindings": [
                {"name": row["name"], "config": row["config"],
                 "binding": row["binding"].as_dict()} for row in rows],
        },
        "alpha4_materialized_runs": {"runs": runs},
    }


def load(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def write_all() -> None:
    for name, document in derive_all().items():
        (FIXTURES / f"{name}.json").write_text(
            json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8", newline="\n")


if __name__ == "__main__":                 # pragma: no cover -- derivation entry
    write_all()
