"""The wizard's provider rows are the server's rows, plus only the two facts still owed to it.

`GET /command/workflows` answers with `provider_projection`: provider id, display name,
availability, implementation, the pinned login, the proven `controls` and the vendor's sandbox.
The wizard needs two more facts of each harness (`offered`: whether this version offers it, and
`task_channel`: how it is fed), which the server does not carry yet. A stand-in row that grew
keys the server never emits let the model read a shape that does not exist, so these guards hold
the fixtures to the real projection: keys, and the roads of every harness this build has.
"""
from __future__ import annotations

from pathlib import Path

from conductor.command.adapters.claude_code import (
    CLAUDE_CAPABILITIES, CLAUDE_DISPLAY_NAME, CLAUDE_LIFECYCLE, CLAUDE_PROVIDER_ID,
    CLAUDE_SCHEMA_PAIRS)
from conductor.command.adapters.codex_cli import (
    CODEX_CAPABILITIES, CODEX_DISPLAY_NAME, CODEX_LIFECYCLE, CODEX_PROVIDER_ID,
    CODEX_SCHEMA_PAIRS)
from conductor.command.adapters.grok_build import (
    GROK_CAPABILITIES, GROK_DISPLAY_NAME, GROK_LIFECYCLE, GROK_PROVIDER_ID, GROK_SCHEMA_PAIRS)
from conductor.command.adapters.kimi_code import (
    KIMI_CAPABILITIES, KIMI_DISPLAY_NAME, KIMI_LIFECYCLE, KIMI_PROVIDER_ID, KIMI_SCHEMA_PAIRS)
from conductor.command.adapters.provider import ProviderContract, provider_projection
from tests.desk_wizard_node import FIXTURES, fixture

#: The facts of a provider row the server does not serve yet. The one place they are named:
#: a fixture row may carry these beyond the projection, and nothing else.
OWED = {"offered", "task_channel"}
ADAPTERS = (
    (CLAUDE_PROVIDER_ID, CLAUDE_DISPLAY_NAME, CLAUDE_CAPABILITIES, CLAUDE_SCHEMA_PAIRS,
     CLAUDE_LIFECYCLE),
    (CODEX_PROVIDER_ID, CODEX_DISPLAY_NAME, CODEX_CAPABILITIES, CODEX_SCHEMA_PAIRS,
     CODEX_LIFECYCLE),
    (GROK_PROVIDER_ID, GROK_DISPLAY_NAME, GROK_CAPABILITIES, GROK_SCHEMA_PAIRS, GROK_LIFECYCLE),
    (KIMI_PROVIDER_ID, KIMI_DISPLAY_NAME, KIMI_CAPABILITIES, KIMI_SCHEMA_PAIRS, KIMI_LIFECYCLE),
)


def _served(provider_id, display_name, capabilities, schema_pairs, lifecycle) -> dict:
    """The row the server projects for one adapter, from the adapter's own declarations."""
    contract = ProviderContract(
        provider_id=provider_id, display_name=display_name, vendor="a vendor", version="1",
        capabilities=capabilities, schema_pairs=list(schema_pairs), lifecycle=lifecycle,
        availability="available", available=True)
    return provider_projection([contract])[0]


def _rows(name: str) -> list[dict]:
    return fixture("wizard", name)["providers"]


def test_a_fixture_provider_row_has_the_servers_keys_and_only_the_owed_facts_beyond_them():
    real = set(_served(*ADAPTERS[0]))
    assert real == {"provider_id", "display_name", "availability", "implementation", "auth",
                    "controls", "vendor_sandbox"}, "the projection itself changed: re-read it"
    for row in _rows("workflows.json"):
        assert set(row) - OWED == real, row["provider_id"]
        assert set(row) & OWED == OWED, "both owed facts or none: " + row["provider_id"]


def test_the_served_fixture_carries_exactly_the_servers_keys_and_nothing_owed():
    full = fixture("wizard", "workflows.json")
    served = fixture("wizard", "workflows_served.json")
    real = set(_served(*ADAPTERS[0]))
    for row in served["providers"]:
        assert set(row) == real, row["provider_id"]
    stripped = {**full, "providers": [{key: value for key, value in row.items()
                                       if key not in OWED} for row in full["providers"]]}
    assert stripped == served, "the two files describe the same roster"


def test_the_roads_of_every_harness_this_build_has_are_the_ones_the_fixture_says():
    rows = {row["provider_id"]: row for row in _rows("workflows.json")}
    for adapter in ADAPTERS:
        served = _served(*adapter)
        assert rows[served["provider_id"]]["controls"] == served["controls"], adapter[0]
        assert rows[served["provider_id"]]["display_name"] == served["display_name"]
    assert rows[CLAUDE_PROVIDER_ID]["controls"] == ["dispatch", "review"]
    assert rows[GROK_PROVIDER_ID]["controls"] == ["dispatch"], "no review road yet"


def test_the_readme_names_the_two_owed_facts_as_owed():
    text = Path(FIXTURES, "wizard", "README.md").read_text(encoding="utf-8")
    for fact in OWED:
        assert f"`{fact}`" in text
    assert "owed" in text
