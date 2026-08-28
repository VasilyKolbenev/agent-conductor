# ADR 0007: The `env_allow` trust boundary

- **Status:** Accepted
- **Date:** 2026-08-28

## Context

An operator pins a vendor build by absolute path and lists, in `env_allow`, the parent environment
variables that build may read. Every name listed reaches the child of a real spawn with the
parent's value; nothing else does. Until now the only checks on that list were type, POSIX name
grammar and uniqueness, so any name at all could be written into it.

That is the right mechanism for a credential — it is what `env_allow` exists for — and it is the
wrong mechanism for a variable the child's own runtime reads before the pinned entrypoint runs. The
security audit of `ade6a7f` closed with the operator trust boundary as the one question it had not
settled, naming `PATH`, `PYTHONPATH` and `LD_PRELOAD` and asking whether allowlisting them should be
refused.

Three facts decide the answer, and all three were established by running this build rather than by
reading it.

1. **Nothing here resolves an executable by name.** `ProcessRunner._spawn` calls
   `subprocess.Popen(list(spec.argv), …, shell=False)` with `argv[0]` an absolute path every
   provider has already proved absolute. Neither `execve` nor `CreateProcess` searches for an
   absolute program, so `PATH` cannot redirect the reviewed entrypoint. `PATH` reaching the child is
   a fact about what that child may go on to find, never about which build started.
2. **An interpreter variable takes the process before the entrypoint gets it.** With
   `env_allow=("PYTHONPATH",)` and the deepseek-harness pin shape — `argv = [sys.executable,
   entrypoint]` — a directory holding a `json.py` was pointed at by the parent value. The reviewed
   entrypoint ran, exit code 0, and its output was `reviewed entrypoint ran attacker-controlled`:
   the attacker's module had already executed inside the process and written a file. With
   `env_allow=("PYTHONHOME",)` the interpreter never reached the entrypoint at all
   (`Failed to import encodings module`). A pin that says which build runs is worth little beside a
   variable that says what runs inside it.
3. **Windows folds case and POSIX does not.** `_child_env` looks names up in the ambient snapshot
   with an exact dictionary lookup. Windows treats environment names case-insensitively and CPython
   upper-cases every key of `os.environ` on `nt`, so `Ld_Preload` and `LD_PRELOAD` are one variable
   there; on POSIX they are two, and only one of them is read by any loader.

## Decision

`env_allow` may name a variable that carries a **secret** or that supports **tool discovery**. It
may not name a variable that causes **code to be loaded into the reviewed process ahead of its own
entrypoint**. The distinction is a relation, not a feeling about a name: `PATH` selects a separate
program the child may choose to start, and the entrypoint still runs first and still decides;
`LD_PRELOAD` selects code that runs inside the reviewed process before its first instruction.

The refusal lives in `CommandSpec` (`process.py::_env_names`), because every road that starts a
child ends in a `CommandSpec` — the operator provider file, the public dispatch body, the deep
adapters and all five headless harnesses — and a refusal on any single door would leave the others
open. The refused roster is closed and each entry states its reason:

| group | names | why |
|---|---|---|
| ELF loader | `LD_PRELOAD`, `LD_AUDIT`, `LD_LIBRARY_PATH` | the dynamic loader maps and runs what they name before the program's first instruction |
| macOS dyld | `DYLD_INSERT_LIBRARIES`, `DYLD_LIBRARY_PATH`, `DYLD_FRAMEWORK_PATH`, `DYLD_FALLBACK_LIBRARY_PATH`, `DYLD_FALLBACK_FRAMEWORK_PATH` | dyld inserts and redirects libraries before `main()` |
| CPython | `PYTHONPATH`, `PYTHONHOME`, `PYTHONSTARTUP`, `PYTHONEXECUTABLE` | read before the pinned entrypoint script, so its first import can be an attacker's module |
| node | `NODE_OPTIONS`, `NODE_PATH`, `NODE_REPL_EXTERNAL_MODULE` | `--require` / `--import` execute modules, and `NODE_PATH` resolves requires, ahead of the entrypoint |
| JVM | `JAVA_TOOL_OPTIONS`, `_JAVA_OPTIONS`, `JDK_JAVA_OPTIONS`, `CLASSPATH` | the option variables carry `-javaagent`, whose `premain` runs before `main`; `CLASSPATH` decides which class a name is |
| .NET | `DOTNET_STARTUP_HOOKS`, `CORECLR_ENABLE_PROFILING`, `CORECLR_PROFILER`, `CORECLR_PROFILER_PATH`, `COR_ENABLE_PROFILING`, `COR_PROFILER`, `COR_PROFILER_PATH` | the host runs a startup hook and loads a profiler library before `Main` |
| ruby, perl | `RUBYOPT`, `RUBYLIB`, `PERL5OPT`, `PERL5LIB`, `PERLLIB` | `-r` and `-I` require a library before the script |

Matching is on the **whole name**, never a prefix or substring — `PATHEXT` is a real variable an
operator may need and begins with `PATH`. Matching folds case when, and only when, the platform
does: `os.name == "nt"`. The rule takes the platform as an argument (`injecting_env_reason(name, *,
windows=…)`) so both values are exercised by tests on either machine.

The list is closed against the **runtimes a vendor CLI in this build can be** rather than against
today's five providers, because the next provider is written from whatever the last one left.
Adding a runtime obliges adding its row.

## Consequences

An operator keeps every authority the mechanism was built for. Credentials
(`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `KIMI_MODEL_API_KEY`, `DSH_API_KEY`, …) are admitted
unchanged, and so are `PATH`, `PATHEXT`, `COMSPEC`, `SystemRoot`, `TEMP`, `HOME` and proxy
settings — a vendor CLI that shells out to `git` still finds it. A refusal list that broke real
operation would be a worse defect than the one it fixes, so tool discovery is proved end to end by a
real spawn that walks `PATH`, locates a helper it was never given the path to, and runs it.

What this boundary does **not** protect against, said out loud:

- **A hostile pinned build.** The pin decides which executable runs; if that executable is hostile,
  nothing here helps. This ADR narrows who else gets to run code inside it, not what it may do.
- **Literal `env` values.** `CommandSpec.env` is code-owned — forced vendor switches and the minted
  home — and is deliberately left unrestricted, because a future adapter may legitimately need to
  point a vendor at a library directory it ships. An operator cannot reach it: the public dispatch
  body refuses the `env` key outright, and the provider config file has no such field.
- **A value, as opposed to a name.** An admitted name still carries whatever the parent holds. A
  poisoned `PATH` can still send a child that shells out to the wrong `git`. That is discovery-class
  risk and is bounded by cwd containment and the ownership token, not by this list.
- **Reporting quality on the harness road.** `headless_cli._spawn` converts every
  `ProcessRunnerError` into "the {tool} harness could not start the pinned build". A refused
  `env_allow` name in a provider pin therefore surfaces as that sentence rather than as a message
  naming the file and row. The refusal is correct; the message is not yet as useful as
  `operator_config` can make it. Adding the same predicate at the operator-config door, purely for
  the message, is owed work and is not a second boundary.
- **Runtimes with no row.** A future provider on a runtime not listed above is admitted by
  omission until its row is written.
