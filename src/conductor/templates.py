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
#
# Phases are labels, and nothing is gated on reaching one: no readiness rule
# and no review rule references a phase. They are read, though. A lane's
# now.phase must name one of these (anything else is warned about and treated
# as undeclared), and the project's current phase is computed from the phases
# the lanes report. It is `stage` below that no merge rule reads.
#
# Renaming a phase therefore means renaming it in every role staged to it, in
# the same edit: a `stage` naming a phase this list does not declare is a map
# error, and an unreadable map leaves the whole project status unknown.
# ---------------------------------------------------------------------------

[cycle]
phases = ["goal", "detect", "diagnose", "design", "deliver"]

# No role is staged to "goal", and that is deliberate, not an omission. The
# goal is human-owned: you state the intended outcome, the scope, what is
# explicitly out of scope, the constraints, the acceptance criteria and who
# owns the decision. The agents start at "detect". A stage with no participant
# is a legitimate shape.
#
# The final human decision is not an object in this file either, and does not
# need to be. A decision lives in the lane that needs it: the agent writes a
# waits_on_human entry the moment it needs your answer, and Conduct builds
# your queue from those entries across every lane. That is the whole
# mechanism, and it is why an approval request appears exactly when someone is
# actually blocked on you rather than because a map said it would.
#
# Removing `waits_on_human` clears the queue but does not by itself record the
# decision. Ask the agent to append an `events.jsonl` event with `kind = "ok"`
# and `ref` set to the closed wait id.
#
# Read that ladder honestly. A wait present means a decision is expected; the
# wait removed means the request is no longer queued; a matching ok event
# means the agent reported a decision. Absence of a wait is not approval, and
# an agent's own event is not a structurally confirmed human receipt. Real
# approved / rejected / deferred states arrive with decision receipts, which
# this version of the protocol does not have.
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
# and the acceptance criteria. The decision at the end is not an object in
# this file either - it is a waits_on_human entry the implementer writes when
# it needs your answer, and your queue is built from those entries.
#
# Removing `waits_on_human` clears the queue but does not by itself record the
# decision. Ask the agent to append an `events.jsonl` event with `kind = "ok"`
# and `ref` set to the closed wait id. Even then: absence of a wait is not
# approval, and an agent's own event is not a structurally confirmed human
# receipt. Real approved / rejected / deferred states arrive with decision
# receipts, which this version of the protocol does not have.
#
# Know what one role costs you. With no role declaring `reviews`, nothing owes
# the implementer a verdict - and its findings do not come out unreviewed,
# they come out `agreed`, which the panel draws as a green check. That is
# vacuous truth, not consent: "every reviewing role has confirmed" holds
# trivially when there are no reviewing roles. The panel prints a
# "no reviewer assigned" hint beside such a finding, and that hint is the only
# thing standing between it and a real review. Add a second role with
# reviews = ["implementer"] when you want the obligation to exist.

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
