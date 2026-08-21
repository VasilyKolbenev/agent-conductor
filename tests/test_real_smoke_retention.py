"""An opt-in smoke may not reach around the retention path it claims to prove.

Two tests here, and they answer different halves of one defect.

The defect: `tests/test_command_kimi_real_smoke.py` asserted that a real install
leaves no state standing under this build's home root, and reached the child by
calling `_spawn(adapter._mint_home())` -- which skips `_attempt`'s
`finally: discard`, the only thing that takes a home back. Pointed at a real
shell-free executable the test was deterministically RED:

    REAL_INSTALL_LEFT_STATE_STANDING=['harness-home-1']

So the module that existed to prove retention was the module proving it was
broken, and nobody saw it because the whole file skips without an install. A
test that only runs where nobody looks is a test that says nothing.

The halves:

- **The class.** An AST guard reads every real-smoke module and refuses the two
  names that reach around the retention path. It NEVER skips, so the next smoke
  written the wrong way fails on an ordinary run rather than the day somebody
  finally sets the pin.
- **The consequence.** A behavioural witness drives the production transport
  through a runner that spawns nothing, and holds both directions: `_attempt`
  takes its home back, and the bypass really does leave one standing. The second
  assertion is what stops the first from guarding an imaginary hazard, and it is
  why the guard names those two symbols rather than a style.

Neither test needs an install, an executable, or a platform primitive, so
neither can skip its way to green.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from conductor.command.adapters.dsh_harness import DshHarnessAdapter, DshPin
from conductor.command.adapters.process import ProcessOutcome, ProcessRunner

#: The names that reach a child, or a home, around `_attempt`. `_attempt` is the
#: ONE road that mints a home and takes it back on every exit including a raise.
BYPASSES = frozenset({"_spawn", "_mint_home"})
#: Every module that drives a real vendor install. They are the modules where a
#: mistake hides, because they skip when no install is pinned.
SMOKE_GLOB = "test_command_*_real_smoke.py"


def _smoke_modules() -> list[Path]:
    modules = sorted(Path(__file__).resolve().parent.glob(SMOKE_GLOB))
    assert modules, f"no module matches {SMOKE_GLOB}; this guard covers nothing"
    return modules


def _attribute_calls(tree: ast.AST) -> set[str]:
    """Every `x.name(...)` called anywhere in the module, by attribute name."""
    return {
        node.func.attr for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)}


def test_no_real_smoke_module_reaches_around_the_retention_path():
    """The guard that never skips: a smoke must go through `_attempt`.

    Read as an assertion about SYMBOLS, not about style: `_spawn` starts a child
    with a home the caller minted and nobody takes back, and `_mint_home` is how
    a caller gets one. A smoke that names either is a smoke that can leave the
    state its own docstring promises this build never keeps.
    """
    offenders: dict[str, list[str]] = {}
    for path in _smoke_modules():
        hit = sorted(_attribute_calls(ast.parse(path.read_text(encoding="utf-8")))
                     & BYPASSES)
        if hit:
            offenders[path.name] = hit
    assert offenders == {}, (
        f"real-smoke modules reach around the retention path: {offenders}")


def test_every_real_smoke_module_really_drives_a_transport():
    """The guard above must not pass by covering modules that drive nothing.

    A smoke that never reaches the transport at all would satisfy the symbol ban
    trivially. Each module must call `_attempt`, which is the road it is being
    held to.
    """
    for path in _smoke_modules():
        calls = _attribute_calls(ast.parse(path.read_text(encoding="utf-8")))
        assert "_attempt" in calls, (
            f"{path.name} drives no transport, so the retention guard proves "
            "nothing about it")


class _SpawnlessRunner(ProcessRunner):
    """A runner that starts no child, so the witness below needs no install.

    The transport requires a real `ProcessRunner` and this IS one -- it only
    answers `run` from a canned outcome instead of a process. Retention is a fact
    about the home the transport minted and about who takes it back, and no child
    is needed to observe it.
    """

    def run(self, spec) -> ProcessOutcome:  # type: ignore[override]
        return ProcessOutcome(
            status="completed", exit_code=0, output=b"0.1.0-rc.7\n",
            output_truncated=False, output_limit=spec.output_limit, pid=0,
            token="witness")


def _transport(tmp_path: Path):
    root = tmp_path / "root"
    root.mkdir()
    pin = DshPin(
        node_executable=str(tmp_path / "node.exe"),
        entrypoint=str(tmp_path / "bin.js"))
    adapter = DshHarnessAdapter(
        pin, _SpawnlessRunner(root), root=root, clock=lambda: "now",
        ids=lambda prefix: f"{prefix}-1")
    adapter._workspace.work_root()
    return adapter, root


def _standing(root: Path) -> list[str]:
    homes = root / ".dsh-home"
    return sorted(path.name for path in homes.iterdir()) if homes.is_dir() else []


def test_the_production_path_takes_its_attempt_home_back(tmp_path):
    """`_attempt` mints and discards, and this is that relation with no install."""
    adapter, root = _transport(tmp_path)

    outcome = adapter._attempt(("--version",), "work", timeout=30)

    assert outcome.status == "completed"
    assert _standing(root) == [], "THE_PRODUCTION_PATH_LEFT_A_HOME_STANDING=True"


def test_the_bypass_really_does_leave_a_home_standing(tmp_path):
    """The hazard is real, which is what makes the guard above worth having.

    Without this, the symbol ban could be guarding nothing: a reader could not
    tell whether `_spawn` with a hand-minted home is dangerous or merely
    unfashionable. It is dangerous, and this is the exact state the real smoke
    left behind before the correction.
    """
    adapter, root = _transport(tmp_path)

    outcome = adapter._spawn(
        ("--version",), adapter._mint_home(), "work", timeout=30)

    assert outcome.status == "completed"
    assert _standing(root) == ["harness-home-1"], (
        "the bypass no longer leaks a home, so the guard above now bans a "
        "symbol that is safe -- re-derive what the retention path is")
