"""The requested source stays inert; only an audited disposable copy executes."""
from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "scripts" / "mutate_merge.py"


def _load_harness():
    spec = importlib.util.spec_from_file_location("mutate_merge_crash", HARNESS)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


harness = _load_harness()


def _project(tmp_path: Path, merge_source: str = "VALUE = 1\n") -> tuple[Path, Path]:
    root = tmp_path / "project"
    package = root / "src" / "conductor"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    merge = package / "merge.py"
    merge.write_text(merge_source, encoding="utf-8")
    return root, merge


class _SimulatedHardKill(BaseException):
    """Stop outside the ordinary `Exception`/restore contract."""


def test_a_hard_kill_can_only_poison_the_disposable_workspace(tmp_path, monkeypatch):
    root, source = _project(tmp_path)
    original = source.read_bytes()
    touched = []
    monkeypatch.setattr(harness, "verify_import_root",
                        lambda source_root, project, merge_path: merge_path)
    monkeypatch.setattr(harness, "check_baseline", lambda *args: 2)

    def stop_while_mutated(merge_path, source_root, project):
        touched.append(merge_path)
        merge_path.write_bytes(b"mutation left by a hard-stopped worker\n")
        assert source.read_bytes() == original
        raise _SimulatedHardKill

    monkeypatch.setattr(harness, "run_mutations", stop_while_mutated)
    with pytest.raises(_SimulatedHardKill):
        harness.measure_in_scratch(root, source)
    assert len(touched) == 1 and touched[0] != source
    assert source.read_bytes() == original


def test_a_copy_that_differs_from_the_source_is_refused_before_mutation(
        tmp_path, monkeypatch):
    root, source = _project(tmp_path)
    mismatched = SimpleNamespace(read_bytes=lambda: source.read_bytes() + b"different\n")
    monkeypatch.setattr(
        harness, "run_mutations",
        lambda *args: pytest.fail("a mismatched copy reached the mutation loop"))
    with pytest.raises(harness.InvalidMeasurement, match="differs from the requested source"):
        harness.measure_in_scratch(root, mismatched)


@pytest.mark.parametrize("extra", [(), ("--verify-only",)], ids=["normal", "verify-only"])
def test_requested_merge_is_never_imported_or_self_modified(tmp_path, extra):
    root, merge = _project(
        tmp_path,
        "from pathlib import Path\n"
        "Path(__file__).write_text('# changed by import\\n', encoding='utf-8')\n")
    before = merge.read_bytes()
    result = subprocess.run(
        [sys.executable, str(HARNESS), "--root", str(root), *extra],
        capture_output=True, text=True, timeout=60,
        env={**os.environ, "PYTHONPATH": str(ROOT / "src")})
    assert result.returncode == harness.EXIT_INVALID
    assert merge.read_bytes() == before
    assert "disposable merge.py changed while its import was verified" in result.stderr


def test_verify_only_refuses_when_the_disposable_workspace_cannot_be_created(
        tmp_path, monkeypatch, capsys):
    root, _ = _project(tmp_path)
    monkeypatch.setattr(
        harness.tempfile, "mkdtemp",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError(28, "no space")))
    assert harness.main(["--root", str(root), "--verify-only"]) == harness.EXIT_INVALID
    captured = capsys.readouterr()
    assert "no space" in captured.err and "verification passed" not in captured.out


def test_temp_inside_requested_root_is_refused_before_copying(tmp_path, monkeypatch):
    root, merge = _project(tmp_path)
    inside = root / "tmp" / "conduct-mutations-fixed"

    def inside_temp(*args, **kwargs):
        inside.mkdir(parents=True)
        return str(inside)

    monkeypatch.setattr(harness.tempfile, "mkdtemp", inside_temp)
    with pytest.raises(harness.InvalidMeasurement, match="inside the requested project"):
        harness.measure_in_scratch(root, merge, verify_only=True)
    assert not inside.exists()


def test_a_directory_link_in_the_copy_surface_is_refused(tmp_path):
    root, _ = _project(tmp_path)
    target = tmp_path / "link-target"
    target.mkdir()
    link = root / "loop"
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"directory symlinks unavailable: {exc}")
    result = subprocess.run(
        [sys.executable, str(HARNESS), "--root", str(root), "--verify-only"],
        capture_output=True, text=True, timeout=60,
        env={**os.environ, "PYTHONPATH": str(ROOT / "src")})
    assert result.returncode == harness.EXIT_INVALID
    assert "link or reparse point" in result.stderr
