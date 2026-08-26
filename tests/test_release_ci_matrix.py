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

from pathlib import Path

import pytest

WORKFLOW = Path(__file__).resolve().parent.parent / ".github" / "workflows" / "ci.yml"
#: Every platform this product claims to run on. Named here rather than counted
#: from the file, so a platform silently dropped from the workflow reds this
#: instead of quietly reducing what the test asks for.
PLATFORMS = ("ubuntu-latest", "windows-latest", "macos-latest")
#: The interpreters the core matrix must cover.
PYTHONS = ("3.11", "3.12")


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
