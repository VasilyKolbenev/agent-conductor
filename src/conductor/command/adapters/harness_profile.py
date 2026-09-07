"""What a provider DECLARES: its pin shape, its profile, and their proofs.

Split out of ``headless_cli`` when the third transport landed and the module
crossed the 800-line cap. The seam is not arbitrary: every provider added to the
roster contributes profile FIELDS and no transport code, so the declarative half
grows with the roster while the behavioural half does not. Keeping them together
meant every new vendor pushed the machine closer to a cap it had no part in.

Nothing here acts. There is no subprocess, no filesystem, no identity comparison
and no product name -- one pin shape, one profile record, the validation both
owe, and the fixed sentences a receipt is built from a profile's nouns with. The
transport that reads them is in ``headless_cli``.

The sentences arrived the same way this module did: ``headless_cli`` crossed the
800-line cap again when the stdin channel grew an attempt-home seam, and the cap
forced a seam rather than a trim. They belong on this side of it. Each is a
function of a profile's ``tool_noun`` and nothing else -- no state, no path, no
child output, no decision -- so they are as declarative as the record they read
from, and the machine next door is what ACTS on them.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import PurePosixPath, PureWindowsPath

from ..contracts import ContractError, _id
from .base import AdapterContractError

#: The one control any of these adapters carries. stop, retry and switch stay
#: ABSENT rather than present and empty, because none is implemented and the
#: provider door refuses a control an adapter cannot back.
DISPATCH_CAPABILITY = "dispatch"
#: The preflight is a version print, not work: it gets its own small budget.
VERSION_TIMEOUT_SECONDS = 30
#: Capture ceiling for either spawn; the pump drains past it and drops the rest.
OUTPUT_LIMIT = 16 * 1024
#: The shape an environment variable NAME may take, so a profile's
#: code-owned environment is proved before any child could read it.
_ENV_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")


class HeadlessCliError(AdapterContractError):
    """The transport cannot honour the request without breaking one of its rules."""


#: Every sentence below names the product, so each is built from the profile's
#: nouns rather than written twice. The WORDING is the approved wording: a
#: refactor may move a promise, and may not reword one -- and moving four of them
#: across a module boundary is exactly the case that rule was written for.


def uncontained_detail(tool: str) -> str:
    """A refused route, carrying no path and no child detail.

    The route is operator state, and naming it here would put it in a receipt,
    the journal and the API at once.
    """
    return (f"a name on the {tool} workspace's own writable route is not locally "
            "contained, so nothing was minted, claimed or spawned")


def residue_detail(tool: str) -> str:
    """The home root holds state this build did not mint and may not delete.

    It carries no name and no count: the residue is operator state, and the
    operator reads it from the disk, not from a receipt.
    """
    return (f"the {tool} home root holds state this build did not mint and may "
            "not delete, so nothing was preflighted, claimed or spawned; a "
            "dispatch runs again once an operator has cleared it")


#: The PREFLIGHT's own home outlived the version spawn. The version answered,
#: but the retention promise is already broken inside this dispatch, so the task
#: never starts on top of it. Product-neutral as written, so it stays a constant.
PREFLIGHT_RESIDUE_DETAIL = (
    "the version preflight could not take back the home it minted, so this "
    "dispatch stopped before claiming or spawning the task")


def retained_detail(tool: str) -> str:
    """Appended to whatever a receipt already says when a home outlived its spawn.

    It never replaces the observed outcome it accompanies: a cleanup that did
    not happen is a second fact about the attempt, not a different result.
    """
    return (" an attempt home could not be discarded and was left standing, so "
            "the next dispatch is blocked until an operator has cleared the "
            f"{tool} home root")


def unroutable_model_detail(tool: str) -> str:
    """A configuration routed a model to a provider that cannot be told one.

    It carries the PRODUCT and never the model id: the id is operator
    configuration and this sentence reaches a receipt, the journal and the API
    at once. The operator reads which model they pinned from their own file.

    A refusal rather than a silent drop, and the difference is the whole reason
    this sentence exists: a dispatch that ran under whatever the vendor's own
    configuration chose, while an operator's file named something else, is a run
    nobody can account for afterwards.
    """
    return (f"this run's configuration pins a model for the instance and "
            f"{tool} has no reviewed flag this build can name one with, so "
            "nothing was minted, claimed or spawned")


def moving_model_detail(tool: str) -> str:
    """A configuration pinned one of this vendor's own MOVING names.

    It names the PRODUCT and never the alias, for the same reason every sentence
    here does: the alias is operator configuration and this reaches a receipt,
    the journal and the API at once. The operator reads which name they wrote
    from their own file; what this owes them is why it was refused.
    """
    return (f"this run's configuration pins one of {tool}'s moving model "
            "aliases rather than a full model name, so a durable record of it "
            "would mean a different model each time it is read; nothing was "
            "minted, claimed or spawned")


def is_absolute(path: str) -> bool:
    """Absolute under EITHER platform's rules, so a pin cannot be read two ways."""
    return PurePosixPath(path).is_absolute() or PureWindowsPath(path).is_absolute()


def reviewed_pin_path(
        value: object, name: str, error: type[HeadlessCliError]) -> str:
    """One operator pin, re-proved absolute and NUL-free before it reaches argv.

    The provider's OWN error class is carried in rather than assumed. A shared
    helper that raised the base type would quietly widen every provider's
    refusal to a type its callers do not name, which is a change of behaviour
    dressed as a refactor.
    """
    if type(value) is not str or not value or "\x00" in value:
        raise error(f"{name} must be a NUL-free non-empty path")
    if not is_absolute(value):
        raise error(f"{name} must be an absolute operator pin")
    return value


def reviewed_env_allow(
        value: object, error: type[HeadlessCliError]) -> tuple[str, ...]:
    """The allowlist carries environment NAMES; a value here would be a leak."""
    names = tuple(value)  # type: ignore[arg-type]
    if any(type(row) is not str for row in names):
        raise error("env_allow must contain environment NAMES only")
    return names


def reviewed_login(
        auth: object, auth_home: object,
        error: type[HeadlessCliError]) -> tuple[str, str]:
    """The pinned login, re-proved here as the executable path already is.

    The config door admits this pair first, and it is proved AGAIN on the way
    into a pin for the same reason a path is: a transport can be built directly,
    and a login the transport would act on may not depend on somebody else
    having checked it. The refusals are the provider's own type, so a bad pin
    still refuses as that provider.

    A directory is required exactly where the mode reads one and refused where
    it does not, so the pair can never say "a subscription with nowhere to keep
    it" or "a login directory nothing will open".
    """
    from .provider import AUTH_MODES, SUBSCRIPTION_AUTH

    if type(auth) is not str or auth not in AUTH_MODES:
        raise error(f"auth must name a reviewed login mode: {sorted(AUTH_MODES)}")
    if type(auth_home) is not str or "\x00" in auth_home:
        raise error("auth_home must be a NUL-free path")
    if auth == SUBSCRIPTION_AUTH:
        if not auth_home:
            raise error("a subscription login needs the directory it is kept in")
        if not is_absolute(auth_home):
            raise error("auth_home must be an absolute operator pin")
    elif auth_home:
        raise error("auth_home is read only by the subscription login")
    return auth, auth_home


@dataclass(frozen=True)
class ExecutablePin:
    """One operator pin, re-proved absolute before it reaches an argv.

    A SHAPE, not an identity: every product that installs as a single native
    binary pins exactly this and nothing more, so the class is neutral and the
    provider that uses it is named by its catalog row rather than by its pin.
    The interpreter-backed shape is a different class, because it has a second
    half this build must never guess at.

    It carries no provider id on purpose. A pin that named its provider would be
    a second place the identity is written down, and the factory already reaches
    the adapter through the catalog key.
    """

    executable: str
    #: The refusal type of the provider being pinned, so a bad pin refuses as
    #: that provider's own error rather than as the shared base's. REQUIRED, and
    #: proved to be one: it defaulted to the base class, which meant a pin built
    #: without thinking about it refused as a type no provider's callers name,
    #: and nothing checked that a caller passed a class at all.
    error: type[HeadlessCliError]
    env_allow: tuple[str, ...] = ()
    #: Which login this provider was pinned to, and -- for the vendor's own
    #: login -- the directory that login is kept in. A pin that says neither is
    #: the road that shipped, so every transport built before this pair existed
    #: is built the same way now.
    auth: str = "api_key"
    auth_home: str = ""

    def __post_init__(self) -> None:
        if not (isinstance(self.error, type)
                and issubclass(self.error, HeadlessCliError)):
            raise HeadlessCliError(
                "a pin's refusal type must be a headless transport error class")
        reviewed_pin_path(self.executable, "executable", self.error)
        object.__setattr__(
            self, "env_allow", reviewed_env_allow(self.env_allow, self.error))
        auth, auth_home = reviewed_login(self.auth, self.auth_home, self.error)
        object.__setattr__(self, "auth", auth)
        object.__setattr__(self, "auth_home", auth_home)


#: The two channels a one-shot task may travel by, and there is no third.
#: `argv` puts the prompt in the child's command line, where any process lister
#: on the machine can read it; `stdin` pipes it, where none can.
TASK_CHANNEL_ARGV = "argv"
TASK_CHANNEL_STDIN = "stdin"
TASK_CHANNELS = (TASK_CHANNEL_ARGV, TASK_CHANNEL_STDIN)


@dataclass(frozen=True)
class HarnessProfile:
    """Every vendor fact one headless CLI transport differs by, and nothing else.

    Each field is a published fact about a product, and the module that builds
    one is expected to cite where it was read. ``exit_codes_published`` is the
    field that most changes what a receipt may CLAIM: a vendor that documents no
    exit-code contract for its one-shot mode has not told this build what a zero
    means, so the receipt says exactly that rather than quietly reading it the
    way a documented tool's zero is read.
    """

    #: The product, as a receipt names it: "dsh", "Kimi Code".
    tool_noun: str
    #: The unit of work, as a receipt names it: "dsh task", "Kimi Code prompt".
    task_noun: str
    display_name: str
    vendor: str
    docs_url: str
    #: The EXACT published version the build was reviewed against. A preflight
    #: reading anything else refuses; "close enough" is not a safe reading of a
    #: version string for tools that ship breaking changes between minors.
    reviewed_version: str
    #: The two subtrees this provider owns beneath the project root.
    home_dir: str
    marker_dir: str
    #: The environment NAMES this provider owns. Only names live in durable
    #: config; the home's VALUE is minted per attempt and never written down.
    home_env: str
    #: Every OTHER environment variable this build sets for a spawn, as (name,
    #: value) pairs the vendor documents. A set rather than one pair, and a
    #: literal VALUE rather than a notion of "disabled", because the vendors do
    #: not agree on polarity: dsh and Kimi Code read a DISABLE flag where ``1``
    #: means off, and Grok Build reads four ENABLED flags where ``0`` means off.
    #: Carrying the published pair keeps the base ignorant of which is which.
    forced_env: tuple[tuple[str, str], ...]
    #: The code-owned version argv. No caller ever contributes a flag.
    version_argv: tuple[str, ...]
    #: The id KIND a minted attempt home is named by, so a home standing under
    #: the home root says which provider left it.
    home_id_kind: str
    #: Whether the vendor publishes exit-code meanings for its one-shot mode.
    exit_codes_published: bool
    capability: str = DISPATCH_CAPABILITY
    output_limit: int = OUTPUT_LIMIT
    version_timeout_seconds: int = VERSION_TIMEOUT_SECONDS
    #: The code-owned argv that asks this vendor whether its own login answers,
    #: or empty for a provider whose transport drives no login. Read for its EXIT
    #: CODE alone: the answer describes somebody's account, and a build that
    #: parsed and reported it would put account state into a durable receipt.
    #: It is asked only on the subscription road, where there is a login to ask
    #: about, and it is never a substitute for a real run.
    login_argv: tuple[str, ...] = ()
    #: WHERE this vendor's one-shot mode takes the task. A closed choice of two,
    #: and it is structural rather than advisory: the transport calls a
    #: DIFFERENT argv builder for each, and the one it calls for `stdin` takes
    #: no task argument at all.
    #:
    #: That is the whole point. An earlier attempt asked an argv builder twice
    #: with two probe texts and compared the answers, which proves only that
    #: those two calls agreed -- a builder can return a constant for both probes
    #: and embed a third instruction, and one did, in a review probe. Two
    #: observations are not independence. A parameter that does not exist is.
    #:
    #: `argv` is the default, so every provider that shipped before this field
    #: is unchanged and unaware of it.
    task_channel: str = TASK_CHANNEL_ARGV
    #: The flag this vendor names a model with, or EMPTY when this build has
    #: established none for it.
    #:
    #: Empty is a statement and not a gap. A model an operator pins reaches a
    #: child only through a flag somebody read in that vendor's own published
    #: material, and inventing one would be the defect this roster has already
    #: paid for twice on version prints. So a provider with no flag here refuses
    #: an action whose configuration routes a model to it, rather than dropping
    #: the routing and running whatever the vendor's own configuration decides
    #: -- a run that silently used another model than the one an operator
    #: configured is worse than a run that did not happen.
    #:
    #: **What the shared record proves about it is the TOKEN, never the FORM.**
    #: A first version of the constructor demanded a leading `-`, reasoning that
    #: a token without one is a positional to every launcher. That is Unix
    #: syntax written into a provider-neutral record: `/model` is an ordinary
    #: Windows option, and a vendor may take its model as a separate leading
    #: token altogether. The guard would have forced an edit to THIS module
    #: before a valid future provider could declare itself, which is exactly the
    #: hardcoding this seam exists to avoid. So the constructor holds it to what
    #: it can know of any vendor -- an exact string, empty or one NUL-free token
    #: with no whitespace -- and the spelling and the position are the provider
    #: module's own declaration, proved by that provider's exact argv test
    #: against a real spawn.
    model_flag: str = ""
    #: The names this vendor publishes as MOVING: aliases that resolve to
    #: whatever it ships this week rather than to one build.
    #:
    #: Not a catalogue of models, and deliberately not: this build cannot know
    #: which model ids a vendor has, and a list it tried to keep would be wrong
    #: the day after it was written. What it CAN know is the much smaller fact
    #: each vendor states about its own naming -- which of its names are not a
    #: single model -- and that is the fact that settles the question.
    #:
    #: A configuration pinning one of these is refused before anything is
    #: minted, claimed or spawned. A durable record naming a moving alias means
    #: a different model each time it is read, so nothing afterwards can be
    #: checked against the model that really did the work. Empty is the honest
    #: default: a vendor this build has read no such statement from publishes no
    #: moving names as far as this build knows, and refuses nothing.
    #:
    #: A TUPLE, and the constructor holds it to that rather than to "iterable".
    #: A bare string is iterable, so the membership test that refuses a moving
    #: alias would silently become a SUBSTRING search -- `"opus"` would refuse a
    #: model called `"op"` and admit `claude-opus-5`, wrong in both directions
    #: at once and invisible to every alias case in the suite.
    #:
    #: Each name goes through `_id`, the CONFIGURATION's own door for a pinned
    #: model, and that is load-bearing rather than tidy: an alias declared under
    #: any other grammar could never equal a pinned one, so the comparison that
    #: refuses it could never match -- a policy that reads as if it were doing
    #: something.
    unstable_models: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """Prove the environment this profile forces, at construction.

        A profile is code, written once per provider, so every fault here is a
        programming fault -- and every one of them used to surface at the FIRST
        SPAWN instead, as a raw ``ValueError`` out of ``dict()`` that sailed past
        the transport's own error type and reached a caller under a sentence
        blaming the operator's pinned build. A code-owned mistake must not be
        reported as an operator's.

        The home collision is the one that matters most: a pair named for
        ``home_env`` would relocate the child's home away from the one this
        dispatch minted and discards, which is the whole retention promise.
        """
        seen: set[str] = set()
        for row in self.forced_env:
            if type(row) is not tuple or len(row) != 2:
                raise HeadlessCliError(
                    "each forced environment row is a (name, value) pair")
            name, value = row
            if type(name) is not str or _ENV_NAME.fullmatch(name) is None:
                raise HeadlessCliError(
                    f"{name!r} is not an environment variable name")
            if type(value) is not str or "\x00" in value:
                raise HeadlessCliError(
                    f"the value forced for {name} must be NUL-free text")
            if name in seen:
                raise HeadlessCliError(
                    f"{name} is forced twice, so one of the two values is lost")
            seen.add(name)
        if self.home_env in seen:
            raise HeadlessCliError(
                f"{self.home_env} carries the home this dispatch minted and "
                "discards; forcing it would relocate the child's home and "
                "retain the state this build promises not to keep")
        if _ENV_NAME.fullmatch(self.home_env) is None:
            raise HeadlessCliError(
                f"{self.home_env!r} is not an environment variable name")
        if self.task_channel not in TASK_CHANNELS:
            raise HeadlessCliError(
                f"a task travels by one of {TASK_CHANNELS}, not "
                f"{self.task_channel!r}")
        self._hold_model_routing()

    def _hold_model_routing(self) -> None:
        """Prove the two model-routing declarations, at construction like the rest.

        They arrived without this and the omission had teeth. A ``model_flag``
        carrying a NUL is a code-owned mistake that surfaces at the FIRST SPAWN,
        under a sentence about the operator's pinned build -- which is exactly
        the reporting failure this whole method exists to prevent. And a
        ``unstable_models`` given a bare STRING is still iterable, so the
        membership test that refuses a moving alias silently becomes a SUBSTRING
        search: ``"opus"`` would then refuse a model called ``"op"`` and admit
        ``claude-opus-5`` -- wrong in both directions at once, and silent in
        both.

        What each field may and may not be held to is written where the field
        is declared. The short of it: this proves the TOKEN and never the FORM,
        and the element grammar is the configuration's own rather than a second
        one invented here.
        """
        if type(self.model_flag) is not str:
            raise HeadlessCliError("model_flag must be a string, or empty")
        if self.model_flag and (
                "\x00" in self.model_flag
                or self.model_flag.split() != [self.model_flag]):
            raise HeadlessCliError(
                "model_flag must be one NUL-free token with no whitespace")
        if type(self.unstable_models) is not tuple:
            raise HeadlessCliError(
                "unstable_models must be a tuple of model names; a string is "
                "iterable and would turn the alias check into a substring search")
        named: set[str] = set()
        for name in self.unstable_models:
            try:
                _id("declared unstable model", name)
            except ContractError as error:
                raise HeadlessCliError(str(error)) from None
            if name in named:
                raise HeadlessCliError(
                    f"{name} is declared unstable twice")
            named.add(name)
        if self.unstable_models and not self.model_flag:
            # A vendor this build cannot name a model to cannot be sent one, so
            # nothing it declared unstable could ever be routed to it. The
            # declaration would read as a policy that is doing something.
            raise HeadlessCliError(
                "unstable_models declares moving names for a provider this "
                "build has no model flag for, so none of them can be routed")


def bounded_output(profile, asked: int | None) -> int:
    """The output ceiling for one spawn: the provider's, or less if a plan said so.

    A CEILING and never a raise. `HarnessProfile.output_limit` is what this
    build's transport for that vendor was reviewed against, so a plan may ask a
    step to write less and can never ask a provider to tolerate more. The same
    rule `timeout_seconds` already follows, and for the same reason: a bound the
    requester could widen is not a bound.

    `None` means no plan named one -- a review, a version probe -- and the
    provider's own limit stands, exactly as it did before a profile meant
    anything.
    """
    if asked is None:
        return profile.output_limit
    return min(profile.output_limit, asked)
