"""Guards on the shipped prose that names `conduct` commands.

Two documents make claims a user can refute by typing: `README.md`, which is
prose about the CLI from its first line to its last, and `docs/release-smoke.md`,
which is a procedure a person runs against a release candidate. Both directions
of the relation are held here, because this repository has been wrong in both:
the README's `conduct init` annotation went on describing what init did before
it grew a wizard, and `conduct report` shipped with the README never learning it
existed.

The command list is not written down in this file. It is taken from the parser
`conductor.__main__._build_parser()` builds — the object that decides what a user
may actually invoke — so renaming, adding or removing a subcommand moves this
list by itself. A guard holding a hand-copied list would be a second place to
forget, and would go on passing the day the two disagreed.

The same holds for the second code-owned list in the same section: the template
names the README's `--template` bullet spells are checked against
`templates.names()`, in both directions, and are likewise not written down here.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

from conductor import prompts, templates
from conductor.__main__ import _build_parser

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
SMOKE = ROOT / "docs" / "release-smoke.md"

#: `conduct` and the word after it, as a command line spells it. Lower-case
#: `conduct` only: the product is `Conduct` in prose and the command is not, so
#: a sentence about the tool never enters the set. A flag does not start with a
#: letter, which keeps `conduct --help` out of it — `--help` is not a subcommand
#: and no document should have to pretend otherwise.
_INVOCATION_RE = re.compile(r"(?<![\w-])conduct +([a-z][a-z0-9-]*)")

#: A repository-relative Markdown path in a code span, e.g. `demo/README.md`.
_DOC_PATH_RE = re.compile(r"`([\w./-]+\.md)`")

#: The README bullet that documents `conduct init --template`, from its own
#: marker down to the next top-level one — an indented sub-list belongs to it.
_TEMPLATE_BULLET_RE = re.compile(r"^- \*\*`--template NAME`\*\*.*?(?=^\S|\Z)",
                                 re.M | re.S)

#: One template entry inside that bullet: an indented item opening with the
#: name in a code span. The em dash is required, so a code span elsewhere in
#: the sub-list cannot pass for a name.
_TEMPLATE_NAME_RE = re.compile(r"^ +- `([a-z][a-z0-9-]*)` — ", re.M)

#: The usage line the release smoke quotes as what `conduct --help` prints, and
#: which its own step 2 calls a blocker when it does not match.
_SMOKE_USAGE_RE = re.compile(r"^usage: conduct \[-h\] \{([^{}]*)\} \.\.\.$", re.M)

#: How many steps the release smoke declares it has, and the step headings it
#: then writes. The count is spelled out in words in a sentence a person reads,
#: so the spellings a step count could plausibly take are mapped below; one this
#: map does not know fails the guard rather than passing it quietly.
_SMOKE_COUNT_RE = re.compile(r"^(\w+) steps, in order\.", re.M)
_SMOKE_STEP_RE = re.compile(r"^## (\d+)\. ", re.M)
_NUMBER_WORDS = {
    word: value for value, word in enumerate((
        "zero", "one", "two", "three", "four", "five", "six", "seven", "eight",
        "nine", "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen",
        "sixteen", "seventeen", "eighteen", "nineteen", "twenty"))
}


def readme_template_names() -> set[str]:
    """Every template name the README's `--template` bullet offers a reader."""
    bullet = _TEMPLATE_BULLET_RE.search(README.read_text(encoding="utf-8"))
    assert bullet, "the README no longer documents `conduct init --template`"
    return set(_TEMPLATE_NAME_RE.findall(bullet.group()))


def vended_template_names() -> set[str]:
    """Every template name `conduct init --template` actually accepts."""
    return {name for name, _ in templates.names()}


def subcommands() -> set[str]:
    """Every subcommand `conduct` accepts, read off the parser it builds."""
    choosers = [a for a in _build_parser()._actions
                if isinstance(a, argparse._SubParsersAction)]
    assert len(choosers) == 1, choosers
    return set(choosers[0].choices)


def smoke_usage_commands() -> set[str]:
    """The exact subcommand list the release smoke says `conduct --help` prints."""
    usage = _SMOKE_USAGE_RE.search(SMOKE.read_text(encoding="utf-8"))
    assert usage, "the release smoke no longer quotes conduct's usage line"
    return set(usage.group(1).split(","))


def named_in(path: Path) -> set[str]:
    """Every `conduct <word>` one document spells out."""
    return set(_INVOCATION_RE.findall(path.read_text(encoding="utf-8")))


def _flat(text: str) -> str:
    """One line, single-spaced — both surfaces here are wrapped by hand."""
    return " ".join(text.split())


def test_every_conduct_command_the_readme_names_is_one_the_cli_accepts():
    # Catches the command that was documented before it existed, or after it
    # stopped existing — a reader who types it gets an argparse usage error.
    named = named_in(README)
    assert named, "the README no longer shows a single conduct command"
    assert named <= subcommands(), sorted(named - subcommands())


def test_every_subcommand_a_user_can_invoke_is_named_in_the_readme():
    # The other half, and the one that fails silently without a guard: a new
    # command ships, works, and nothing tells anyone it is there.
    assert subcommands() <= named_in(README), \
        sorted(subcommands() - named_in(README))


def test_every_conduct_command_the_release_smoke_names_is_one_the_cli_accepts():
    # A release procedure that names a command this build does not have is worse
    # than one that names none: it is a step the person running it cannot do.
    named = named_in(SMOKE)
    assert named, "the release smoke no longer runs a single conduct command"
    assert named <= subcommands(), sorted(named - subcommands())


def test_the_release_smoke_exercises_every_subcommand_the_release_ships():
    # What "smoke test" means here: a command nobody ran before publishing is a
    # command published untried.
    assert subcommands() <= named_in(SMOKE), \
        sorted(subcommands() - named_in(SMOKE))


def test_the_usage_line_the_release_smoke_quotes_is_the_parsers_own_command_list():
    # The guards above are satisfied by a mention anywhere in the file, which is
    # how the quoted usage line went on listing seven commands after `preview`
    # shipped as the eighth. This one holds the EXACT list step 2 tells the
    # reader to expect "no more, no fewer" against the list argparse would print,
    # so the two cannot drift in either direction.
    quoted, real = smoke_usage_commands(), subcommands()
    assert quoted == real, {"only in the document": sorted(quoted - real),
                            "only in the CLI": sorted(real - quoted)}


def test_the_release_smoke_declares_the_number_of_steps_it_actually_writes():
    # The document opens by telling a reader how many steps to expect and closes
    # by calling any mismatch with what it does a release blocker, so its own
    # count is a claim like every other. It said ten while writing eleven.
    text = SMOKE.read_text(encoding="utf-8")
    declared = _SMOKE_COUNT_RE.search(text)
    assert declared, "the release smoke no longer says how many steps it has"
    word = declared.group(1).casefold()
    assert word in _NUMBER_WORDS, f"unmapped step-count spelling {word!r}"
    steps = [int(number) for number in _SMOKE_STEP_RE.findall(text)]
    # Numbered 1..N with no gap, so counting the headings counts the steps.
    assert steps == list(range(1, len(steps) + 1)), steps
    assert _NUMBER_WORDS[word] == len(steps)


def test_every_template_name_the_readme_lists_is_one_conduct_init_accepts():
    # The reader's failure mode: they copy a name out of this bullet, and
    # `conduct init --template <it>` exits 1 with "unknown template". The
    # subcommand list next door is held this way; this list was not, and a
    # misspelling here reads exactly like a working instruction.
    named = readme_template_names()
    assert named, "the README no longer lists a single template name"
    assert named <= vended_template_names(), sorted(named - vended_template_names())


def test_every_template_conduct_init_vends_is_listed_in_the_readme():
    # The other half: a fifth template ships, `--help` shows it, and the README
    # goes on describing four. Nothing else would say so.
    assert vended_template_names() <= readme_template_names(), \
        sorted(vended_template_names() - readme_template_names())


def test_the_readme_promises_two_imperatives_and_each_template_earns_the_right_one():
    # The README's `conduct init` paragraph promises two INSTRUCTIONS, not two
    # observations: where the nodes are placeholders the prompt tells the agent
    # to replace them with the reader's real components, and where they already
    # name components — `minimal`, which quotes the spec's §2 example — to check
    # each one against the reader's project instead. Held on the verb in both
    # documents, because the earlier version of this guard pinned only the
    # subordinate clauses ("Every/No [[nodes]] block in it is a placeholder")
    # and stayed green through a rewrite that kept both clauses and told the
    # agent to delete the real nodes.
    promised_replace = "it tells the agent to replace them with your real components"
    promised_check = "it tells the agent to check each one against your project instead"
    readme = _flat(README.read_text(encoding="utf-8"))
    assert promised_replace in readme and promised_check in readme
    replace_them = "Replace them with the real components of this project"
    check_them = "Check every one against THIS project, replace what does not describe it"
    assert "PLACEHOLDER" not in templates.get("minimal")
    said = _flat(prompts.bootstrap_prompt(prompts.DEFAULT_MAP_PATH,
                                          templates.get("minimal")))
    assert check_them in said and replace_them not in said
    for name in vended_template_names() - {"minimal"}:
        assert "PLACEHOLDER" in templates.get(name), name
        said = _flat(prompts.bootstrap_prompt(prompts.DEFAULT_MAP_PATH,
                                              templates.get(name)))
        assert replace_them in said and check_them not in said, name


def test_every_repository_document_the_readme_points_a_reader_at_exists():
    # The panel pays for its own version of this in tests/test_panel_smoke.py;
    # every repository document named by the README must survive refactors.
    named = set(_DOC_PATH_RE.findall(README.read_text(encoding="utf-8")))
    assert named, "the README no longer points a reader at any document"
    for path in sorted(named):
        assert (ROOT / path).exists(), path


# -- how many subcommands a document tells a person to expect ----------------
#
# `conduct reconcile` landed and made two documents wrong in the same instant:
# both said "nine" and there were ten. Neither was guarded. The two that ARE
# guarded above -- the README and the release smoke -- are guarded by NAME, so
# a total nobody derives went stale in silence beside them.
#
# Not every counted claim is live. A `docs/audits/*` file is a dated record of
# what was true when it was written, and so is the body of a superseded spec;
# rewriting either to agree with today would destroy the only reason to keep
# it. What is live is a sentence somebody acts on now: the acceptance script's
# step 1, and the present-tense banner that tells a reader of the old design
# what the product does TODAY.

ACCEPTANCE = ROOT / "docs" / "owner-acceptance.md"
DESIGN = ROOT / "docs" / "specs" / "2026-07-29-agent-conductor-design.md"
CLOSEOUT = ROOT / "docs" / "audits" / "2026-08-10-alpha-closeout.md"

#: (document, the sentence that states the CURRENT count). Each pattern must
#: match exactly once, so a reworded sentence reds here and is re-decided
#: rather than quietly becoming an unguarded number again.
_LIVE_COUNTS = (
    (ACCEPTANCE, re.compile(r"You must see\*\* the (\w+) subcommands")),
    (DESIGN, re.compile(r"now ships (\w+) commands")),
)
#: (document, the word it states) for claims that are CORRECT because they are
#: about a day that has passed.
_DATED_COUNTS = ((CLOSEOUT, "seven"), (DESIGN, "five"))


def test_every_document_that_counts_the_subcommands_counts_them_correctly():
    """The count is derived from the parser, never transcribed beside it."""
    real = subcommands()
    for path, pattern in _LIVE_COUNTS:
        found = pattern.findall(path.read_text(encoding="utf-8"))
        assert len(found) == 1, (
            f"{path.name}: expected exactly one counted claim, found {found}")
        assert _NUMBER_WORDS.get(found[0]) == len(real), (
            f"{path.name} says {found[0]!r}; conduct has {len(real)}: "
            f"{sorted(real)}")


def test_the_acceptance_script_names_the_authority_a_driven_run_needs():
    """Step 10 chooses `confirm`, and says what the form starts at.

    The run form defaults to the most restrictive authority, and a person who
    followed steps 10-13 as they were written met the observe sentence where
    step 13 requires a Propose control (the slice-3 review's #15). The default
    is read off the form rather than restated, so the doc reds the day the
    form's default moves.
    """
    text = ACCEPTANCE.read_text(encoding="utf-8")
    step_ten = re.search(r"## 10\. (.*?)\n## 11\.", text, re.DOTALL)
    assert step_ten is not None, "the acceptance script has no step 10"
    form = (ROOT / "src" / "conductor" / "panel" / "studio-runform.js").read_text(
        encoding="utf-8")
    default = re.search(r'\? opening\.mode : "(\w+)";', form)
    assert default is not None, "the run form names no default authority"
    assert "the authority **confirm**" in step_ten.group(1), step_ten.group(1)
    assert f"The form starts at *{default.group(1)}*" in step_ten.group(1)
    assert text.index("## 10.") < text.index("offers **Propose this step**")


def test_a_dated_record_is_not_held_to_todays_count():
    """The other half of the ruling, so nobody later "fixes" the evidence.

    Both of these state a smaller number and both are correct, because both
    describe a day that has passed. A guard that swept every counted claim into
    agreement with the parser would quietly rewrite the audit trail, so the
    exclusion is written down and measured rather than left to whoever reads
    the regex next.
    """
    for path, word in _DATED_COUNTS:
        assert re.search(rf"\b{word}\s+(?:sub)?commands\b",
                         path.read_text(encoding="utf-8")), path.name
        assert _NUMBER_WORDS[word] != len(subcommands()), (
            f"{path.name} states {word!r}, which is now today's count; this "
            "record and the live ones can no longer be told apart by number")
