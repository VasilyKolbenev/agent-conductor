"""The order `state.json` lists its warnings in, pinned across every rule.

`warnings` is a public, ORDERED list in a document a person reads top to bottom
and the broker fingerprints for change detection. Nothing in the merge sorts it:
the order is exactly the order the rules were called in, which makes it a fact
about `_document`'s body rather than about any one rule.

That is why it needs a guard of its own. Extracting `_document` out of `merge`
moved two rules from statements into values of the returned dict literal, and a
dict literal evaluates its values in KEY order -- so `_cycle` (at "cycle") began
running before `_invariants` (at "invariants"), which is the reverse of the
order they had run in since the merge existed. Two sentences swapped places in
`state.json` inside a refactor that changed no rule and claimed to preserve
behaviour, and no test noticed, because every other test about warnings asks
whether a sentence is PRESENT.

So this module asks the other question. One input trips six rules at once and
the whole list is compared as a sequence; a rule that moves reds here whether it
moved by one place or by five.
"""
from datetime import datetime, timezone

from conductor import merge

NOW = datetime(2026, 7, 30, 12, 0, tzinfo=timezone.utc)

#: The six rules, in the order `_document` calls them. `_readable_map` runs in
#: `merge` before `_document` exists, `_lane_view` runs once per lane while the
#: views are built, and the remaining four run inside `_document` itself.
EXPECTED = [
    "events.jsonl: skipped 2 malformed line(s)",
    "lane later: updated is in the future (clock skew?)",
    "lane early: map_status key 'ghost-node' is not a map node — ignored",
    "lane early: role 'archivist' is not in cycle.roles — treated as observer",
    "finding 'F-1': refs ['ghost-ref'] are not map nodes — ignored",
    "lane early: invariant 'ghost-invariant' is not declared in the map — ignored",
    "lane early: now.phase 'shipping' is not a cycle phase — treated as undeclared",
]


def a_map():
    """A map that declares exactly one node, one phase, one role, one invariant."""
    return {
        "schema_version": 1,
        "project": "warning-order",
        "nodes": [{"id": "api", "label": "API", "kind": "component"}],
        "cycle": {"phases": ["plan"],
                  "roles": [{"id": "implementer", "harness": "claude-code",
                             "reviews": []}]},
        "invariants": [{"id": "declared", "text": "the one that is declared"}],
    }


def a_lane(author, **over):
    data = {
        "schema_version": 1,
        "author": author,
        "role": "implementer",
        "updated": "2026-07-30T11:00:00+00:00",
        "staleness_after_minutes": 52560000,
        "now": {"phase": "plan", "focus": "f", "next": "n"},
        "map_status": {"api": "ok"},
        "findings": [],
        "invariants": [],
    }
    data.update(over)
    return {"author": author, "data": data, "error": None}


def tripping_every_rule():
    """One map and two lanes that trip all six warning-raising rules at once.

    The lane names are chosen so the assertion cannot pass by accident: `early`
    raises five of the seven sentences and `later` raises the future-dated one,
    so a rule that ran against the wrong lane would name the wrong author.
    """
    early = a_lane(
        "early",
        role="archivist",
        now={"phase": "shipping", "focus": "f", "next": "n"},
        map_status={"api": "ok", "ghost-node": "ok"},
        findings=[{"id": "F-1", "title": "t", "claim": "c", "detail": "d",
                   "evidence": "e", "refs": ["api", "ghost-ref"],
                   "severity": "blocker"}],
        invariants=[{"id": "ghost-invariant", "ok": False}])
    later = a_lane("later", updated="2026-07-30T13:00:00+00:00")
    return a_map(), [early, later]


def test_state_lists_its_warnings_in_the_order_the_rules_are_called():
    """The whole sequence, not a membership test.

    Every other warning test in this suite asks whether a sentence appears. That
    question stayed green through a refactor that reversed two of them, which is
    the entire reason this one compares a list.
    """
    map_data, lanes = tripping_every_rule()

    state = merge.merge(map_data, None, lanes, [], 2, NOW)

    assert state["warnings"] == EXPECTED


def test_the_invariant_rule_is_called_before_the_cycle_rule():
    """The exact pair the extraction swapped, named so a reader sees the defect.

    Held separately from the whole sequence above so that a future edit which
    legitimately adds or removes some OTHER warning fails one assertion with an
    obvious cause, rather than making a reader diff two seven-line lists to find
    out that this relation is still intact.
    """
    map_data, lanes = tripping_every_rule()

    warnings = merge.merge(map_data, None, lanes, [], 2, NOW)["warnings"]
    invariant = next(i for i, line in enumerate(warnings) if "invariant" in line)
    phase = next(i for i, line in enumerate(warnings) if "now.phase" in line)

    assert invariant < phase, warnings


def test_a_document_calls_no_warning_rule_from_inside_its_returned_literal():
    """Close the class, not the case.

    Reordering the two calls fixes the sentences that were observed to swap. It
    does not stop the next rule from being written at its own key, where its
    call order is decided by where its key sits in a document nobody edits for
    that reason. The three rules that take `warnings` are held to being called
    as statements, which is the property the sentences above actually depend on.
    """
    import ast
    import inspect

    body = ast.parse(inspect.getsource(merge._document)).body[0]
    returned = next(node for node in body.body if isinstance(node, ast.Return))
    called_in_the_literal = {
        node.func.id for node in ast.walk(returned)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}
    takes_warnings = {
        name for name in ("_nodes", "_findings", "_invariants", "_cycle")}

    assert not (called_in_the_literal & takes_warnings), sorted(
        called_in_the_literal & takes_warnings)
