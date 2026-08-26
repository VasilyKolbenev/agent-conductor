"""The release workflow's SHAPE, held locally. Not its results.

This module proves what a file says, and that is the whole of what a local run
can honestly prove about CI. Whether the three platforms really pass is a
different claim entirely, and only GitHub's runners can make it -- so nothing
here should ever be quoted as "CI is green".

What it does buy is that the matrix cannot shrink quietly. A gate covering one
platform reads exactly like a gate covering three, right up until the day the
one it dropped is the one that breaks: this product owns child processes with
primitives the operating system supplies -- a Job Object on Windows, a
process/session group on POSIX -- and "POSIX" is not one platform, because
macOS is not proved by Linux.

The file is read as TEXT rather than parsed. PyYAML is not a dependency of this
project and adding one so a test can read a config file would be a runtime cost
paid for a test's convenience. The assertions are therefore change detectors on
what the workflow says, and they say so.
"""
from __future__ import annotations

import ast
import re
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
#: Every platform this product claims to run on. Named here rather than counted
#: from the file, so a platform silently dropped from the workflow reds this
#: instead of quietly reducing what the test asks for.
PLATFORMS = ("ubuntu-latest", "windows-latest", "macos-latest")
#: The interpreters the core matrix must cover.
PYTHONS = ("3.11", "3.12")
#: The ONE install form this guard understands, matched WHOLE.
#:
#: Whole, because a head match reads the extras off a command that never puts
#: the package in this job's environment. All four of these were accepted while
#: only the first installs anything here:
#:
#:     python -m pip install -e ".[dev,browser]"
#:     python -m pip install -e ".[dev,browser]" --dry-run
#:     python -m pip install -e ".[dev,browser]" --target /tmp/elsewhere
#:     python -m pip install -e ".[dev,browser]" --prefix /opt/nowhere
#:
#: So no tail is allowed at all. That is deliberately stricter than pip: a flag
#: this guard has not reasoned about must make it FAIL rather than guess, in
#: the same way a block scalar does. Widening it is a decision, not an edit.
_EDITABLE_INSTALL = re.compile(
    r'\s*python\s+-m\s+pip\s+install\s+-e\s+"\.\[(?P<extras>[^\]"]*)\]"\s*')
#: A step's command written on the `run:` line ITSELF. The excluded first
#: characters are the two block-scalar indicators and a comment marker.
_RUN_INLINE = re.compile(r"^\s*run:\s*(?P<command>[^|>#\s].*)$")
#: A step that opens a block scalar instead. Detected so its presence can be
#: REPORTED, never read.
_RUN_SCALAR = re.compile(r"^\s*run:\s*[|>]")


def _inline_run_commands(job: str) -> list[str]:
    """Every command written ON a `run:` line, and deliberately nothing else.

    A commented-out line is not a command, which is why an earlier version of
    this guard was wrong: it collected any line containing `pip install -e`, so
    this pair answered yes while installing pytest alone:

        # run: python -m pip install -e ".[dev,browser]"
        run: python -m pip install -e ".[dev]"

    **Block scalars are not read at all, and that is the point.** `|` keeps
    newlines while `>` FOLDS them into ONE command, so a reader that walked a
    body line by line accepted this as an install:

        run: >
          echo
          python -m pip install -e ".[dev,browser]"

    which really runs `echo python -m pip install ...` and installs nothing.
    Folding correctly also means getting chomping indicators, blank lines and
    the fact that `#` inside a block scalar is CONTENT right -- three more ways
    for a guard to be wrong about the thing it exists to be right about. So
    this reads the one form the install really uses, and the caller FAILS
    CLOSED when it is not there: moving the install into a block scalar must
    force this test to be re-derived, not quietly satisfied.
    """
    return [found.group("command").strip()
            for found in map(_RUN_INLINE.match, job.splitlines()) if found]
#: The name at the head of a requirement string, before any version marker.
_REQUIREMENT_NAME = re.compile(r"^\s*([A-Za-z0-9._-]+)")


def _imports_module(source: str, dotted: str) -> bool:
    """Is `dotted` imported at the TOP LEVEL of this source, as syntax?

    Read with `ast` rather than matched, and the difference is the whole reason
    this helper exists. `tests/test_browser_gate.py` imports two names from the
    same package -- `conftest`, which pulls playwright in, and `gate`, which
    does not -- so a pattern matching the PACKAGE kept answering yes after the
    load-bearing import was deleted. A guard that survives the removal of the
    thing it exists to notice proves nothing.
    """
    package, _, leaf = dotted.rpartition(".")
    for node in ast.parse(source).body:
        if isinstance(node, ast.Import):
            if any(alias.name == dotted for alias in node.names):
                return True
        elif isinstance(node, ast.ImportFrom):
            if node.module == dotted:
                return True
            if node.module == package and any(
                    alias.name == leaf for alias in node.names):
                return True
    return False


def _installed_extras(command: str) -> set[str]:
    """The extras this command really puts in the job's environment.

    The command has to BE the reviewed install, WHOLE. Containing the words is
    not enough -- an `echo "python -m pip install ..."` installs nothing -- and
    neither is starting with them, because `--dry-run`, `--target` and
    `--prefix` all leave this environment without the package.
    """
    found = _EDITABLE_INSTALL.fullmatch(command)
    return ({name.strip() for name in found.group("extras").split(",")}
            if found else set())


def _extra_providing(package: str) -> str:
    """Which optional-dependency group carries `package`, read from the file.

    `tomllib` rather than a text search: a requirement is a structured thing,
    and "the string appears somewhere in pyproject.toml" would be satisfied by a
    comment, a URL, or the package's own name in an unrelated table.
    """
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    groups = data.get("project", {}).get("optional-dependencies", {})
    for name, requirements in groups.items():
        for requirement in requirements:
            head = _REQUIREMENT_NAME.match(requirement)
            if head and head.group(1).lower() == package:
                return name
    return ""


@pytest.fixture(scope="module")
def workflow() -> str:
    assert WORKFLOW.is_file(), f"no workflow at {WORKFLOW}"
    return WORKFLOW.read_text(encoding="utf-8")


def _job(text: str, name: str) -> str:
    """One job's block, from its key to the next top-level job key.

    Split rather than parsed, and bounded on both ends: asking whether a
    platform appears "in the file" would let a browser-only platform satisfy a
    claim about the core matrix, which is exactly the confusion this file's two
    jobs invite.
    """
    start = text.index(f"\n  {name}:")
    rest = text[start + 1:]
    lines = rest.splitlines()
    body = [lines[0]]
    for line in lines[1:]:
        if line and not line[0].isspace():
            break
        if line.startswith("  ") and not line.startswith("   ") and line.rstrip().endswith(":"):
            if line.strip() != f"{name}:":
                break
        body.append(line)
    return "\n".join(body)


def test_the_core_matrix_covers_all_three_platforms_and_both_interpreters(
        workflow: str) -> None:
    """Six core jobs, and none of them assumed from another."""
    job = _job(workflow, "test")
    for platform in PLATFORMS:
        assert platform in job, (
            f"the core matrix does not name {platform}; a platform this "
            "product owns processes on cannot be inferred from another")
    for version in PYTHONS:
        assert f'"{version}"' in job, f"the core matrix does not name {version}"


def test_the_browser_gate_runs_on_all_three_platforms(workflow: str) -> None:
    """Chromium is an OS-owned process too, and it is owned differently."""
    job = _job(workflow, "browser")
    for platform in PLATFORMS:
        assert platform in job, f"the browser gate does not name {platform}"


def test_the_browser_gate_runs_in_both_orders(workflow: str) -> None:
    """The recurring Chromium flake was order-sensitive.

    A gate that only ever ran one order cannot say whether a module passed on
    its own merits or on its neighbour's leftover state, so the release gate
    runs the modules forwards and backwards.
    """
    job = _job(workflow, "browser")

    assert "--reverse" in job, (
        "the browser gate never runs the modules in the other order")
    assert job.count("browser_tests/gate.py") == 2, (
        "the browser gate is invoked once, so one of the two orders is missing")


def test_no_gate_writes_its_artifacts_into_the_worktree(workflow: str) -> None:
    """Engine logs and browser profiles stay in the runner's own temporary root.

    A browser writing beside the checkout leaves profiles and Chromium's own
    log inside the tree under test, where a later step reads them as part of
    the product -- and where two runs on one machine share them.
    """
    for line in workflow.splitlines():
        if "--artifacts" not in line:
            continue
        assert "RUNNER_TEMP" in line or "runner.temp" in line, (
            f"a gate names an artifacts directory outside the runner temp: {line}")


def test_the_core_job_installs_what_the_fast_suite_needs_to_COLLECT(
        workflow: str) -> None:
    """Born red on remote run #8: six core jobs died before any test ran.

    `testpaths` is `tests/`, and a module there imports `browser_tests.conftest`,
    which imports `playwright.sync_api` at module level. So the fast suite cannot
    be COLLECTED without a package only the `browser` extra provides -- and the
    core job installed `.[dev]`, which is pytest alone. All six jobs failed with
    `ModuleNotFoundError` on three platforms at once, and not one of them said
    anything about the product.

    **Derived, not spelled.** Each link is read from the file that carries it:
    the bridge from `tests/` into `browser_tests`, the module-level import in
    that conftest, and which extra `pyproject.toml` puts playwright in. Move the
    import or rename the extra and this reds, instead of leaving a pinned
    spelling that agrees with nothing.
    """
    bridged = sorted(
        path.name for path in (ROOT / "tests").glob("test_*.py")
        if _imports_module(path.read_text(encoding="utf-8"),
                           "browser_tests.conftest"))
    assert bridged, (
        "nothing under testpaths imports browser_tests.conftest any more, so "
        "the reason the core job needs a browser extra has moved; re-derive "
        "this guard rather than widening it")
    conftest = (ROOT / "browser_tests" / "conftest.py").read_text(encoding="utf-8")
    assert _imports_module(conftest, "playwright.sync_api"), (
        f"{bridged} import browser_tests.conftest, which no longer imports "
        "playwright at module level -- the reason for the extra has moved")

    extra = _extra_providing("playwright")
    assert extra, "no optional-dependency group provides playwright"

    job = _job(workflow, "test")
    installs = [command for command in _inline_run_commands(job)
                if _EDITABLE_INSTALL.fullmatch(command)]
    scalars = sum(1 for line in job.splitlines() if _RUN_SCALAR.match(line))
    assert installs, (
        'the core job runs no inline `python -m pip install -e ".[...]"`. This '
        "guard understands that exact command and nothing else: it will not "
        f"read the {scalars} block scalar(s) it can see -- a folded `run: >` "
        "body is ONE command, so reading it line by line accepts an `echo` as "
        "an install -- and it refuses any tail, because --dry-run, --target "
        "and --prefix all leave this environment without the package. "
        "Re-derive this test rather than widening it")
    assert any(extra in _installed_extras(command) for command in installs), (
        f"the fast suite cannot be COLLECTED without the {extra!r} extra "
        f"({bridged} reach playwright through browser_tests.conftest), and no "
        f"command the job actually RUNS asks for it: {installs}")


def test_both_jobs_prove_the_checkout_is_clean_before_they_report_green(
        workflow: str) -> None:
    """A job that leaves a file behind and still reports green says nothing.

    Both positions are held, not one. The core job builds a wheel and installs
    it; the browser job runs an engine that writes profiles, caches and its own
    log wherever it is pointed -- and "pointed at the runner temp" is exactly
    the claim this check exists to prove rather than assert. On a matrix this
    wide the failure mode is quiet: one platform out of three leaves something
    in the checkout, and nothing anywhere says so.

    The check must FAIL CLOSED, so the `exit 1` is part of what is held: a step
    that printed the dirt and returned zero would read like a gate and be a
    report.
    """
    for name in ("test", "browser"):
        job = _job(workflow, name)
        assert "git status --porcelain" in job, (
            f"the {name} job never checks whether it left the checkout dirty")
        assert "--untracked-files=all" in job, (
            f"the {name} job's clean check would miss a file it never added "
            "to the index")
        assert "exit 1" in job, (
            f"the {name} job reports dirt without failing on it")


def test_the_wheel_smoke_rides_the_whole_core_matrix(workflow: str) -> None:
    """A clean-wheel install and start, proved on every platform rather than one.

    It sits inside the core job on purpose: packaging is exactly the thing that
    differs between platforms, and a wheel smoke on Ubuntu alone says nothing
    about the two where the console script is spelled differently.
    """
    job = _job(workflow, "test")

    assert "python -m build --wheel" in job
    assert "conduct validate --dir" in job
