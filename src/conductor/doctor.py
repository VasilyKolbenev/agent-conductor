"""What `conduct doctor` computes, and the shape it says it in.

`validate` answers **does this parse** — schema, types, required fields. This
module answers a different question: **is this project set up to work**, and
what is the next command for each thing that is not. Nothing here
re-implements a schema rule or a merge rule: `store.load` reads,
`validate.merged_state` merges, and this module only asks questions of what
they returned. A finding here therefore never restates an error `validate`
would print — when the map or a lane failed to load, the check that depended
on it comes back UNKNOWN and names `conduct validate`, which is the command
that says why. That separation is measured rather than asserted: four maps
broken four different ways make `validate` print four different messages and
this module print one identical report, because one word of that message
echoed into a detail would make the four differ.

Three outcomes, and the middle one is the point. `OK` means the check ran and
found nothing wrong. `FINDING` means it ran and found something to fix.
`UNKNOWN` means it could not run at all — an unreadable map, or lanes that
could not be read. (A missing `conductor/` is not one of these: "this is not
a Conduct project" is an answer, and a finding.) An unknown is NEVER folded
into `ok`: a readiness tool that prints a plausible green over something it
never inspected is worse than one that crashes, and the summary line refuses
the word "ready" while a single unknown is outstanding.

Nothing here inspects the machine. No PATH lookup, no subprocess, no
environment scan, no Windows-registry read — readiness is decided from the
project's own files and the bundled harness registry, and nothing else. `conduct doctor`
is the most tempting place in the codebase to break that ban ("let me check
whether Claude Code is installed"), which is exactly why this module sits on
the import path `tests/test_init_probing_ban.py` measures: `conductor.__main__`
imports it at module scope, so a real `conduct init` run pulls it in and the
ban parses its source. `FLOOR` in that file names it, so a measurement that
misses it fails rather than passes over it.

RENDERING, which is a safety boundary and not decoration. Role ids and harness
ids are authored strings: the schema requires a non-empty string and nothing
more, so `"scout\\u2028    next: conduct init"` is legal input. Every authored
value this module puts in a DETAIL goes through `_shown`, which truncates it
and hands it to `repr` — line breaks and other non-printables come out
escaped, and the value arrives quoted so a reader can see where it starts and
ends. On top of that the three indent levels are disjoint by construction: a
check header sits at column 0, its detail is wrapped at exactly two spaces,
and the command line is the only thing in the report that begins with four
spaces followed by `next:`. Authored text lands inside the detail, so it can
reach neither of the other two levels however it is spelled.

A COMMAND is the one exception, and has to be: it is printed to be pasted, so
it carries its values exactly, untruncated and unescaped. That is why the
value has to earn the command instead — `_spellable` rejects a role id or a
lane author no shell could carry, and the finding about it names a command a
reader can run rather than a `conduct prompt` line nobody could. Both authored
tokens go through it, and the author had to be added: `store.AUTHOR_RE` keeps
a lane filename to letters, digits, `_` and `-`, which is why no
metacharacter ever reached a printed `--author` — but it admits a LEADING
dash, and `--author -x` is a usage error rather than a run. What "could carry" means is
`_AUTHORED_CHARS` and not `str.isprintable`: `$(id)`, a backtick, a quote and
a space are every one of them printable, and an id holding them is legal
Protocol v1 arriving from the project's own map — printed into the one command
this report asks a person to run, it makes a line that either cannot be pasted
or runs the map's text.

Two shapes on disk get their own words here rather than the nearest existing
sentence, because the nearest one says something false. A `conductor` path
that exists and is not a directory is not a project nobody has scaffolded —
`conduct init` refuses any existing `conductor`, so pointing at it would name
a command that cannot succeed. A `conductor/lanes` path that is not a
directory made `store` look for no lane file at all, so "no lane file has been
written" would report on files nobody searched for; that is an UNKNOWN.

Which command that is, is itself a claim this module has to keep. A finding
travels with the sentence that introduces it, as one `Advice` value, because
the two drifting apart is the failure this file has already had: a fallback
kept the sentence written for the branch it fell back from, and the report
said "Start one with:" over `conduct validate`, which starts nothing.
`conduct validate` is named where a file did not load and it will therefore
print why; `conduct doctor` is named where the thing to fix is legal
Protocol v1 — an unedited template map, an unregistered harness id — and this
report is the only place it is ever said. Sending a reader to a command that
is silent about what they were just told is a dead end, so which of the two a
finding may name is measured rather than reviewed.
"""
from __future__ import annotations

import string
import sys
import textwrap
import tomllib
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from conductor import harnesses, prompts, store, templates, validate

#: The check ran and found nothing wrong.
OK = "ok"
#: The check ran and found something the user has to fix.
FINDING = "finding"
#: The check could not run. Never reported as `OK`, never silently dropped.
UNKNOWN = "unknown"

#: Where a check's detail is wrapped, and where its command sits. The two must
#: stay different: the command line is identified by its indent, so a detail
#: line that could carry the same prefix would let an authored string forge one.
_DETAIL_INDENT = "  "
_COMMAND_INDENT = "    "

#: The prefix that marks the one line of a check a person is meant to copy.
COMMAND_PREFIX = f"{_COMMAND_INDENT}next: "

#: How much of an authored value is shown before it is cut. Long enough to
#: recognise a typo in a harness id, short enough that one value cannot push a
#: report off the screen.
SHOWN_LIMIT = 80

#: Every character a token of a printed command may hold and still mean itself
#: in the shell it is pasted into. An allowlist, and not a list of
#: metacharacters to reject: a denylist is a claim about the grammar of POSIX
#: sh, PowerShell and cmd at once, and the character left out of it is the one
#: that runs. The backslash and the tilde are here for the one token that is a
#: path the reader themselves passed rather than a value out of their map.
_BARE_CHARS = frozenset(string.ascii_letters + string.digits + "-_.,:/@+=~\\")

#: What a value out of the project's map may hold. The path characters are not
#: in it: an id needs neither, and a backslash is an escape wherever a token
#: goes unquoted.
_AUTHORED_CHARS = _BARE_CHARS - set("~\\")

#: What a token that opens with this means to `argparse`, whatever it holds
#: after it: a flag. `conduct prompt --role --dir` is not a command with an
#: oddly named role, it is a usage error — so an id spelled this way earns no
#: printed command either.
_FLAG_MARK = "-"


@dataclass(frozen=True)
class Check:
    """One readiness question, its answer, and what to run about it.

    Attributes:
        name: The subject — `scaffold`, `map`, `lanes`, `roles`, `harnesses`.
        outcome: `OK`, `FINDING` or `UNKNOWN`.
        detail: One paragraph, wrapped at render time. Authored values inside
            it have already been through `_shown`.
        command: The next command as argv WITHOUT the `conduct` program name,
            e.g. `("validate", "--dir", "/srv/app")`. Empty for `OK`, and
            never empty for the other two: an unknown that names no way
            forward is as useless as a green one. Argv rather than a string so
            a caller — the CLI, or a test proving the command is real — runs
            exactly what the report printed.
    """

    name: str
    outcome: str
    detail: str
    command: tuple[str, ...] = ()


def _shown(value: str) -> str:
    """One authored string, safe to put in a line of the report.

    Args:
        value: A role id, a harness id or any other string an author wrote.

    Returns:
        The value cut to `SHOWN_LIMIT` characters and passed through `repr`,
        so a line break comes back as `\\n` rather than as a line break, and
        the result is quoted. The cut happens before `repr` and not after:
        truncating the repr itself would drop its closing quote and produce a
        value that looks like it continues.
    """
    if len(value) > SHOWN_LIMIT:
        value = value[:SHOWN_LIMIT] + "…"
    return repr(value)


def _spellable(value: str) -> bool:
    """True if `value` can be put on a command line and stay itself.

    Args:
        value: A role id or another string the project's map authored.

    Returns:
        True only when every character is one of `_AUTHORED_CHARS` and the
        value does not open like a flag. Being printable is a weaker question
        and the wrong one: a role id holding a line break cannot be typed at
        all, but `scout $(id)`, ``scout `id` `` and `scout "x"` are printable,
        legal Protocol v1, and would each turn the one command this report
        asks a person to run into a line that runs the map's text instead of
        theirs. `-x` is quieter and just as unrunnable — `argparse` reads it
        as a flag and exits 2 on the command this report printed. A finding
        about a value that is not spellable names a command a reader can run
        instead.
    """
    return (bool(value) and not value.startswith(_FLAG_MARK)
            and not set(value) - _AUTHORED_CHARS)


def _dir_args(root: str) -> tuple[str, ...]:
    """The ` --dir X` a printed command needs, or nothing for the default root."""
    return () if root == "." else ("--dir", root)


def _validate_command(root: str) -> tuple[str, ...]:
    """`conduct validate` for this root — the command that says why a file did not load.

    Named ONLY where the answer is a file `validate` refuses: a broken map, a
    broken lane. It prints nothing at all about a project whose files are fine,
    so naming it for a readiness finding — a map full of template nodes, a
    harness id nobody registered — would send a reader to a silent command and
    leave them with no way to see the finding go away. `_recheck_command` is
    what those findings name instead.
    """
    return ("validate", *_dir_args(root))


def _recheck_command(root: str) -> tuple[str, ...]:
    """`conduct doctor` for this root — how to see a readiness finding again.

    The counterpart of `_validate_command`, and the honest one wherever the
    thing to fix is legal Protocol v1: this report is the only place such a
    finding is ever stated, so this is the only command that can confirm it
    is gone.
    """
    return ("doctor", *_dir_args(root))


# --- the checks -------------------------------------------------------------


def _no_scaffold(root: str) -> Check:
    """The whole report when there is no `conductor/` to inspect.

    Two shapes reach here, because `store` refuses both, and they are told
    apart rather than described by the commoner one. A root with nothing of
    that name is a project nobody has scaffolded, and `conduct init` is the
    command that fixes it. A root where the name is already taken by a file is
    not that: `conduct init` refuses any existing `conductor` before it asks
    anything, so naming it would name a command that cannot succeed, and
    saying there is no `conductor/` would say something that is not so.
    """
    if (Path(root) / "conductor").exists():
        return Check("scaffold", FINDING,
                     f"conductor/ under {root} exists and is not a directory, "
                     "so nothing could be read from it and conduct init "
                     "refuses to touch a name that is already taken. Move it "
                     "aside, then re-check with:",
                     _recheck_command(root))
    return Check("scaffold", FINDING,
                 f"there is no conductor/ directory under {root}, so this is "
                 "not a Conduct project yet and nothing else about it can be "
                 "checked. Scaffold one:",
                 ("init", "--template", templates.DEFAULT, *_dir_args(root)))


def _unlisted_lanes(root: str) -> bool:
    """True when `conductor/lanes` is a path `store` could not list.

    `store` reads lane files out of a directory of that name and returns
    quietly when there is not one, so a `lanes` path taken by a file leaves it
    with an empty list — the same list a project nobody has ever reported into
    produces. The two are different facts, and the checks that read lanes are
    given this one so they do not report on files nobody searched for.
    """
    lanes = Path(root) / "conductor" / "lanes"
    return lanes.exists() and not lanes.is_dir()


def _template_node_sets() -> dict[str, frozenset[tuple[str, str]]]:
    """Every built-in template's nodes, as `{template name: {(id, label)}}`.

    Derived from `conductor.templates` rather than listed here, so a template
    that gains, loses or renames a node keeps being recognised without an edit
    in this file. Every template parses and validates by that module's own
    contract, which is why the ids and labels can be read without guarding.
    """
    return {name: frozenset((node["id"], node.get("label", ""))
                            for node in tomllib.loads(templates.get(name))["nodes"])
            for name, _ in templates.names()}


def _check_map(root: str, loaded: store.Loaded) -> Check:
    """Did the map load, and does it describe this project or still a template?"""
    if loaded.map_error is not None:
        return Check("map", UNKNOWN,
                     "conductor/map.toml did not load, so nothing about the "
                     "map can be judged from here. This command reports why:",
                     _validate_command(root))
    nodes = frozenset((node["id"], node.get("label", ""))
                      for node in loaded.map_data["nodes"])
    for name, template_nodes in _template_node_sets().items():
        if nodes == template_nodes:
            return Check("map", FINDING,
                         f"conductor/map.toml declares exactly the nodes of "
                         f"the built-in {name} template, unedited — so nothing "
                         f"this project reports is about your code. Replace "
                         f"them with your real components, then re-check with:",
                         _recheck_command(root))
    return Check("map", OK,
                 f"conductor/map.toml declares {len(nodes)} node(s) of its own.")


#: An advice: the sentence a detail ends on, and the command that sentence is
#: true of. The two travel together because that is the only way a fallback
#: cannot keep the sentence written for the branch it fell back FROM — which is
#: how `conduct validate` came to be printed under "Start one with:".
Advice = tuple[str, tuple[str, ...]]


def _start_advice(root: str, loaded: store.Loaded, state: dict) -> Advice:
    """How to start the first declared role — or why there is none to start."""
    for role in state["cycle"]["roles"]:
        if _spellable(role["id"]):
            return ("Start one with:",
                    ("prompt", "--role", role["id"], *_dir_args(root)))
    if loaded.map_error is not None:
        return ("The map did not load, so which role to start is unknown; "
                "this command reports why:", _validate_command(root))
    return ("No role in conductor/map.toml can be handed out: either none is "
            "declared under cycle.roles, or not one of them has an id that "
            "could be named on a command line. Fix that, then re-check with:",
            _recheck_command(root))


def _restart_advice(root: str, state: dict, stale: list[dict]) -> Advice:
    """How to hand a stale lane's role its prompt again — or why that cannot be done.

    This is the one printed command carrying TWO authored values, and both
    have to earn it. The author is a lane filename `store` read off disk, so
    `store.AUTHOR_RE` has already kept every shell metacharacter out of it —
    but that rule admits a leading dash, and `conduct prompt --author -x` is
    `argparse` exiting 2 on the line this report asked a person to paste.
    `_spellable` is what rejects that, the same predicate and for the same
    reason as the role id beside it.
    """
    declared = {role["id"] for role in state["cycle"]["roles"]}
    for lane in stale:
        if (lane["role"] in declared and _spellable(lane["role"])
                and _spellable(lane["author"])):
            return ("Hand the work back out with:",
                    ("prompt", "--role", lane["role"], "--author", lane["author"],
                     *_dir_args(root)))
    return ("No stale lane pairs a role this map declares with a role id and "
            "an author a command line could carry, so there is no prompt to "
            "hand back out. This command shows when each lane last reported:",
            ("up", *_dir_args(root)))


def _check_lanes(root: str, loaded: store.Loaded, state: dict,
                 unlisted: bool) -> Check:
    """Has anything reported at all, and did it report recently?"""
    if unlisted:
        return Check("lanes", UNKNOWN,
                     "conductor/lanes exists and is not a directory, so no "
                     "lane file was looked for and whether anyone has "
                     "reported cannot be judged from here. Move it aside, "
                     "then re-check with:",
                     _recheck_command(root))
    lanes = state["lanes"]
    if not lanes:
        sentence, command = _start_advice(root, loaded, state)
        return Check("lanes", FINDING,
                     "no lane file has been written, so no agent has ever "
                     f"reported into this project. {sentence}", command)
    live = [lane for lane in lanes if not lane["broken"]]
    if not live:
        return Check("lanes", UNKNOWN,
                     f"all {len(lanes)} lane file(s) are unreadable, so "
                     "whether anyone has reported cannot be judged from here. "
                     "This command reports why:",
                     _validate_command(root))
    stale = [lane for lane in live if lane["stale"]]
    if len(stale) == len(live):
        sentence, command = _restart_advice(root, state, stale)
        return Check("lanes", FINDING,
                     f"every one of the {len(live)} readable lane(s) is stale "
                     "— nothing has reported recently, so what the panel shows "
                     f"is a picture of the past. {sentence}", command)
    return Check("lanes", OK,
                 f"{len(live) - len(stale)} of {len(lanes)} lane(s) reported recently.")


def _unheld_advice(root: str, unheld: list[str]) -> Advice:
    """The prompt that starts an unheld role — or why none of them can be started."""
    for role_id in unheld:
        if _spellable(role_id):
            return ("Start one of them with:",
                    ("prompt", "--role", role_id, *_dir_args(root)))
    return ("Not one of those ids can be named on a command line, so no "
            "prompt can be handed out for them. Rename them in "
            "conductor/map.toml, then re-check with:", _recheck_command(root))


def _check_roles(root: str, loaded: store.Loaded, state: dict,
                 unlisted: bool) -> Check:
    """Is every role the map declares actually held by a lane?"""
    if loaded.map_error is not None:
        return Check("roles", UNKNOWN,
                     "the map did not load, so which roles this project "
                     "declares is unknown. This command reports why:",
                     _validate_command(root))
    roles = [role["id"] for role in state["cycle"]["roles"]]
    if not roles:
        return Check("roles", FINDING,
                     "conductor/map.toml declares no cycle.roles, so there is "
                     "no role for an agent to claim and no prompt to hand out. "
                     "Declare at least one, then re-check with:",
                     _recheck_command(root))
    if unlisted:
        return Check("roles", UNKNOWN,
                     "conductor/lanes exists and is not a directory, so no "
                     f"lane file was looked for and which of the {len(roles)} "
                     "declared role(s) are held cannot be judged from here. "
                     "Move it aside, then re-check with:",
                     _recheck_command(root))
    broken = [lane for lane in state["lanes"] if lane["broken"]]
    if broken:
        return Check("roles", UNKNOWN,
                     f"{len(broken)} lane file(s) are unreadable, so which of "
                     f"the {len(roles)} declared role(s) are held cannot be "
                     "judged from here. This command reports why:",
                     _validate_command(root))
    held = {lane["role"] for lane in state["lanes"]}
    unheld = [role for role in roles if role not in held]
    if unheld:
        sentence, command = _unheld_advice(root, unheld)
        return Check("roles", FINDING,
                     f"no lane claims {len(unheld)} of the {len(roles)} "
                     f"declared role(s): {', '.join(_shown(r) for r in unheld)}. "
                     f"Nothing is doing that work. {sentence}", command)
    return Check("roles", OK,
                 f"every one of the {len(roles)} declared role(s) is held by a lane.")


def _check_harnesses(root: str, loaded: store.Loaded, state: dict) -> Check:
    """Are the harness ids the map names ones the bundled registry knows?"""
    if loaded.map_error is not None:
        return Check("harnesses", UNKNOWN,
                     "the map did not load, so which harnesses this project "
                     "names is unknown. This command reports why:",
                     _validate_command(root))
    declared = [role["harness"] for role in state["cycle"]["roles"] if role["harness"]]
    unregistered = sorted({h for h in declared if harnesses.get(h) is None})
    if unregistered:
        return Check("harnesses", FINDING,
                     f"conductor/map.toml names {len(unregistered)} harness "
                     f"id(s) the bundled registry does not know: "
                     f"{', '.join(_shown(h) for h in unregistered)}. That is "
                     "legal, and Conduct never checks whether a harness is "
                     "installed — but such a harness gets the neutral badge "
                     "instead of its own. If one of them is a typo, the "
                     f"registry knows {', '.join(h.id for h in harnesses.known())}. "
                     "Fix the spelling, then re-check with:",
                     _recheck_command(root))
    if not declared:
        return Check("harnesses", OK, "no role names a harness; nothing to resolve.")
    return Check("harnesses", OK,
                 f"all {len(declared)} declared harness(es) are in the bundled registry.")


def inspect(root: Path | str) -> list[Check]:
    """Every readiness check for one project root.

    Args:
        root: The project root — the directory holding `conductor/`.

    Returns:
        The checks in reporting order. A root `store` refuses — no
        `conductor/` at all, or that name taken by something which is not a
        directory — yields the single `scaffold` finding and nothing else:
        there is genuinely nothing to inspect, and five unknowns saying so
        would be noise rather than honesty — the one finding states in its own
        words that nothing else could be checked, and no check comes back `OK`.
    """
    text_root = str(root)
    try:
        loaded = store.load(root)
    except store.StoreError:
        # Not an operational failure here, unlike in `validate`: "this project
        # was never set up" IS the answer `doctor` exists to give.
        return [_no_scaffold(text_root)]
    state = validate.merged_state(loaded)
    unlisted = _unlisted_lanes(text_root)
    return [Check("scaffold", OK, "conductor/ is present."),
            _check_map(text_root, loaded),
            _check_lanes(text_root, loaded, state, unlisted),
            _check_roles(text_root, loaded, state, unlisted),
            _check_harnesses(text_root, loaded, state)]


# --- saying it --------------------------------------------------------------


def _spelled(token: str) -> str:
    """One token of a printed command, quoted if bare would not carry it.

    A space is not the only character that costs a token its meaning — a
    Windows root under `Program Files (x86)`, or any path holding `&`, breaks
    a line that only quotes on spaces. Quoting whatever is not `_BARE_CHARS`
    is the whole rule, and it is stated as an allowlist for the reason
    `_BARE_CHARS` is: the metacharacter left out of a denylist is the one that
    runs.

    Double quotes and not single: they are the one quoting form POSIX sh,
    PowerShell and cmd all read. What they do NOT neutralise in a POSIX shell
    is `$`, a backtick, a backslash and a double quote itself — so nothing
    holding one may reach here from the project's map, and nothing does.
    Exactly two kinds of token arrive here already authored rather than
    written by this module: a role id out of `cycle.roles`, and a lane author,
    which is the stem of a filename `store` found on disk. `_spellable` is
    what covers both — a `Check.command` is built with one only after it
    returned True — and it admits none of the four. `store.AUTHOR_RE` narrows
    an author further, to letters, digits, `_` and `-`, and that is worth
    knowing when reading a `--author` token; it is not what this paragraph
    rests on, and it is not enough on its own, since it admits a leading dash.
    That there are exactly two is not a reading of this file but a walk over
    it: `tests/test_doctor_argv_doors.py` finds every tuple a printed command
    is built from and holds each element to being a literal, the root, or a
    value `_spellable` was asked about — so a third authored token added later
    is named there rather than discovered here.

    Every remaining token is this module's own literal or the root the reader
    themselves typed — and the root is the reason the rule is `_BARE_CHARS`
    and not "quote on a space": a reader's own directory may hold `&`.
    What quoting the root does is make it ONE token, which is all this
    function claims: a root holding `$` or a backtick still expands inside
    double quotes in a POSIX shell, and nothing here prevents that. That is
    accepted rather than solved, because the root is the path the reader
    passed on their own command line and not a value out of their map — the
    reader is not the attacker. No value this module reads from a project can
    reach that position.
    """
    return token if token and not set(token) - _BARE_CHARS else f'"{token}"'


def spell(argv: tuple[str, ...]) -> str:
    """One command as a person would type it: `conduct prompt --role scout`.

    Args:
        argv: A `Check.command`.

    Returns:
        The command line, `conduct` included, with every token that needs it
        quoted. NOT truncated and NOT escaped, unlike the authored values in a
        detail: a command a reader cannot paste and run is worse than a long
        one, so this stays exactly what `main` would be given.
    """
    return "conduct " + " ".join(_spelled(token) for token in argv)


def summary(checks: list[Check]) -> str:
    """The one line that says whether this project is ready.

    Args:
        checks: The checks `inspect` returned.

    Returns:
        A sentence that says "ready" only when every check came back `OK`. An
        unknown keeps that word out of the report even when nothing was found
        wrong, because a check that did not run is not a check that passed.
    """
    counts = Counter(check.outcome for check in checks)
    if counts[FINDING] or counts[UNKNOWN]:
        return (f"not ready: {counts[FINDING]} finding(s), {counts[UNKNOWN]} "
                f"unknown, {counts[OK]} ok.")
    return f"ready: {counts[OK]} check(s) ran and found nothing to fix."


def render(root: Path | str, checks: list[Check]) -> str:
    """The full report as text, ending in exactly one newline.

    Args:
        root: The project root, named in the header so a redirected report
            says which project it is about.
        checks: The checks `inspect` returned, in reporting order.

    Returns:
        The report. Three indent levels, disjoint by construction: a check
        header at column 0, its detail wrapped at two spaces, and its command
        alone at `COMMAND_PREFIX`. `textwrap` drops the whitespace it breaks
        on, so every wrapped detail line begins with exactly two spaces and a
        non-space — which is what stops an authored string inside a detail
        from producing a line that reads as a command.
    """
    lines = [f"conduct doctor — {root}", ""]
    for check in checks:
        lines.append(f"[{check.outcome}] {check.name}")
        # break_on_hyphens=False: a template name and a harness id are things
        # to be copied, and `default-orbit` split across two lines is not.
        lines.append(textwrap.fill(check.detail, width=prompts.WIDTH,
                                   initial_indent=_DETAIL_INDENT,
                                   subsequent_indent=_DETAIL_INDENT,
                                   break_on_hyphens=False))
        if check.command:
            lines.append(COMMAND_PREFIX + spell(check.command))
        lines.append("")
    lines.append(summary(checks))
    return "\n".join(lines) + "\n"


def run(args) -> int:
    """Report this project's readiness on stdout; `args.func` dispatch target.

    Args:
        args: The parsed `doctor` namespace — `dir` is the project root.

    Returns:
        0 when every check came back `OK`, and 1 otherwise. Two codes, the
        same two the rest of the CLI uses: 0 means there is nothing to report,
        and 1 means something needs the user — which is the only code that
        keeps an unknown from reading as success in a script. A root that is
        not a directory at all is the command failing to run rather than a
        finding about a project, so it goes to stderr with an empty stdout.
    """
    if not Path(args.dir).is_dir():
        print(f"cannot inspect {args.dir}: not a directory", file=sys.stderr)
        return 1
    checks = inspect(args.dir)
    sys.stdout.write(render(args.dir, checks))
    return 0 if all(check.outcome == OK for check in checks) else 1
