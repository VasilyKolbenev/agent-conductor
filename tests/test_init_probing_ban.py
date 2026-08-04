"""The machine-probing ban, stated over the init path's import graph.

Split out of test_init.py when that file passed the project's 800-line cap.
The seam is clean in both directions: nothing here is used by test_init.py and
nothing here reaches back into it, so no helper is shared, duplicated, or
promoted into a conftest. The measurement cache below stays module-local for
the same reason — it belongs to this subject, not to the suite.

This guard spawns a child interpreter because the question it asks — which
modules does a real `conduct init` import? — cannot be answered in this
process: the suite has already imported every module in the package, so
`sys.modules` here would answer "all of them". It cannot hang: the child's
stdin is the null device, `conduct init` never reads stdin off a terminal
anyway, and the call carries a timeout. It is the only subprocess in the init
tests, and a second one would need the same justification.
"""
import ast
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest
import conductor

PROBING_MODULES = {"shutil", "subprocess", "os", "platform", "socket",
                   "importlib", "sysconfig", "site", "winreg"}

#: QUALIFIED calls, never bare attribute names. The bare form banned `.run`
#: outright, which cost the entry point its natural spelling (`init.run` read
#: as `subprocess.run`) — and a rule that renames honest code is a rule people
#: learn to route around. Matching the pair costs nothing: the module half is
#: already unimportable, so a probe has to spell out where it came from.
PROBING_CALLS = {
    "shutil.which", "shutil.disk_usage",
    "subprocess.run", "subprocess.Popen", "subprocess.call",
    "subprocess.check_call", "subprocess.check_output", "subprocess.getoutput",
    "os.system", "os.popen", "os.getenv", "os.environ", "os.listdir",
    "os.scandir", "os.walk", "os.uname", "os.get_exec_path", "os.path.exists",
    "platform.system", "platform.machine", "platform.node",
    "socket.gethostname", "socket.gethostbyname",
    "importlib.util.find_spec", "importlib.metadata.version",
    "sysconfig.get_paths", "site.getsitepackages",
    "winreg.OpenKey", "winreg.QueryValueEx",
}

#: The modules the ban exists FOR. If a measurement is missing one of these
#: the child died before importing it, and a ban that parsed the remainder
#: would pass while covering nothing that matters — so this is checked at the
#: measurement, where a crash can still be told apart from a clean run.
FLOOR = {"conductor", "conductor.__main__", "conductor.init",
         "conductor.harnesses", "conductor.templates", "conductor.validate"}

SRC = Path(conductor.__file__).parent


def _dotted(node):
    """An attribute chain as source text (`os.environ`), or None if computed."""
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if not isinstance(node, ast.Name):
        return None
    parts.append(node.id)
    return ".".join(reversed(parts))


#: Run a real `conduct init` in a fresh interpreter and report which
#: `conductor.*` modules ended up imported, and the file each was read from.
#: Measuring beats reasoning here: a static walk has to decide what to follow,
#: and every answer is either an over-approximation (`__main__` imports every
#: command's code) or a claim about the call graph that nobody checks again.
#: Reporting `__file__` rather than rebuilding a path from the dotted name
#: keeps the parent parsing the exact source the child executed, packages and
#: submodules included.
_PROBE = """
import json, sys, tempfile
try:
    from conductor.__main__ import main
    with tempfile.TemporaryDirectory() as root:
        outcome = "exit %d" % main(["init", "--dir", root])
except BaseException as failure:      # a probe that crashes init is still a probe
    outcome = "%s: %s" % (type(failure).__name__, failure)
loaded = {n: getattr(m, "__file__", None) for n, m in sorted(sys.modules.items())
          if n == "conductor" or n.startswith("conductor.")}
with open(sys.argv[1], "w", encoding="utf-8") as report:
    json.dump({"outcome": outcome, "modules": loaded}, report)
"""

#: One measurement, reused: both tests below ask about the same child run and
#: nothing between them can change its answer, so this keeps the file at one
#: spawned interpreter instead of two.
_measured: dict[str, dict[str, Path]] = {}


def _measured_modules(data: dict) -> dict[str, Path]:
    """The measured modules the ban can parse, checked against `FLOOR`.

    Args:
        data: The child's report — `{"outcome": str, "modules": {name: file}}`.

    Returns:
        `{dotted name: source Path}` for every module reported with a source
        file. The filter runs BEFORE the floor check, and that order is the
        point: a module measured with `__file__` of None is one
        `_probing_findings` can never parse, so counting it toward the floor
        would let the measurement claim a module the ban then skipped.

    Raises:
        AssertionError: When a `FLOOR` module was not measured, or was
            measured without a source file the ban could read.
    """
    modules = {name: Path(file) for name, file in data["modules"].items() if file}
    assert FLOOR <= set(modules), (
        f"the init path was not measured to the floor ({data['outcome']}); "
        f"missing {sorted(FLOOR - set(modules))}")
    return modules


def _init_path_modules():
    """The `conductor.*` modules a real `conduct init` run actually imports.

    Returns:
        `{dotted name: source Path}`, measured in a child interpreter. Not
        measurable in this process: the suite has already imported the whole
        package, so `sys.modules` here would answer "all of them".

    The measurement is the point. `conductor.demo` and `conductor.server`
    stay off this list only because `conductor.__main__` defers importing
    them into the two commands that need them — hoist either back to module
    scope and it appears here, gets parsed, and fails the ban on its own
    honest `shutil`/`importlib` import. That is a boundary the test proves
    rather than asserts.

    Whether the probed `init` SUCCEEDS is deliberately not asserted: a probe
    planted in a module init reaches may well crash the run, and a crash does
    not change which modules got imported. What IS asserted is `FLOOR`, and
    the two failures read differently on purpose — a missing floor names the
    child's outcome and means it crashed before measuring, while a probe the
    ban caught names the module and the call.
    """
    if not _measured:
        with tempfile.TemporaryDirectory() as work:
            script, report = Path(work) / "probe.py", Path(work) / "report.json"
            script.write_text(_PROBE, encoding="utf-8")
            # cwd is containment, not mechanism: the measurement is identical
            # without it, since `sys.path[0]` is the script's own directory
            # and not the working one. It only keeps a child that resolves a
            # relative path resolving it inside this throwaway rather than
            # inside the repository it is measuring. PYTHONPATH is SET, not
            # prepended — `{**os.environ, ...}` drops whatever the shell
            # exported, so an inherited entry cannot be searched ahead of
            # `SRC.parent`, the source root this test puts there.
            done = subprocess.run(
                [sys.executable, str(script), str(report)],
                cwd=work, stdin=subprocess.DEVNULL, capture_output=True,
                timeout=120, env={**os.environ, "PYTHONPATH": str(SRC.parent)})
            assert report.is_file(), (
                "the probe wrote no report, so nothing was measured — the "
                "child died before it could write one. Its stderr:\n"
                + done.stderr.decode("utf-8", "replace"))
            data = json.loads(report.read_text(encoding="utf-8"))
        _measured["modules"] = _measured_modules(data)
    return _measured["modules"]


def _probing_findings(module, path):
    """Every banned import and qualified call in one module's source.

    Args:
        module: The dotted name, used to write the finding.
        path: The file the child interpreter actually imported it from.

    Returns:
        One string per violation. Collected rather than asserted node by node
        so a failure names ALL of them: a sabotage check that reads back only
        the first violation cannot tell its own probe from the honest import
        that happens to be parsed earlier.
    """
    findings = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        imported = []
        if isinstance(node, ast.Import):
            imported = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            imported = [node.module or ""]
        findings += [f"{module} may not import {name}" for name in imported
                     if name.split(".")[0] in PROBING_MODULES]
        if isinstance(node, ast.Attribute) and _dotted(node) in PROBING_CALLS:
            findings.append(f"{module} may not call {_dotted(node)}")
    return findings


def test_init_never_probes_the_machine_for_installed_harnesses():
    # Detecting installed harnesses is deferred, and probing a user's box is a
    # new capability class that needs its own ADR (privacy, sandboxing). The
    # ban is a REPOSITORY GUARD, not a security sandbox: it stops a probe from
    # arriving by accident or without discussion, and it would not stop a
    # determined one — `getattr` and a string defeat it in a line. What it
    # covers is every conductor module a real `conduct init` imports, and both
    # halves of how a probe is spelled: the import, and the qualified call.
    # Parsed, so a comment naming subprocess is fine and an import is not.
    findings = []
    for module, path in _init_path_modules().items():
        findings += _probing_findings(module, path)
    assert findings == []


def test_a_module_measured_without_a_source_file_fails_the_floor():
    # The ban parses source, and a module reported with `__file__` of None has
    # none to parse — so the filter has to run before the check, not after it.
    full = {"outcome": "exit 0", "modules": {name: f"{name}.py" for name in FLOOR}}
    assert set(_measured_modules(full)) == FLOOR
    blind = {"outcome": "exit 0",
             "modules": {**full["modules"], "conductor.init": None}}
    with pytest.raises(AssertionError, match="conductor.init"):
        _measured_modules(blind)


def test_the_ban_reaches_every_conductor_module_init_actually_runs():
    # The old ban parsed a hand-kept list of modules and followed nothing, so
    # a probe in a module init merely called went unseen. These assertions are
    # what makes the widening real rather than nominal. `FLOOR` is not restated
    # here: the measurement itself refuses to return without it.
    modules = set(_init_path_modules())
    # Nobody had to remember these; init reaches them and the measurement saw it.
    assert {"conductor.merge", "conductor.store", "conductor.schema",
            "conductor.prompts"} <= modules
    # And the boundary, measured rather than argued: `conduct init` does not
    # import the two modules that legitimately touch the machine. They are
    # deferred inside `conduct demo` and `conduct up`; undo that and this fails.
    assert "conductor.demo" not in modules and "conductor.server" not in modules
