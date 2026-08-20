"""Named starting maps — the *text* of a `conductor/map.toml`, not a dict.

`map.toml` is committed and hand-edited, so the comments are part of the
deliverable: a template that validates but explains nothing teaches the user
the wrong shape. Each template is therefore a literal TOML document, and every
one of them must parse and pass `schema.validate_map` with zero errors and
zero warnings.

Four are vended: `default-orbit` (the recommended five-stage process, and what
`conduct init` writes when nothing else is asked for), `single-harness` (one
implementing role plus a human decision), `empty` (the minimum that
validates), and `minimal` (the spec's own §2 example, vended from
`prompts.MAP_EXAMPLE`, which a guard holds byte-for-byte against the fenced
block in `spec/PROTOCOL.md` so the spec and the scaffold cannot drift in
silence). This module renders no UI — `names()` returns data for a caller to
display, never display text.

`get()` takes the three values `conduct init` fills in — project name, primary
harness, reviewing harness — and rewrites both the TOML assignments and the
comment sentences that state facts *about* those values, so a generated map
never contradicts itself. Omitting them reproduces the template verbatim.

The decision-receipt paragraph is a shared constant, not copied prose: it
states what Protocol v1 can and cannot record, so a protocol version that
ships receipts must be able to correct it in one edit.
"""
from __future__ import annotations

import re

from conductor import prompts


class UnknownTemplate(Exception):
    """Raised when a template name is not one of the built-in templates."""


class InvalidName(ValueError):
    """Raised when a project name or harness id is outside the allowed set."""


class TemplateOutOfSync(Exception):
    """Raised when a template holds a value assignment the substitution cannot rewrite.

    A programming error, not user error: it means an edit to a template has
    outrun the substitution that fills it in.
    """


#: Every character a caller-supplied project name or harness id may contain.
#: These values are interpolated into TOML *text*, where a quote, a backslash,
#: a newline or a control character breaks the file — or, worse, silently
#: changes what it means. Real product names carry spaces and parentheses
#: ("Claude Code", "Qwen Code (beta)"), so those are in; nothing that TOML
#: gives a meaning to is. Rejected, never escaped into something clever.
_ALLOWED_CHAR_RE = re.compile(r"[\w .+()-]")

#: The whole rule: an allowed run, opened by a letter or digit, at most 64
#: characters. Unicode-aware — a project name is a name, not an identifier.
NAME_RE = re.compile(r"\A[^\W_][\w .+()-]{0,63}\Z")

#: `NAME_RE` in words. Public because the sentence a rejected caller has to act
#: on must be the same one wherever the rejection happens.
NAME_RULE = ("letters, digits, space, and . _ - + ( ) only, starting with a "
             "letter or digit, at most 64 characters")


def _offence(value: str) -> str:
    """Name what is wrong with a rejected value, most specific reason first."""
    if not isinstance(value, str):
        return f"it is a {type(value).__name__}, not text"
    for char in value:
        if not _ALLOWED_CHAR_RE.fullmatch(char):
            return f"the character {char!r} is not allowed"
    if not value:
        return "it is empty"
    if len(value) > 64:
        return f"it is {len(value)} characters long"
    return f"it starts with {value[0]!r}"


def check_name(kind: str, value: str) -> str:
    """Return `value` unchanged if it is a legal name, else raise.

    Args:
        kind: What is being named, for the message (e.g. `"project name"`).
        value: The candidate name.

    Returns:
        `value`, unchanged — so callers can validate and assign in one step.

    Raises:
        InvalidName: If `value` is not a `NAME_RE` name. The message names
            three things: the field, the character that failed, and the format
            allowed instead — enough to fix it without seeing the regex.
    """
    if not isinstance(value, str) or not NAME_RE.fullmatch(value):
        raise InvalidName(f"invalid {kind} {value!r}: {_offence(value)}; "
                          f"allowed: {NAME_RULE}")
    return value


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
# "claude-code" appears three times below. Those are separate participants
# that happen to run the same product - separate lanes, separate author ids -
# not separate installations of it. A participant is whoever writes a lane
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
    # The spec's §2 example, vended from prompts.MAP_EXAMPLE and held against
    # the fenced block in spec/PROTOCOL.md by a guard, so the spec and this
    # template cannot say two different things without a test naming it.
    # It is quoted verbatim, which is why it alone carries realistic node
    # labels rather than the PLACEHOLDER convention the other three follow —
    # and why it is last: it is kept, not recommended. MAP_EXAMPLE ends without
    # a newline; every template must end in exactly one.
    "minimal": (
        prompts.MAP_EXAMPLE + "\n",
        "The spec's own example map — what `conduct init` wrote before v0.2."),
}


# What the literal templates above say, and therefore what `get()` swaps out
# when a caller supplies its own values. `minimal` is quoted from the spec and
# names its own example project, so both placeholders are recognised.
_DEFAULT_PROJECT = "your-project"
_LEGACY_PROJECT = "web-app"
_DEFAULT_PRIMARY = "claude-code"
_DEFAULT_REVIEWER = "codex"
#: The shipped document, as ONE value rather than three loose ones. The
#: question `_substitute` asks with it is about the DOCUMENT -- did the caller
#: replace anything? -- and not about any harness named inside it, and naming
#: it that way is what keeps this module inside the provider-identity gate:
#: comparing the three constants separately reads, to anything examining the
#: text, exactly like deciding something by a vendor's name.
_SHIPPED = (_DEFAULT_PROJECT, _DEFAULT_PRIMARY, _DEFAULT_REVIEWER)

# The two places `default-orbit` states a fact ABOUT its harness values rather
# than merely using them. Rewriting the values without these would leave a
# generated map asserting something its own role blocks contradict.
_COUNT_CLAIM = f'# "{_DEFAULT_PRIMARY}" appears three times below.'
_DIFFERENT_PRODUCT = (
    "The reviewer above runs a\n"
    "# different harness product from the implementer it reviews: a deliberate\n"
    "# default and nothing more.")
_SAME_PRODUCT = (
    "The reviewer above runs the\n"
    "# same harness product as the implementer it reviews, because that is what\n"
    "# you chose - and nothing here checks it either way.")


#: Every assignment the substitution knows how to rewrite. `_check_in_sync`
#: requires that a template hold no OTHER `project =` or `harness =` line:
#: matching on exact text is what preserves inline comments, but it also means
#: a reformatted line would miss silently — and a silent miss ships a committed
#: map naming a harness the user never chose.
_SWAPPABLE = (f'project = "{_DEFAULT_PROJECT}"',
              f'project = "{_LEGACY_PROJECT}"',
              f'harness = "{_DEFAULT_PRIMARY}"',
              f'harness = "{_DEFAULT_REVIEWER}"')

_ASSIGNMENT_RE = re.compile(r"\A\s*(project|harness)\s*=")


def _assignment(line: str) -> str:
    """One line's assignment: everything before its comment, right-stripped.

    A comment line yields `""`, so it can never match; a trailing
    `# informational` is held back and survives the swap. Safe because no
    value we substitute may contain a `#` — `NAME_RE` forbids it.
    """
    return line.partition("#")[0].rstrip()


def _check_in_sync(name: str, text: str) -> None:
    """Raise if a template holds a value assignment the substitution would miss.

    Args:
        name: The template's name, for the message.
        text: The template document.

    Raises:
        TemplateOutOfSync: If any `project =` or `harness =` line is not one of
            `_SWAPPABLE`. Run on every `get()`, parameterised or not, so the
            desync is reported the first time anyone asks for the template
            rather than only to the caller unlucky enough to pass a value.
    """
    for number, line in enumerate(text.split("\n"), 1):
        assignment = _assignment(line)
        if _ASSIGNMENT_RE.match(assignment) and assignment not in _SWAPPABLE:
            raise TemplateOutOfSync(
                f"template {name!r} line {number} is {assignment!r}, an assignment "
                f"`conduct init` must be able to rewrite but does not recognise "
                f"(known: {', '.join(_SWAPPABLE)}). Restore one of those spellings, "
                f"or add this one to _SWAPPABLE. Left alone it is skipped in "
                f"silence, and the user commits a map naming a harness they never "
                f"chose.")


def _swap_assignment(line: str, swap: dict[str, str]) -> str:
    """Rewrite one line's assignment if it is one we swap, keeping its comment."""
    assignment = _assignment(line)
    replacement = swap.get(assignment)
    if replacement is None:
        return line
    code, hash_sign, comment = line.partition("#")
    return replacement + code[len(assignment):] + hash_sign + comment


def _times(count: int) -> str:
    """`3` -> `three times`. Keeps the counted sentence grammatical at any count."""
    if count == 1:
        return "once"
    if count == 2:
        return "twice"
    return {3: "three times", 4: "four times", 5: "five times",
            6: "six times"}.get(count, f"{count} times")


def _substitute(text: str, project: str, primary: str, reviewer: str) -> str:
    """Rewrite one template's project and harness values, prose included.

    Args:
        text: The literal template document.
        project: The `project` value to write.
        primary: The harness id of the implementing roles.
        reviewer: The harness id of the reviewing roles.

    Returns:
        The rewritten document. Assignments are matched whole, so a harness id
        occurring inside a sentence is never rewritten by accident; the two
        sentences that state a fact about those values are named above and
        rewritten deliberately.
    """
    if (project, primary, reviewer) == _SHIPPED:
        return text
    # Built in one pass off the ORIGINAL values, so swapping the two default
    # harnesses for each other cannot collapse them onto one.
    swap = {f'project = "{_DEFAULT_PROJECT}"': f'project = "{project}"',
            f'project = "{_LEGACY_PROJECT}"': f'project = "{project}"',
            f'harness = "{_DEFAULT_PRIMARY}"': f'harness = "{primary}"',
            f'harness = "{_DEFAULT_REVIEWER}"': f'harness = "{reviewer}"'}
    body = "\n".join(_swap_assignment(line, swap) for line in text.split("\n"))
    # Counted from the result, not asserted: pick the reviewer's harness for
    # the implementing roles too and the sentence has to say five, not three.
    appearances = sum(1 for line in body.split("\n")
                      if _assignment(line) == f'harness = "{primary}"')
    body = body.replace(_COUNT_CLAIM,
                        f'# "{primary}" appears {_times(appearances)} below.')
    if primary == reviewer:
        body = body.replace(_DIFFERENT_PRODUCT, _SAME_PRODUCT)
    return body


def get(name: str, *, project: str | None = None, primary: str | None = None,
        reviewer: str | None = None) -> str:
    """Return the full `map.toml` text of one named template.

    Args:
        name: A template name as listed by `names()`, or `DEFAULT`.
        project: The `project` value to write, or None for the built-in
            placeholder.
        primary: The harness id of the implementing roles, or None for the
            built-in default.
        reviewer: The harness id of the reviewing roles, or None for the
            built-in default. Templates that declare no reviewer ignore it.

    Returns:
        The template's literal TOML document, comments included, ending in
        exactly one newline — ready to be written to `conductor/map.toml`
        with no further fixing up. Passing None for all three reproduces the
        template verbatim.

    Raises:
        UnknownTemplate: If `name` is not a built-in template.
        InvalidName: If any supplied value is not a `NAME_RE` name. Rejected
            here, at the boundary, rather than escaped into the TOML.
        TemplateOutOfSync: If the template holds a `project =` or `harness =`
            line the substitution cannot rewrite.
    """
    entry = _TEMPLATES.get(name)
    if entry is None:
        known = ", ".join(_TEMPLATES)
        raise UnknownTemplate(f"unknown template {name!r} (available: {known})")
    _check_in_sync(name, entry[0])
    return _substitute(
        entry[0],
        _DEFAULT_PROJECT if project is None else check_name("project name", project),
        _DEFAULT_PRIMARY if primary is None else check_name("harness id", primary),
        _DEFAULT_REVIEWER if reviewer is None else check_name("harness id", reviewer))


def names() -> list[tuple[str, str]]:
    """Return the available templates as `(name, one-line description)` pairs.

    Returns:
        The pairs in vending order, recommended first. Data, not display text:
        the caller decides how to render them.
    """
    return [(name, description) for name, (_, description) in _TEMPLATES.items()]
