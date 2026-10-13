"""The environment names an operator may not reference; no process, no filesystem.

Split out of ``process.py`` unchanged. ``process`` re-exports both names, so every
existing import (``process.INJECTING_ENV``, ``process.injecting_env_reason``) still holds.
"""
from __future__ import annotations

import os
from collections.abc import Mapping
from types import MappingProxyType

#: Environment names an operator may NOT put in `env_allow`, grouped by the
#: runtime that reads them, each group carrying the reason it is refused.
#:
#: The line is a relation, not a feeling about a name. `PATH` and its kin choose
#: a SEPARATE program the child may decide to start, and the reviewed entrypoint
#: still runs first and still decides. Every name below instead chooses code
#: loaded INTO the reviewed process before its own first instruction, which
#: hands back the authority an absolute pin was taken to hold. The roster is
#: closed against the runtimes a vendor CLI here can BE, not against today's
#: five providers, so adding a runtime obliges adding its row. The ruling, its
#: evidence and its stated limits: `docs/adr/0007-env-allow-trust-boundary.md`.
_INJECTING_ENV_GROUPS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("LD_PRELOAD", "LD_AUDIT", "LD_LIBRARY_PATH"),
     "the ELF dynamic loader maps and runs what it names inside the process "
     "before the program's own first instruction"),
    (("DYLD_INSERT_LIBRARIES", "DYLD_LIBRARY_PATH", "DYLD_FRAMEWORK_PATH",
      "DYLD_FALLBACK_LIBRARY_PATH", "DYLD_FALLBACK_FRAMEWORK_PATH"),
     "macOS dyld inserts and redirects libraries into the process before "
     "main() runs"),
    (("PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP", "PYTHONEXECUTABLE"),
     "CPython reads it before the pinned entrypoint script, so the first "
     "import that script performs can be an attacker's module"),
    (("NODE_OPTIONS", "NODE_PATH", "NODE_REPL_EXTERNAL_MODULE"),
     "node executes --require and --import modules, and resolves requires "
     "through NODE_PATH, ahead of the pinned entrypoint"),
    (("JAVA_TOOL_OPTIONS", "_JAVA_OPTIONS", "JDK_JAVA_OPTIONS", "CLASSPATH"),
     "the JVM reads it before main: the option variables carry -javaagent, "
     "whose premain runs first, and CLASSPATH decides which class a name is"),
    (("DOTNET_STARTUP_HOOKS", "CORECLR_ENABLE_PROFILING", "CORECLR_PROFILER",
      "CORECLR_PROFILER_PATH", "COR_ENABLE_PROFILING", "COR_PROFILER",
      "COR_PROFILER_PATH"),
     "the .NET host runs a startup hook, and loads a profiler library, before "
     "the entrypoint's Main"),
    (("RUBYOPT", "RUBYLIB", "PERL5OPT", "PERL5LIB", "PERLLIB"),
     "ruby and perl read them for -r and -I, requiring a library before the "
     "script they were pointed at"),
)
INJECTING_ENV: Mapping[str, str] = MappingProxyType({
    name: reason for names, reason in _INJECTING_ENV_GROUPS for name in names})


def injecting_env_reason(name: str, *, windows: bool | None = None) -> str | None:
    """Say why an operator may not reference ``name``, or ``None`` if they may.

    Args:
        name: An environment variable name, in the spelling the operator wrote.
        windows: Whether to match without regard to case. ``None`` asks the
            running platform, which is the only honest default: Windows
            environment names are case-insensitive, so ``Ld_Preload`` there IS
            ``LD_PRELOAD`` and a case-sensitive rule would be bypassed by
            shift-key alone. On POSIX the two spellings are different variables
            and folding them would refuse a name that can inject nothing.

    Returns:
        The reason this name is refused, or ``None`` when it may be referenced.
    """
    if windows is None:
        windows = os.name == "nt"
    return INJECTING_ENV.get(name.upper() if windows else name)
