"""Refuse the whitespace faults that cost this repository two style commits.

Three faults, one guard: a blank line at the end of a file, a missing final
newline, and trailing whitespace on any line. Each has been committed here
before -- `c14ea2c` and `1db26ad` were style commits paying for exactly this
class -- and each is invisible to every other instrument the suite carries.
`handoff-v1-studio/structural_limits.py` counts lines, functions and nesting
and never looks at the bytes at the end of one.

**Read over the working tree, deliberately not `git diff --check`.** That
command answers a different question: whether the lines THIS branch introduced
are clean, against some base. It is silent about a file that was already wrong
at the base, which is not a hypothetical -- when this module was written the
tree carried four faults and `git diff --check` against the integration base
reported exactly one of them, because the other three predated it. A guard that
inherits its blind spots from a base commit stops being a guard the moment the
base moves.

The file list comes from `git ls-files`, so the boundary is "what this
repository ships" rather than "what happens to be on disk": a scratch file, a
virtualenv, a build directory or an editor backup is not this project's
problem, and walking the filesystem instead would either drown in them or
require a second ignore list free to disagree with `.gitignore`.

**The reading is aimed, not hard-wired.** `whitespace_faults` takes the root
and the names to read, which is what lets the witnesses below plant files
carrying each fault and prove the guard NAMES them -- a guard nobody has seen
fail is a guard nobody has seen.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

#: What this guard calls a text file. Every suffix here is one this repository
#: authors by hand and a person reads in a diff. It is deliberately a list of
#: what to READ rather than what to skip: a new binary kind added to the tree
#: is then silently out of scope, where a skip-list would have to be taught
#: about it before the guard stopped reading its bytes as lines.
TEXT_SUFFIXES = frozenset({
    ".py", ".js", ".md", ".json", ".toml", ".yml", ".yaml",
    ".css", ".html", ".ps1"})

#: The fewest text files a real checkout of this repository can hold. Not a
#: census -- a floor, and a low one. It exists because every fault this module
#: reports is an absence of a fault elsewhere: if `git ls-files` answered
#: nothing (no git, a bare directory, a renamed flag) the guard would find zero
#: faults and pass, which is the one failure mode an instrument like this has.
#: An auditor owes its own witness, so this one refuses an empty collection.
FEWEST_CREDIBLE_FILES = 200


def tracked_files(root: Path) -> tuple[str, ...]:
    """Every path git tracks under `root`, in git's own order.

    Args:
        root: The repository or worktree to ask about.

    Returns:
        Repository-relative paths, exactly as git spells them.

    Raises:
        AssertionError: git could not answer. Not a skip: a suite that
            quietly stops checking when its instrument is missing reports
            the same green as a suite that checked and found nothing.
    """
    try:
        listed = subprocess.run(
            ["git", "-C", str(root), "ls-files", "-z"],
            check=True, capture_output=True)
    except (OSError, subprocess.CalledProcessError) as error:  # no git, no repo
        raise AssertionError(
            f"this guard reads the list of tracked files from git, and git "
            f"could not answer for {root}: {error}") from error
    names = tuple(name for name in listed.stdout.decode("utf-8").split("\0")
                  if name)
    if not names:
        # The refusal that makes the floor below a judgement call rather than
        # the only thing standing between this guard and a silent pass. git
        # exiting 0 while listing nothing is the shape a wrong directory, a
        # renamed flag or an empty index takes, and it is indistinguishable
        # from a clean tree everywhere downstream.
        raise AssertionError(
            f"git listed no tracked files under {root}; a guard with nothing "
            f"to read reports the same green as a guard that found nothing "
            f"wrong, so this refuses instead")
    return names


def whitespace_faults(root: Path, names: "tuple[str, ...]") -> tuple[str, ...]:
    """Each whitespace fault in these files, named by file, line and fault.

    Args:
        root: The directory the names are relative to.
        names: Paths to consider. Anything whose suffix is not in
            `TEXT_SUFFIXES` is passed over, as is a name that is not a file
            on disk -- git lists a deleted-but-tracked path, and a missing
            file is a different complaint than a badly ended one.

    Returns:
        One sentence per fault, in the order the names arrived, spelling
        `path:line: fault` -- the shape a person can paste into an editor.
        An empty tuple means every file read was clean.
    """
    found: list[str] = []
    for name in names:
        path = root / name
        if Path(name).suffix.lower() not in TEXT_SUFFIXES or not path.is_file():
            continue
        found.extend(_faults_in(name, path.read_bytes()))
    return tuple(found)


def _faults_in(name: str, data: bytes) -> list[str]:
    """Every fault in one file's bytes, as `path:line: fault` sentences.

    An empty file carries none of the three: git is content with a tracked
    file of zero bytes, and calling that a missing newline would report a
    fault nobody can fix except by writing something.

    The line a fault is reported at is the line git would name. For a blank
    line at the end that is the count of newlines -- `}\\n\\n` is a fault on
    the second line, not a phantom third -- and for a missing final newline it
    is the last line, the one that should have ended and did not.
    """
    if not data:
        return []
    lines = data.split(b"\n")
    # Counted into a name rather than spelled inside the f-string below: a
    # backslash inside an f-string expression is a syntax error on Python
    # 3.11, which is this project's floor, and a module that will not parse
    # takes the whole suite with it on the one interpreter that matters most.
    ended_lines = data.count(b"\n")
    faults = [f"{name}:{number}: trailing whitespace"
              for number, line in enumerate(lines, start=1)
              if line != line.rstrip(b" \t")]
    if not data.endswith(b"\n"):
        faults.append(f"{name}:{len(lines)}: no newline at end of file")
    elif data.endswith(b"\n\n"):
        faults.append(f"{name}:{ended_lines}: blank line at end of file")
    return faults


# -- the guard ------------------------------------------------------------

def test_no_file_this_repository_ships_ends_badly_or_trails_whitespace():
    """The guard itself, over every tracked text file in the working tree.

    A failure here names the file, the line and which of the three faults it
    is, so the repair is the sentence and needs no second investigation.
    """
    faults = whitespace_faults(ROOT, tracked_files(ROOT))
    assert faults == (), "\n".join(("whitespace faults:", *faults))


def test_the_guard_reads_a_credible_number_of_files_rather_than_none():
    """The instrument's own calibration: silence must mean clean, not blind.

    Every other assertion in this module is an absence, and an absence is
    what a broken file list produces too. So the reading is calibrated before
    the cleanliness is believed -- and calibrated on NAMED files as well as on
    a count, because a count is checked against a number written beside it and
    a number can be lowered. These four are facts about the repository that
    lowering anything here cannot make true, and they are four suffixes on
    four roads -- a filter that lost any one of them fails here by name.

    This module is deliberately not among them. It is tracked like everything
    else once committed, but a test that demanded its own path would be red
    for exactly as long as it sat uncommitted, which is the window in which
    somebody is running it.
    """
    names = tracked_files(ROOT)
    readable = [name for name in names
                if Path(name).suffix.lower() in TEXT_SUFFIXES]
    for owed in ("README.md", "pyproject.toml",
                 "src/conductor/command/templates/dalio-v3.json",
                 "src/conductor/panel/studio-transitions.js"):
        assert owed in readable, (
            f"{owed} is tracked text this guard must read, and it is not in "
            f"the {len(readable)} files the walker collected")
    assert len(readable) >= FEWEST_CREDIBLE_FILES, (
        f"git listed {len(names)} tracked paths, of which {len(readable)} are "
        f"text this guard reads -- too few to believe, so the guard's silence "
        f"would mean nothing")


def test_a_git_that_answers_nothing_is_refused_rather_than_believed(
        monkeypatch):
    """The failure the floor above cannot be trusted to catch, closed here.

    A number written beside an assertion can be lowered until the assertion
    means nothing; this cannot, because it is about what the reading DOES
    when handed an empty answer. git exits 0 and prints nothing for a wrong
    directory or an emptied index, and every fault this module reports is an
    absence -- so an empty list would sail through as a clean tree.
    """
    class _Empty:
        stdout = b""

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _Empty())
    with pytest.raises(AssertionError, match="listed no tracked files"):
        tracked_files(ROOT)


# -- the witnesses: the guard, shown failing ------------------------------

def _plant(directory: Path) -> None:
    """One planted file per fault, each a kind this repository really ships."""
    (directory / "ends-blank.js").write_bytes(b"const a = 1;\n\n")
    (directory / "ends-bare.py").write_bytes(b"value = 1\nother = 2")
    (directory / "trails.md").write_bytes(b"# Title\n\nA line with a tail  \n")


def test_the_guard_names_the_file_the_line_and_the_fault_for_all_three(tmp_path):
    """Born red by construction: three planted faults, three named sentences.

    Aimed at a scratch directory rather than at the tree, so the witness
    proves what the reading DOES rather than restating what the tree happens
    to be. Each assertion names its own fault: a witness that only counted
    three would pass while the guard reported one fault three times.
    """
    _plant(tmp_path)
    faults = whitespace_faults(
        tmp_path, ("ends-blank.js", "ends-bare.py", "trails.md"))
    assert "ends-blank.js:2: blank line at end of file" in faults
    assert "ends-bare.py:2: no newline at end of file" in faults
    assert "trails.md:3: trailing whitespace" in faults
    assert len(faults) == 3, faults


def test_a_planted_file_that_ends_properly_is_reported_by_nothing(tmp_path):
    """The other half: the guard must be quiet about what is correct.

    Without this, every assertion above is also satisfied by a reading that
    reports every file it is handed.
    """
    (tmp_path / "clean.js").write_bytes(b"const a = 1;\n")
    (tmp_path / "clean.py").write_bytes(b"value = 1\n")
    (tmp_path / "clean.md").write_bytes(b"# Title\n\nA line.\n")
    assert whitespace_faults(
        tmp_path, ("clean.js", "clean.py", "clean.md")) == ()


def test_one_blank_line_is_the_fault_and_a_blank_line_inside_is_not(tmp_path):
    """The distinction the whole guard turns on, asserted from both sides.

    Blank lines between paragraphs and between functions are how these files
    are written; only the one after the last of them is a fault. A guard that
    could not tell them apart would have to be turned off.
    """
    (tmp_path / "inside.md").write_bytes(b"# Title\n\nA paragraph.\n")
    (tmp_path / "after.md").write_bytes(b"# Title\n\nA paragraph.\n\n")
    assert whitespace_faults(tmp_path, ("inside.md",)) == ()
    assert whitespace_faults(tmp_path, ("after.md",)) == (
        "after.md:4: blank line at end of file",)


def test_a_file_kind_this_guard_does_not_read_is_passed_over(tmp_path):
    """The suffix list is a real boundary, and it is asserted as one.

    The same bytes are a fault under a name this repository authors and are
    nothing under a name it does not, so the list above is load-bearing
    rather than decorative.
    """
    (tmp_path / "fault.js").write_bytes(b"const a = 1;\n\n")
    (tmp_path / "fault.bin").write_bytes(b"const a = 1;\n\n")
    assert whitespace_faults(tmp_path, ("fault.js",)) == (
        "fault.js:2: blank line at end of file",)
    assert whitespace_faults(tmp_path, ("fault.bin",)) == ()


def test_an_empty_file_and_a_missing_file_are_not_called_badly_ended(tmp_path):
    """Two shapes that are not this guard's business, held apart from silence.

    A zero-byte file is something git is content with, and a tracked path
    that is no longer on disk is a different complaint entirely. Reporting
    either as a missing newline would send somebody to fix the wrong thing.
    """
    (tmp_path / "empty.py").write_bytes(b"")
    assert whitespace_faults(tmp_path, ("empty.py",)) == ()
    assert whitespace_faults(tmp_path, ("gone.py",)) == ()


def test_the_file_list_comes_from_git_and_says_so_when_git_cannot_answer(
        tmp_path):
    """The refusal that keeps a missing instrument from reading as a pass.

    `tmp_path` is not a repository, so git answers with an error, and the
    guard must raise rather than return an empty list -- the failure mode
    this module's own calibration exists to close.
    """
    with pytest.raises(AssertionError, match="git could not answer"):
        tracked_files(tmp_path)
