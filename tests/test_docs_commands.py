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
    # the README points at four documents, one of them added with this slice.
    named = set(_DOC_PATH_RE.findall(README.read_text(encoding="utf-8")))
    assert named, "the README no longer points a reader at any document"
    for path in sorted(named):
        assert (ROOT / path).exists(), path
