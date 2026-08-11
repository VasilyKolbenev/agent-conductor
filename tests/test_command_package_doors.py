"""No module of the December Command package opens a network or execution door.

The adapter SDK is fenced by its own strict import allowlist. This guard is the
package-wide complement: across every module -- contracts, the run store, the
service, and the adapters -- no import reaches a subprocess, a socket, or a
browser, and no call names a system-exec, spawn, or network primitive under any
import name. It fails closed on the dangerous names, so a new door is a failure
until it is removed, not until someone remembers to list it.
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


def _package_sources():
    package = Path(command_contracts.__file__).resolve().parent
    sources = sorted(package.rglob("*.py"))
    assert sources, "the command package has no modules to inspect"
    return package, sources


def test_no_command_module_imports_a_network_or_subprocess_module():
    _, sources = _package_sources()
    offenders: dict[str, list[str]] = {}
    for path in sources:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                imported.add(node.module or "")
        hit = sorted(imported & FORBIDDEN_MODULES)
        if hit:
            offenders[path.name] = hit
    assert offenders == {}, f"forbidden imports reached: {offenders}"


def test_no_command_module_calls_an_exec_spawn_or_network_primitive():
    _, sources = _package_sources()
    offenders: dict[str, list[str]] = {}
    for path in sources:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        attribute_calls = {
            node.func.attr for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        }
        name_calls = {
            node.func.id for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        hit = sorted((attribute_calls & FORBIDDEN_CALLS)
                     | (name_calls & (FORBIDDEN_CALLS | FORBIDDEN_NAMES)))
        if hit:
            offenders[path.name] = hit
    assert offenders == {}, f"forbidden calls reached: {offenders}"
