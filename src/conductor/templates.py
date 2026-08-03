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

The decision-receipt paragraph is a shared constant, not copied prose: it
states what Protocol v1 can and cannot record, so a protocol version that
ships receipts must be able to correct it in one edit.
"""
from __future__ import annotations


class UnknownTemplate(Exception):
    """Raised when a template name is not one of the built-in templates."""


#: The recommended template. A caller wanting "the default" asks for this
#: rather than hardcoding a name or trusting `names()` ordering.
DEFAULT = "default-orbit"

# The one place the v1 decision semantics are stated. Rendered verbatim into
# every template that mentions `waits_on_human`; keep it comment-formatted.
_RECEIPT_LADDER = '''# Removing `waits_on_human` clears the queue but does not by itself record
# the decision. Ask the agent to append an `events.jsonl` event with
# `kind = "ok"` and `ref` set to the closed wait id.
#
# Read that ladder honestly. A wait present means a decision is expected; the
# wait removed means the request is no longer queued; a matching ok event
# means the agent reported a decision. Absence of a wait is not approval, and
# an agent's own event is not a structurally confirmed human receipt. Real
# approved / rejected / deferred states arrive with decision receipts, which
# this version of the protocol does not have.'''

_ORBIT_HEAD = '''schema_version = 1
project = "your-project"

# ---------------------------------------------------------------------------
# 1. ARCHITECTURE - what your agents are allowed to talk about.
#
# Add one [[nodes]] block per component you want reported on. The fields:
#   id          unique, and the only name a lane may use: a lane's map_status
#               keys and a finding's refs must both come from this list, and
#               anything else is warned about and ignored
#   label       the human name the panel shows
#   kind        free-form (artifact | check | component | doc | ...); the
#               panel prints it, no rule computes on it
#   depends_on  ids declared in this same file. The panel draws the graph
#               from them; status does NOT propagate along them, so a failing
#               dependency never marks its dependents failing by itself.
#
# PLACEHOLDER - replace all three below with your real components before you
# rely on anything this map reports.
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
# 2. THE ORBIT - goal -> detect -> diagnose -> design -> deliver.
#
# Phases are labels, and nothing is gated on reaching one: no readiness rule
# and no review rule references a phase. They are read, though: a lane's
# now.phase must name one of these (anything else is warned about and treated
# as undeclared), and the project's current phase is computed from the phases
# the lanes report.
# ---------------------------------------------------------------------------

[cycle]
phases = ["goal", "detect", "diagnose", "design", "deliver"]

# ---------------------------------------------------------------------------
# 3. PARTICIPANTS - one [[cycle.roles]] block per role. The fields:
#   id        unique; an agent claims it with "role" in its own lane file
#   harness   which product runs it. Informational: no rule reads it.
#   stage     which phase above this role works in. Presentation and handoff
#             metadata, and no merge rule reads it - but it MUST name one of
#             the phases above, so renaming a phase means renaming it here in
#             the same edit or the map stops validating.
#   reviews   the role ids whose findings this role owes a verdict on. The one
#             field with teeth: it is what makes the merger compute unreviewed
#             and disagreement states instead of assuming agreement.
#
# "claude-code" appears three times below. Those are three separate
# participants that happen to run the same product - three lanes, three author
# ids - not three installations of it. A participant is whoever writes a lane
# file.
#
# Nobody is staged to "goal", and that is deliberate, not an omission. The
# goal is human-owned: you state the intended outcome, the scope, what is
# explicitly out of scope, the constraints, the acceptance criteria and who
# owns the decision. The agents start at "detect". A stage with no participant
# is a legitimate shape.
# ---------------------------------------------------------------------------

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

[[cycle.roles]]
id = "reviewer"
harness = "codex"
stage = "deliver"
reviews = ["implementer"]

# ---------------------------------------------------------------------------
# 4. INVARIANTS - things that must stay true. Conduct does not enforce this
# and cannot: the entry below declares an id and a sentence, nothing more. It
# starts out reported as holding and only an agent can change that, by putting
# invariants = [{ id = "main-untouched", ok = false }] in its own lane. So a
# green invariant means "no lane has reported a breach", never "checked". A
# lane reporting an id this file does not declare is warned about and ignored.
# ---------------------------------------------------------------------------

[[invariants]]
id = "main-untouched"
text = "main branch is never committed to directly"

# ---------------------------------------------------------------------------
# 5. TWO THINGS THIS FILE DELIBERATELY DOES NOT CONTAIN. Worth reading once,
# when you wonder where they went; skip it if you came here to edit.
#
# There is no approval object, and there does not need to be. A human decision
# lives in the lane that needs it: the agent writes a waits_on_human entry the
# moment it needs your answer, and Conduct builds your queue from those
# entries across every lane. That is the whole mechanism, and it is why an
# approval request appears exactly when someone is actually blocked on you
# rather than because a map said it would.
#
'''

_ORBIT_TAIL = '''
#
# And nothing here makes a review independent. The reviewer above runs a
# different harness product from the implementer it reviews: a deliberate
# default and nothing more. Protocol v1 expresses a review obligation - who
# owes a verdict on whose findings - and excluding an author's verdict on
# their own finding gives only minimal authorship separation. It does not
# establish that a review is independent, not by harness, not by provider, not
# by model family. Change these values freely.
# ---------------------------------------------------------------------------
'''

_SOLO_HEAD = '''schema_version = 1
project = "your-project"

# One implementing role and a human decision. The smallest process that is
# still a process: use it when a second reviewing participant would be
# ceremony rather than help. The "default-orbit" template carries the full
# field reference; only what differs is explained here.

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
'''

_SOLO_TAIL = '''
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

_EMPTY = '''schema_version = 1
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
# template shows the recommended five-stage shape and documents every field;
# "single-harness" shows the smallest one.
'''

_DEFAULT_ORBIT = _ORBIT_HEAD + _RECEIPT_LADDER + _ORBIT_TAIL
_SINGLE_HARNESS = _SOLO_HEAD + _RECEIPT_LADDER + _SOLO_TAIL

# name -> (text, one-line description). Insertion order is the vending order:
# recommended first, then the smaller shapes. A caller renders this list; this
# module never formats it.
_TEMPLATES: dict[str, tuple[str, str]] = {
    DEFAULT: (
        _DEFAULT_ORBIT,
        "The recommended five-stage process: goal, detect, diagnose, design, deliver."),
    "single-harness": (
        _SINGLE_HARNESS,
        "One implementing role plus a human decision - no reviewer."),
    "empty": (
        _EMPTY,
        "The minimum map that validates: one placeholder node, no cycle."),
}


def get(name: str) -> str:
    """Return the full `map.toml` text of one named template.

    Args:
        name: A template name as listed by `names()`, or `DEFAULT`.

    Returns:
        The template's literal TOML document, comments included, ending in
        exactly one newline — ready to be written to `conductor/map.toml`
        with no further fixing up.

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
