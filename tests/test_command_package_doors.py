"""The December Command package opens an execution door in exactly one place.

Through CMD-1..4 the package had no execution surface at all. B/RUN-1 adds the
owned-process runner -- the one reviewed door where a child process may be
started -- so this guard is now a confinement, not a blanket ban: across every
module OTHER THAN the runner (`process.py`) and its process-group helper
(`_procgroup.py`), no import reaches a subprocess, a socket, or a browser, and
no call names a system-exec, spawn, or network primitive under any import name.
A separate test proves the door has not spread beyond those two modules, and
that the runner really does hold it. The runner's own safety -- structured
argv, contained cwd, sanitized environment, bounded output, timeout, and
ownership -- is proven behaviourally by `tests/test_command_process_*.py`, not
by an AST name check, which is why the door is exempted here rather than
pretended away. It fails closed on the dangerous names: a new door in any other
module is a failure until it is removed.
"""
from __future__ import annotations

import ast
from pathlib import Path

from conductor.command import contracts as command_contracts


# Whole modules that can leave the machine or spawn work off it. Importing any of
# them anywhere in the package is a failure; the store's os/tempfile/shutil doors
# are durability, not probing, and are deliberately absent from this set.
FORBIDDEN_MODULES = frozenset({
    "subprocess", "socket", "ssl", "urllib", "urllib.request", "http",
    "http.client", "ftplib", "telnetlib", "smtplib", "poplib", "imaplib",
    "requests", "httpx", "aiohttp", "ctypes", "cffi", "webbrowser",
    "multiprocessing", "asyncio", "socketserver", "xmlrpc", "xmlrpc.client",
    "selenium", "pty", "winreg", "psutil",
})
# Call targets that execute a program, spawn a process, or open a connection,
# whatever module they were reached through.
FORBIDDEN_CALLS = frozenset({
    "system", "popen", "Popen", "startfile", "execl", "execle", "execlp",
    "execlpe", "execv", "execve", "execvp", "execvpe", "spawnl", "spawnle",
    "spawnlp", "spawnv", "spawnve", "spawnvp", "urlopen", "connect", "create_connection",
    "check_output", "check_call", "getoutput", "getstatusoutput",
})
FORBIDDEN_NAMES = frozenset({"__import__", "eval", "exec", "compile"})
# The one reviewed execution door: the owned-process runner and the helper that
# terminates only the group it started. Every other module stays fenced.
EXECUTION_DOOR = frozenset({"process.py", "_procgroup.py"})


def _package_sources():
    package = Path(command_contracts.__file__).resolve().parent
    sources = sorted(package.rglob("*.py"))
    assert sources, "the command package has no modules to inspect"
    return package, sources


def _imported_modules(tree: ast.AST) -> set[str]:
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            imported.add(node.module or "")
    return imported


def _called_names(tree: ast.AST) -> set[str]:
    attribute_calls = {
        node.func.attr for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    name_calls = {
        node.func.id for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    return (attribute_calls & FORBIDDEN_CALLS) | (name_calls & (FORBIDDEN_CALLS | FORBIDDEN_NAMES))


def test_no_command_module_outside_the_runner_imports_a_network_or_subprocess_module():
    _, sources = _package_sources()
    offenders: dict[str, list[str]] = {}
    for path in sources:
        if path.name in EXECUTION_DOOR:
            continue
        hit = sorted(_imported_modules(ast.parse(path.read_text(encoding="utf-8")))
                     & FORBIDDEN_MODULES)
        if hit:
            offenders[path.name] = hit
    assert offenders == {}, f"forbidden imports reached: {offenders}"


def test_no_command_module_outside_the_runner_calls_an_exec_spawn_or_network_primitive():
    _, sources = _package_sources()
    offenders: dict[str, list[str]] = {}
    for path in sources:
        if path.name in EXECUTION_DOOR:
            continue
        hit = sorted(_called_names(ast.parse(path.read_text(encoding="utf-8"))))
        if hit:
            offenders[path.name] = hit
    assert offenders == {}, f"forbidden calls reached: {offenders}"


def test_the_execution_door_is_confined_to_the_owned_process_runner():
    """The door exists in the runner modules and nowhere else -- present, not spread.

    A module holds an execution door if it imports a forbidden module or calls a
    forbidden exec/spawn/network primitive. The set of such modules must equal
    the sanctioned runner set exactly: an escape into any other module reds the
    subset check, and silently removing the runner's door reds the presence check.
    """
    _, sources = _package_sources()
    door_holders: set[str] = set()
    for path in sources:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        if (_imported_modules(tree) & FORBIDDEN_MODULES) or _called_names(tree):
            door_holders.add(path.name)
    escaped = sorted(door_holders - EXECUTION_DOOR)
    assert escaped == [], f"an execution door appeared outside the runner: {escaped}"
    assert "process.py" in door_holders, "the runner's execution door has vanished"
