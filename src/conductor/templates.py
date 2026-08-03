"""Named starting maps — the *text* of a `conductor/map.toml`, not a dict.

`map.toml` is committed and hand-edited, so the comments are part of the
deliverable: a template that validates but explains nothing teaches the user
the wrong shape. Each template is therefore a literal TOML document, and every
one of them must parse and pass `schema.validate_map` with zero errors and
zero warnings.

Three are vended: `default-orbit` (the recommended five-stage process),
`single-harness` (one implementing role plus a human decision), and `empty`
(the minimum that validates). Nothing here is wired to the CLI — `names()`
returns data for a caller to render, never rendered text.
"""
from __future__ import annotations


class UnknownTemplate(Exception):
    """Raised when a template name is not one of the built-in templates."""


DEFAULT_ORBIT = '''schema_version = 1
project = "your-project"

# ---------------------------------------------------------------------------
# Architecture. PLACEHOLDER - replace these three nodes with your real
# components before you rely on anything this map reports. A node is one
# concrete piece of work or one part of the system that a lane can report a
# status for; ids must be unique, and lanes may only report on ids declared
# here.
# ---------------------------------------------------------------------------

[[nodes]]
id = "placeholder-contracts"
label = "PLACEHOLDER - replace with your shared contracts"
kind = "artifact"

[[nodes]]
id = "placeholder-service"
label = "PLACEHOLDER - replace with your service or component"
kind = "artifact"
depends_on = ["placeholder-contracts"]

[[nodes]]
id = "placeholder-checks"
label = "PLACEHOLDER - replace with your test suite or CI job"
kind = "check"
depends_on = ["placeholder-service"]

# ---------------------------------------------------------------------------
# The Default Orbit: goal -> detect -> diagnose -> design -> deliver.
# Phases are labels. They carry no protocol semantics: no merge rule reads
# them, nothing is gated on reaching one, and you may rename or drop them.
# ---------------------------------------------------------------------------

[cycle]
phases = ["goal", "detect", "diagnose", "design", "deliver"]

# No role is staged to "goal", and that is deliberate, not an omission. The
# goal is human-owned: you state the intended outcome, the scope, what is
# explicitly out of scope, the constraints, the acceptance criteria and who
# owns the decision. The agents start at "detect". A stage with no participant
# is a legitimate shape.
#
# There is likewise no approval object anywhere in this file. Protocol v1 has
# no dedicated human-gate entity - they were considered and cut - and the
# human queue is computed from the lanes instead. So the final approval is a
# waits_on_human entry written by whichever agent needs the decision, at the
# moment it needs it. Adding an "approval" node or a "gate" role here would
# buy you nothing the queue does not already give you.
#
# "claude-code" appears three times below. Those are three separate
# participants that happen to run the same harness product - three lanes,
# three author ids - not three installations of it. A participant is whoever
# writes a lane file. `harness` is informational: no rule reads it.

[[cycle.roles]]
id = "scout"
harness = "claude-code"
stage = "detect"
reviews = []

[[cycle.roles]]
id = "diagnostician"
harness = "codex"
stage = "diagnose"
reviews = ["scout"]

[[cycle.roles]]
id = "architect"
harness = "claude-code"
stage = "design"
reviews = []

[[cycle.roles]]
id = "implementer"
harness = "claude-code"
stage = "deliver"
reviews = []

# The reviewer runs a different harness product from the implementer it
# reviews. That is a deliberate default and nothing more. Protocol v1
# expresses a review obligation - who owes a verdict on whose findings - and
# excluding an author's verdict on their own finding gives only minimal
# authorship separation. It does not establish that a review is independent,
# not by harness, not by provider, not by model family. Change these values
# freely.

[[cycle.roles]]
id = "reviewer"
harness = "codex"
stage = "deliver"
reviews = ["implementer"]

[[invariants]]
id = "main-untouched"
text = "main branch is never committed to directly"
'''

SINGLE_HARNESS = '''schema_version = 1
project = "your-project"

# One implementing role and a human decision. The smallest process that is
# still a process: use it when a second reviewing participant would be
# ceremony rather than help.

# PLACEHOLDER - replace with your real component.

[[nodes]]
id = "placeholder-service"
label = "PLACEHOLDER - replace with your service or component"
kind = "artifact"

[cycle]
phases = ["goal", "deliver"]

# "goal" is human-owned and carries no role: you set the outcome, the scope
# and the acceptance criteria. The approval at the end is not an object in
# this file either - it is a waits_on_human entry the implementer writes when
# it needs your decision, and the human queue is built from those.
#
# Be aware of what one role costs you: with nobody declared to review the
# implementer, no role owes a verdict on its findings, so Conduct will not
# report them as unreviewed. Add a second role with reviews = ["implementer"]
# when you want that obligation to exist.

[[cycle.roles]]
id = "implementer"
harness = "claude-code"
stage = "deliver"
reviews = []
'''

EMPTY = '''schema_version = 1
project = "your-project"

# The minimum map that validates: one node, no cycle. A starting point to
# grow, not a finished map.
#
# Required: schema_version = 1, and at least one node. Node ids must be
# unique, and every depends_on entry must name a node declared in this file.
# Everything else - project, cycle, invariants - is optional.
#
# PLACEHOLDER - replace the node below with a real component of your system,
# then add one [[nodes]] block per component you want reported on. Lanes may
# only report a status for ids declared here, so this list is what your agents
# are allowed to talk about.

[[nodes]]
id = "placeholder"
label = "PLACEHOLDER - replace with a real component"
kind = "artifact"

# When you are ready to describe a process, add a [cycle] table with a phases
# list and one [[cycle.roles]] block per participant. The "default-orbit"
# template shows the recommended five-stage shape; "single-harness" shows the
# smallest one.
'''

# name -> (text, one-line description). Insertion order is the vending order:
# recommended first, then the smaller shapes. A caller renders this list; this
# module never formats it.
_TEMPLATES: dict[str, tuple[str, str]] = {
    "default-orbit": (
        DEFAULT_ORBIT,
        "The recommended five-stage process: goal, detect, diagnose, design, deliver."),
    "single-harness": (
        SINGLE_HARNESS,
        "One implementing role plus a human decision - no reviewer."),
    "empty": (
        EMPTY,
        "The minimum map that validates: one placeholder node, no cycle."),
}


def get(name: str) -> str:
    """Return the full `map.toml` text of one named template.

    Args:
        name: A template name as listed by `names()`.

    Returns:
        The template's literal TOML document, comments included, ready to be
        written to `conductor/map.toml`.

    Raises:
        UnknownTemplate: If `name` is not a built-in template.
    """
    entry = _TEMPLATES.get(name)
    if entry is None:
        known = ", ".join(_TEMPLATES)
        raise UnknownTemplate(f"unknown template {name!r} (available: {known})")
    return entry[0]


def names() -> list[tuple[str, str]]:
    """Return the available templates as `(name, one-line description)` pairs.

    Returns:
        The pairs in vending order, recommended first. Data, not display text:
        the caller decides how to render them.
    """
    return [(name, description) for name, (_, description) in _TEMPLATES.items()]
