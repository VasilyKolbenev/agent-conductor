"""The Seatbelt box, its fixtures and its applied-witness, checked on every POSIX host.

The darwin tests run only on macOS. What the box hands them (a layout of their own, an
absent name that really is absent, a profile that names it) and how a launch is judged
applied (a write to a canary that the profile must refuse, never an echo) do not depend on
Seatbelt, so they are checked here with fake wrappers: a red run of this module is a fault
in the test support, never a finding about the mechanism. The fake that ignores the profile
is the negative control; the fake that makes the canary directory unwritable is the positive
one, and without it a witness that always said "no" would pass the first.
"""
from __future__ import annotations

import os
import re
import subprocess

import pytest

from tests import os_boundary_darwin as sb
from tests.os_boundary_seatbelt_box import (  # noqa: F401
    absent_box, implement_box, protected_box, unprotected_box)
# The table sits beside the darwin tests that judge it; here it is only read, never run.
from tests.test_os_boundary_darwin import PROTECTED_OPS

pytestmark = pytest.mark.skipif(
    os.name == "nt", reason="needs POSIX paths: a Seatbelt profile names POSIX paths")
not_root = pytest.mark.skipif(
    os.name != "nt" and os.geteuid() == 0,
    reason="needs a non-root user: root writes into an unwritable directory")

_ABSENT_NAMES = ("hooks", "hooks-paths")
_IGNORES_THE_PROFILE = '#!/bin/sh\nshift 2\nexec "$@"\n'


def _install(monkeypatch, path, text: str) -> None:
    """Make ``path`` the sandbox wrapper: an executable script with the given text."""
    path.write_bytes(text.encode("utf-8"))
    path.chmod(0o755)
    monkeypatch.setattr(sb, "SANDBOX_EXEC", str(path))


def _refuses_the_canary(directory) -> str:
    """A wrapper that makes the canary directory unwritable, then execs without a profile."""
    return f'#!/bin/sh\nchmod a-w "{directory}"\nshift 2\nexec "$@"\n'


def test_two_boxes_asked_for_by_one_test_do_not_share_a_vendor_home(
        absent_box, unprotected_box):
    assert absent_box.layout.base != unprotected_box.layout.base
    assert absent_box.layout.vendor_home != unprotected_box.layout.vendor_home


def test_the_box_that_protects_absent_names_starts_without_them_beside_a_box_that_has_them(
        absent_box, unprotected_box):
    for name in _ABSENT_NAMES:
        assert not (absent_box.layout.vendor_home / name).exists(), name
        assert (unprotected_box.layout.vendor_home / name).exists(), name


def test_the_control_box_leaves_the_directory_that_holds_the_entries_removable_and_the_other_not(
        protected_box, unprotected_box):
    """Only the protected box may stop a rename of the holder: the control must not."""
    holder_rule = 'file-write-unlink (literal "{}")'
    assert holder_rule.format(protected_box.layout.vendor_home.resolve()) in protected_box.profile
    assert holder_rule.format(
        unprotected_box.layout.vendor_home.resolve()) not in unprotected_box.profile
    assert holder_rule.format(unprotected_box.layout.tmp.resolve()) in unprotected_box.profile


@pytest.mark.parametrize("operation", PROTECTED_OPS, ids=lambda op: op.name)
def test_every_path_a_protected_operation_names_is_inside_a_root_the_control_profile_may_write(
        unprotected_box, operation):
    """An operation that lands outside every allowed root can never change anything there, so
    its run without the protection would show nothing and could not tell the protection apart."""
    allow = next(line for line in unprotected_box.profile.splitlines()
                 if line.startswith("(allow file-write*"))
    roots = re.findall(r'\(subpath "([^"]+)"\)', allow)
    tokens = unprotected_box.tokens("vendor")
    for step in operation.posix:
        body = step.body
        for key, value in tokens.items():
            body = body.replace(f"@{key}@", os.path.realpath(value))
        for path in re.findall(r'"(/[^"]*)"', body):
            assert any(path == root or path.startswith(root + "/") for root in roots), (
                f"{operation.name}: {path} is outside {roots}")


def test_the_profile_of_the_absent_box_denies_both_names_after_the_allow_that_covers_them(
        absent_box):
    lines = absent_box.profile.splitlines()
    allow = next(i for i, line in enumerate(lines) if line.startswith("(allow file-write*"))
    named = [os.path.realpath(absent_box.layout.vendor_home / name) for name in _ABSENT_NAMES]
    denies = [i for i, line in enumerate(lines)
              if line.startswith("(deny file-write* (subpath")
              and all(f'(subpath "{path}")' in line for path in named)]
    assert denies, "no rule denies both absent names"
    assert denies[0] > allow, "a later rule wins, so the deny must come after the allow"


def _shell(script: str) -> subprocess.CompletedProcess:
    return subprocess.run(["/bin/sh", "-c", script], capture_output=True, text=True,
                          timeout=60, check=False)


def test_the_witness_script_reports_unconfined_and_skips_the_body_when_its_canary_write_works(
        tmp_path):
    canary, ran = tmp_path / "witness", tmp_path / "ran"
    done = _shell(sb.witnessed_script(canary, f'touch "{ran}"'))
    assert done.stdout.splitlines()[0] == sb.UNCONFINED, done
    assert done.returncode != 0 and canary.exists() and not ran.exists()


@not_root
def test_the_witness_script_reports_applied_and_runs_the_body_when_the_canary_dir_is_unwritable(
        tmp_path):
    directory = tmp_path / "canary"
    directory.mkdir()
    directory.chmod(0o555)
    try:
        ran = tmp_path / "ran"
        done = _shell(sb.witnessed_script(directory / "witness", f'touch "{ran}"'))
    finally:
        directory.chmod(0o755)
    assert done.stdout.splitlines()[0] == sb.APPLIED, done
    assert done.returncode == 0 and ran.exists() and not (directory / "witness").exists()


def test_a_wrapper_that_ignores_the_profile_is_judged_not_applied_and_the_body_never_runs(
        implement_box, monkeypatch, tmp_path):
    _install(monkeypatch, tmp_path / "sandbox-exec", _IGNORES_THE_PROFILE)
    outcome = implement_box.run_body('printf x > "@TMPD@/ran"')
    assert not outcome.applied, outcome
    assert not (implement_box.layout.tmp / "ran").exists(), "the body ran without a policy"
    assert implement_box.canary.exists(), "the parent has no evidence the write got through"


@not_root
def test_a_launch_whose_canary_directory_is_unwritable_is_judged_applied_and_the_body_runs(
        implement_box, monkeypatch, tmp_path):
    directory = implement_box.canary.parent
    _install(monkeypatch, tmp_path / "sandbox-exec", _refuses_the_canary(directory))
    try:
        outcome = implement_box.run_body('printf x > "@TMPD@/ran"')
    finally:
        directory.chmod(0o755)
    assert outcome.applied and outcome.exit_code == 0, outcome
    assert (implement_box.layout.tmp / "ran").read_bytes() == b"x"
    assert not implement_box.canary.exists()


@pytest.mark.parametrize("output", ["", "\n", f"{sb.UNCONFINED}\n", "sandbox-exec: bad profile\n",
                                    f"note\n{sb.APPLIED}\n"],
                         ids=["empty", "blank", "unconfined", "wrapper-error", "not-first"])
def test_require_applied_refuses_output_whose_first_line_is_not_the_witness(output, tmp_path):
    with pytest.raises(sb.PolicyNotApplied):
        sb.require_applied(output, tmp_path / "witness")


def test_require_applied_refuses_an_applied_first_line_when_the_canary_exists(tmp_path):
    canary = tmp_path / "witness"
    canary.write_bytes(b"x")
    with pytest.raises(sb.PolicyNotApplied):
        sb.require_applied(f"{sb.APPLIED}\nbody output\n", canary)


def test_require_applied_accepts_the_witness_first_when_the_canary_is_absent(tmp_path):
    sb.require_applied(f"{sb.APPLIED}\nbody output\n", tmp_path / "witness")
