"""What this build refuses, what it only NOTICES, and what it does not isolate.

Three questions a person deciding whether to run a model over their project has
to be able to tell apart, and which one honest word -- "contained" -- runs
together:

- **refused before the spawn.** The condition is judged and the run stops with
  no child, no vendor call and nothing written. Whatever the model would have
  done, it never got the chance.
- **detected after the spawn.** The child ran. This build then looks at what it
  left and refuses to publish, verify or call it a success. The work happened;
  what is withheld is the verdict on top of it.
- **not isolated at all.** No refusal and no detection. The child is an ordinary
  process with this user's own rights, and this build imposes no operating
  system boundary on it.

The third category is the reason this module exists. A product that listed only
the first two would be telling the truth about every line it printed and lying
by omission about the shape of the whole -- and `scope`, a pinned home and a
result manifest all read like confinement to somebody who has not been told they
are not. They are a DECLARATION of what a step is for, judged after the fact
against what was touched, and this says so where the product can be read.

Each fact names the code that implements it. That is not decoration: prose about
a guard drifts from the guard, and a table nobody can check against the source
becomes marketing within two refactors. A guard resolves every one of these
names, so a protection that is renamed or deleted takes its claim down with it.

A vendor's OWN sandbox is a different kind of promise and is stated as one, but
WHICH vendor ships what is not said here. This module sits on the request path,
where nothing may know a provider's name -- the rule that keeps a request from
being routed, sized or trusted differently because of who is behind it. So the
row below says that such a mechanism exists, belongs to the vendor, and is
recorded per provider; the provider seam is where the actual flag and the
providers that have none are named, and a reader is joined to it there.

That constraint is not a workaround. A table that hard-coded two vendors would
be a table to edit every time the roster moves, in the one module whose whole
job is to be true.
"""
from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType

#: The three answers, and there is no fourth. A condition this build handles at
#: all is refused before the spawn or noticed after it; anything else belongs in
#: the third, which is a statement about what is NOT done.
REFUSED_BEFORE_SPAWN = "refused_before_spawn"
DETECTED_AFTER_SPAWN = "detected_after_spawn"
NOT_ISOLATED = "not_isolated"
CATEGORIES = (REFUSED_BEFORE_SPAWN, DETECTED_AFTER_SPAWN, NOT_ISOLATED)


#: WHEN a row is a protection of the configuration in front of a person. A
#: reference table lists everything this build can do; a screen before Confirm
#: must say what is standing HERE, so each row carries the condition it needs.
ALWAYS = "always"
#: Only where a login directory is pinned. A configuration that pins none has no
#: login-directory protections, and showing them anyway would advertise somebody
#: else's guarantees as this run's.
WITH_PINNED_LOGIN = "with_pinned_login"
#: The vendor's own mechanism, whose answer arrives as DATA from the provider's
#: row -- this module may not know which provider has what.
FROM_THE_VENDOR = "from_the_vendor"

#: What a row is FOR one configuration. Four answers, and only the first may be
#: rendered as a protection: `unknown` is an unmeasured combination, and neither
#: it nor `not_applicable` nor a stated absence is a guarantee.
ACTIVE = "active"
NOT_APPLICABLE = "not_applicable"
STATED_ABSENCE = "stated_absence"
UNKNOWN = "unknown"
STANDINGS = (ACTIVE, NOT_APPLICABLE, STATED_ABSENCE, UNKNOWN)


@dataclass(frozen=True)
class IsolationFact:
    """One protection, or one absence of protection, and where it lives.

    ``implemented_by`` is a dotted path this build resolves: module, then the
    attribute inside it. A fact whose implementation moved away is a fact this
    module can no longer make.
    """

    name: str
    category: str
    sentence: str
    implemented_by: str
    #: What has to be true for this row to be a protection of the configuration
    #: a person is looking at. Most rows hold for every one; two depend on a
    #: pinned login directory, and one is the vendor's own.
    applies_when: str = ALWAYS


ISOLATION_FACTS = (
    IsolationFact(
        "uncontained_route", REFUSED_BEFORE_SPAWN,
        "A work route that leaves the project root -- through a portal, a "
        "junction or a link planted at a name this build owns -- stops the "
        "dispatch. No task is spawned and nothing outside the root is written.",
        "conductor.command.adapters.harness_profile.uncontained_detail"),
    IsolationFact(
        "inherited_home_residue", REFUSED_BEFORE_SPAWN,
        "State of unknown ownership left under the profile home root by an "
        "earlier attempt stops the next dispatch before it mints its own.",
        "conductor.command.adapters.harness_profile.residue_detail"),
    IsolationFact(
        "login_directory_carries_configuration", REFUSED_BEFORE_SPAWN,
        "A pinned login directory that also carries configuration is refused "
        "before any task: configuration there could redirect the provider.",
        "conductor.command.adapters.harness_profile.PREFLIGHT_LOGIN_RESIDUE_DETAIL",
        WITH_PINNED_LOGIN),
    IsolationFact(
        "unroutable_model", REFUSED_BEFORE_SPAWN,
        "A model this provider has no road for is refused before the workspace "
        "turn is taken, so nothing is minted for a run that cannot happen.",
        "conductor.command.adapters.harness_profile.unroutable_model_detail"),
    IsolationFact(
        "instruction_bytes_moved", REFUSED_BEFORE_SPAWN,
        "When a proposal promised the digest of the instruction it previewed "
        "and the bytes no longer match, the dispatch stops before the spawn.",
        "conductor.command.adapters.task_binding.CHANGED_DETAIL"),
    IsolationFact(
        "work_outside_the_item", DETECTED_AFTER_SPAWN,
        "Files changed elsewhere INSIDE the observed work tree -- another work "
        "item beside this one -- are found by comparing that tree before and "
        "after the child ran. The comparison covers `work/` and nothing above "
        "it: a write the child makes outside that tree is not observed here and "
        "may not be detected at all. What a detected change costs is "
        "publication and independent verification; it is not undone.",
        "conductor.command.verify_holds.DOER_OUTSIDE_SUBTREE"),
    IsolationFact(
        "environment_value_echoed", DETECTED_AFTER_SPAWN,
        "A child that repeated an allowed environment value into its output is "
        "caught by scanning what it produced, after it produced it.",
        "conductor.command.verify_holds.DOER_ENV_ECHO"),
    IsolationFact(
        "profile_home_retained", DETECTED_AFTER_SPAWN,
        "A profile home this build could not take back is discovered when the "
        "attempt ends. The work is not published and not verified.",
        "conductor.command.verify_holds.DOER_HOME_RETAINED"),
    IsolationFact(
        "login_directory_gained_state", DETECTED_AFTER_SPAWN,
        "Undeclared state appearing in the pinned login directory is measured "
        "after the spawn, by comparing it with what was declared.",
        "conductor.command.verify_holds.CHECKER_LOGIN_RESIDUE",
        WITH_PINNED_LOGIN),
    IsolationFact(
        "review_changed_the_tree", DETECTED_AFTER_SPAWN,
        "A read-only review that wrote to the work tree is found by reading the "
        "tree afterwards, and its result is refused.",
        "conductor.command.verify_holds.DOER_TREE_CHANGED"),
    IsolationFact(
        "scope_is_declarative", NOT_ISOLATED,
        "`scope` says what a step is FOR. It is recorded, shown and judged "
        "against what was touched -- it does not stop the child reading or "
        "writing anywhere this user's own account may.",
        "conductor.command.isolation_facts.CATEGORIES"),
    IsolationFact(
        "no_operating_system_boundary", NOT_ISOLATED,
        "This build starts an ordinary process with this user's rights. It "
        "creates no container, no jail and no separate account, and it cannot "
        "confine what that process does outside the routes it watches.",
        "conductor.command.isolation_facts.CATEGORIES"),
    IsolationFact(
        "vendor_sandbox_is_the_vendors", NOT_ISOLATED,
        "Where a vendor ships a sandbox of its own, this build pins it and "
        "records it on that provider's own row -- and where a vendor ships "
        "none, nothing is claimed. Either way the mechanism is the vendor's, "
        "not this build's: a mode it was ASKED for, which its own platform may "
        "or may not enforce, and never proof that the operating system confined "
        "anything. Which providers have one is answered beside this table "
        "rather than inside it.",
        "conductor.command.adapters.harness_profile.HarnessProfile",
        FROM_THE_VENDOR),
)

#: The same facts by category, for a reader that shows them grouped. Built once
#: from the tuple above so a screen can never show a grouping the table does not
#: hold.
BY_CATEGORY = MappingProxyType({
    category: tuple(fact for fact in ISOLATION_FACTS if fact.category == category)
    for category in CATEGORIES
})


def _standing(fact: IsolationFact, auth: str | None,
              vendor_sandbox: object) -> str:
    """What this row IS for one configuration, which is not what it could be."""
    if fact.applies_when == FROM_THE_VENDOR:
        # Three answers arrive as data and stay three: nothing declared is not
        # an absence, and an absence is not a protection.
        if vendor_sandbox is None:
            return UNKNOWN
        return ACTIVE if tuple(vendor_sandbox) else STATED_ABSENCE
    if fact.category == NOT_ISOLATED:
        return STATED_ABSENCE
    if fact.applies_when == WITH_PINNED_LOGIN:
        if auth is None:
            return UNKNOWN
        return ACTIVE if auth == "subscription" else NOT_APPLICABLE
    return ACTIVE


def facts_for(auth: str | None = None,
              vendor_sandbox: object = None) -> tuple[dict[str, object], ...]:
    """The table AS IT STANDS for one selected binding.

    A reference list of everything this build can do is not an answer to "what
    is protecting the run I am about to confirm". A configuration that pins no
    login directory HAS no login-directory protections, and showing them because
    the table holds them would advertise somebody else's guarantees as this
    run's.

    Neither argument is an identity. The login mode is a word from a closed
    vocabulary and the vendor's sandbox arrives as the provider's own declared
    data -- this module never learns which provider is in front of it, which is
    the rule that keeps a request from being treated differently because of who
    is behind it.

    The rows carry NO sentence. The words live once, in the reference block a
    reader gets beside these, joined by name: repeating every paragraph under
    every binding would put the same text in one answer as many times as a run
    has bindings, and two copies of a sentence are two sentences the moment one
    of them is edited.
    """
    rows: list[dict[str, object]] = []
    for fact in ISOLATION_FACTS:
        row: dict[str, object] = {
            "name": fact.name, "category": fact.category,
            "standing": _standing(fact, auth, vendor_sandbox)}
        if fact.applies_when == FROM_THE_VENDOR:
            # The vendor's own words, per road, exactly as the provider declared
            # them -- and never rewritten here into a claim about confinement.
            row["vendor_detail"] = (
                None if vendor_sandbox is None
                else [list(pair) for pair in vendor_sandbox])
        rows.append(row)
    return tuple(rows)


def reference_block() -> tuple[dict[str, str], ...]:
    """The words themselves, once per answer, for a reader to join by name.

    One source for the text a person reads: a screen carrying its own copy would
    drift from the guards this table is written against, and the drift would be
    invisible until somebody compared them by hand.
    """
    return tuple({"name": fact.name, "category": fact.category,
                  "sentence": fact.sentence} for fact in ISOLATION_FACTS)


def facts_as_dicts() -> tuple[dict[str, str], ...]:
    """The table in the shape an API answer or a screen consumes."""
    return tuple(
        {"name": fact.name, "category": fact.category,
         "sentence": fact.sentence, "implemented_by": fact.implemented_by}
        for fact in ISOLATION_FACTS)
