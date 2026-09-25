"""The `conduct` command-line interface.

Subcommands: `validate` (schema errors → exit 1, merge warnings → exit 0);
`init` (scaffold conductor/ from a template and print the prompt that fills
it in — `--template NAME` is the explicit path, a terminal without it gets a
guided wizard, and anything that is not a terminal takes the same default
without reading stdin); `doctor` (report whether this project is set up to
work and name the command that fixes each problem — exit 1 while anything is
wrong or could not be checked); `prompt --role R [--author A]` (vend a role's
working prompt; the positional role form is deprecated); `report` (render the
merged state as a Markdown report); `preview` (create/open a run with a frozen
config, propose one dispatch through the command service, and print its canonical
preview for inspection — it prepares and executes nothing); `integration-smoke`
(run the fixed synthetic Day-1 loop through the owned-process adapter, verify
honestly, and print the immutable result receipt; it is not Human Confirm);
`providers` (ask for one harness's absolute paths and the
environment variable NAMES it may read, and write `conductor/providers.json`;
it takes no setting on the command line and accepts no credential value);
`up` (serve the panel
on 127.0.0.1 with SSE
live updates; Ctrl-C → exit 0; `--providers PATH` names the operator provider
file, default `conductor/providers.json`, and an absent one configures nothing);
`demo` (materialize the bundled fixture into a
temp directory, write the workflow, revision and run the Studio reads, and serve
both halves — takes `--port` but no `--dir`). Every other
command takes `--dir` (the project root, default `.`).

THE STREAM CONTRACT, which every command here obeys and every command added
here must obey. stdout carries the command's primary result and nothing else,
so that redirecting it yields something usable on its own: the rendered prompt
for `prompt`, the bootstrap prompt for `init`, the validation report for
`validate`, the Markdown report for `report`, the bare URL for `up` and
`demo`. stderr carries everything a
person reads around that — dialogue, progress, explanations, deprecation
warnings, and errors that mean the command could not run.

Two deliberate exceptions. What `validate` found IS its result, so findings
stay on stdout even when the exit code is 1; and a clean `validate` prints
nothing at all, on either stream. Whether a terminal is attached changes the
conversation on stderr, never a byte of stdout.

Nothing structural enforces this. It is held by review and by one contract
test per command, in `tests/test_cli.py` and — for `init` — `tests/test_init.py`;
a new command that prints its progress to stdout would pass every other check
in the suite.

Exit codes flow through `main`'s return value (0 ok, 1 failure); argparse
exits 2 on usage errors.
"""
from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from pathlib import Path

from conductor import doctor, init, prompts, report, store, templates, validate

# `conductor.demo`, `conductor.server`, `conductor.command.preview`, and
# `conductor.command.control_loop` are imported inside the commands that need
# them, not here. demo copies a tree with `shutil`, server reads `os.environ`, and
# the command modules' run store uses `os`/`tempfile` for durable writes — all
# legitimate, none a probe, but importing them at module scope would put them on
# the import path of EVERY command, `conduct init` included. The machine-probing
# guard in tests/test_init_probing_ban.py measures what a real `conduct init`
# imports, so hoisting any of them back to the top makes that test fail. That is
# the point: the boundary is enforced, not asserted.


def _cmd_validate(args: argparse.Namespace) -> int:
    """Print schema errors (exit 1) or merge warnings (exit 0)."""
    errors, warnings = validate.check(args.dir)
    for line in errors or warnings:
        print(line)
    return 1 if errors else 0


# No `_cmd_init`: `init.run(args)` already has the `args.func(args)` shape, so
# a wrapper here would be pure indirection restating a contract that lives in
# `conductor.init`. Its `ask=` parameter, which argparse never passes, belongs
# to the tests that inject a scripted wizard — and they test `conductor.init`.


def _cmd_prompt(args: argparse.Namespace) -> int:
    """Render the role prompt; bad author, broken map, or unknown role → stderr, exit 1."""
    if args.role_positional is not None and args.role is not None:
        args.prompt_parser.error("give the role via --role or positionally, not both")
    if args.role_positional is None and args.role is None:
        args.prompt_parser.error("a role is required: conduct prompt --role <role>")
    if args.role_positional is not None:
        print("warning: positional role is deprecated; use --role/--author",
              file=sys.stderr)
    role = args.role if args.role is not None else args.role_positional
    if args.author is not None and not store.AUTHOR_RE.fullmatch(args.author):
        print(f"invalid author {args.author!r}: must match the lane filename "
              "rule (letters, digits, _ and - only)", file=sys.stderr)
        return 1
    loaded = store.load(args.dir)
    if loaded.map_error is not None:  # a substitute empty map would mislead the agent
        print(f"cannot vend a prompt: {loaded.map_error}", file=sys.stderr)
        return 1
    try:
        state = validate.merged_state(loaded)
        text = prompts.role_prompt(state, role, args.author)
    except prompts.UnknownRole as e:
        print(str(e), file=sys.stderr)
        return 1
    # write, not print: role_prompt() already ends in a newline, and print's
    # own would put a blank line at the end of every redirected prompt.
    sys.stdout.write(text)
    return 0


def _cmd_report(args: argparse.Namespace) -> int:
    """Write the Markdown report of the merged state to stdout.

    The state comes from `store.load` + `validate.merged_state` — the same two
    calls `prompt` makes, and no second merge is written here.
    `tests/test_report.py` measures the rest of that claim by running this
    command: on one project, what it writes to stdout is the report of the very
    document the panel's server serves, `generated_at` apart. A missing
    `conductor/` raises `store.StoreError`, which `main` reports on stderr with
    exit 1; stdout stays empty, so a redirected report file is never a
    half-written one. A map that will not parse is not that failure: the merger
    represents it as `project_status.state == "unknown"`, which is a state worth
    reporting.
    """
    state = validate.merged_state(store.load(args.dir))
    # write, not print: render() already ends in exactly one newline.
    sys.stdout.write(report.render(state))
    return 0


def _serve(root: Path | str, port: int, providers: str | None = None) -> int:
    """Serve the panel for `root` on 127.0.0.1; Ctrl-C shuts down cleanly.

    `providers` names the operator's provider file; without it the default under
    the project's own `conductor/` is read, and an absent file configures nothing.
    A file that IS there and cannot be honoured is a refusal on stderr with exit
    1 and no server at all — starting with a provider the operator asked for
    silently dropped would be the worse answer.
    """
    from conductor import server              # deferred: see the import block
    from conductor.command import operator_config   # deferred: see the import block
    path = (Path(providers) if providers is not None
            else operator_config.provider_config_path(store.conductor_dir(root)))
    try:
        pinned = operator_config.load_provider_configs(path)
    except operator_config.OperatorConfigError as e:
        print(str(e), file=sys.stderr)
        return 1
    try:
        srv = server.build(root, port=port, providers=pinned)
    except OSError as e:                  # port busy / unbindable → exit 1
        # `port` is the one the user asked for, and the ONLY port this message
        # may name: an OSError is not proof the port is busy, and no other
        # port is known to be free, so the hint keeps the PORT placeholder
        # literal instead of volunteering a number.
        print(f"cannot serve on 127.0.0.1:{port}: {e}. "
              "To try a different port, rerun with --port PORT.", file=sys.stderr)
        return 1
    host, bound = srv.server_address[:2]
    # The URL is the result; how to stop the server is lifecycle chatter. Split
    # so `conduct up | xargs open` gets a URL and not a sentence about it.
    #
    # flush=True is load-bearing, not tidiness. A redirected stdout is
    # block-buffered, and the next statement blocks until the server stops —
    # so without the flush the URL reaches the pipe only once it is useless,
    # and a killed server never emits it at all. stderr needs no flush: it is
    # line-buffered whether or not it is a terminal.
    print(f"http://{host}:{bound}/", flush=True)
    print(f"serving {root} — Ctrl+C to stop", file=sys.stderr)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
    return 0


def _cmd_up(args: argparse.Namespace) -> int:
    """Serve the panel on 127.0.0.1; Ctrl-C shuts down cleanly (exit 0)."""
    return _serve(args.dir, args.port, args.providers)


def _cmd_providers(args: argparse.Namespace) -> int:
    """Configure one provider interactively; deferred so `init` never imports it.

    `conductor.provider_setup` reaches the command package for the catalogue,
    the provider contract and the operator file. Importing it at module scope
    would put all of that on `conduct init`'s import path, which
    tests/test_init_probing_ban.py measures.
    """
    from conductor import provider_setup          # deferred: see the import block

    return provider_setup.run(args)


def _cmd_demo(args: argparse.Namespace) -> int:
    """Materialize the bundled demo into a temp dir and serve BOTH its halves.

    The front door is the Workflow Studio, which reads the command surface; the
    packaged fixture is Protocol v1, which the Studio does not read. Writing
    only the fixture served a person an empty Overview, an empty workflow list
    and an empty run list over a directory that in fact held the whole story.
    So both halves are written here, and `populate` is not optional: a demo
    that cannot build its own story is a broken demo and says so, rather than
    serving the empty front door that made this a finding.
    """
    import tempfile               # local to its one use; no boundary rides on it
    from conductor import demo                # deferred: see the import block
    from conductor.command.run_store import StoreError   # deferred with it
    try:
        root = demo.materialize(Path(tempfile.mkdtemp(prefix="conduct-demo-")))
    except OSError as e:                  # unwritable temp dir / broken package data
        print(f"cannot materialize the demo fixture: {e}", file=sys.stderr)
        return 1
    try:
        named = demo.populate(root)
    except (OSError, StoreError) as e:
        print(f"cannot build the demo workflow and run: {e}", file=sys.stderr)
        return 1
    print(f"demo fixture materialized in {root} (throwaway copy)", file=sys.stderr)
    print(f"demo workflow {named['workflow_id']} revision {named['revision']}, "
          f"run {named['run_id']}, gate {named['waiting_gate']} is waiting",
          file=sys.stderr)
    return _serve(root, args.port)


def _require_a_project(root: Path | str) -> None:
    """Refuse a directory that is not a Conduct project, before anything writes.

    Only `conduct init` may bring a project into existence. `preview` and
    `integration-smoke` build a run store straight from `--dir` and reach
    `runs_root.mkdir(parents=True)`; that `parents=True` is there for `runs/`
    under an existing `conductor/`, and creating `conductor/` itself was its
    side effect. Run either command one directory too high and the directory
    silently became a project — and a durably broken one, because `conduct
    init` refuses any existing `conductor` and would then report state the
    person never created as their own.

    The question asked is the one the rest of the product already means by
    "this is a project": `conductor/` is a directory. `store.conductor_dir`
    defines it, `doctor` reports its absence as a project that was never set
    up, and the message raised here is theirs — it names the directory and the
    command that fixes it, and `main` turns it into stderr with exit 1, leaving
    stdout empty as the stream contract requires.

    Args:
        root: The project root the command was pointed at (`--dir`).

    Raises:
        store.StoreError: If `root` holds no `conductor/` directory.
    """
    store.conductor_dir(root)


def _cmd_preview(args: argparse.Namespace) -> int:
    """Print the canonical dispatch preview for one configured instance.

    The Day-1 control-loop gate: it opens (or creates) a run with a frozen config,
    asks the fixed CommandService for one dispatch proposal bound to the instance,
    and writes that proposal's canonical JSON — preview_digest included — to stdout
    for inspection. It prepares, executes and spawns nothing. An unknown instance,
    an adapter that does not match the frozen config's binding, and a run already
    standing at the preview's identity that is not the preview's own run are each
    a refusal on stderr with exit 1; stdout stays empty, so a redirected preview
    is never a half-written one.

    A directory that is not a Conduct project yet is the refusal that comes
    before all of those; `_require_a_project` says why.
    """
    _require_a_project(args.dir)
    from conductor.command import preview          # deferred: see the import block
    try:
        rendered = preview.render_dispatch_preview(
            args.dir, instance_id=args.instance, adapter_id=args.adapter)
    except preview.PreviewError as e:
        print(str(e), file=sys.stderr)
        return 1
    # write, not print: the canonical preview is one line and gets exactly one
    # trailing newline, so a redirected preview is a clean single-line document.
    sys.stdout.write(rendered + "\n")
    return 0


def _cmd_integration_smoke(args: argparse.Namespace) -> int:
    """Run the synthetic Day-1 loop and print the immutable result receipt.

    The synthetic companion to `preview`: it opens the fixed fixture run,
    authorizes one synthetic dispatch, executes it through the owned-process adapter, and
    writes the canonical result receipt to stdout. A run at the
    scenario's fixed identity that disagrees with it is a refusal on stderr with
    exit 1; stdout stays empty, so a redirected receipt is never a half-written one.

    A directory that is not a Conduct project yet is refused before any of that,
    for the reason `_require_a_project` records.
    """
    _require_a_project(args.dir)
    from conductor.command import control_loop      # deferred: see the import block
    try:
        rendered = control_loop.render_integration_smoke(args.dir)
    except control_loop.GateError as e:
        print(str(e), file=sys.stderr)
        return 1
    # write, not print: the canonical receipt is one line and gets exactly one
    # trailing newline, so a redirected receipt is a clean single-line document.
    sys.stdout.write(rendered + "\n")
    return 0


def _reconcile_listing(root: str) -> int:
    """Print every action a crash stranded, and name what could not be read.

    Two findings, not one, and the second used to be dropped. Filtering the
    survey to runs that HAVE actions discards an unreadable run, which has
    none -- so a project holding nothing but a broken run answered "no action
    is waiting", exit 0: a clean bill of health for a run nobody can open.
    They are reported separately because they are separate repairs, and the
    clean sentence is said only when both are empty.
    """
    from conductor.command import reconcile        # deferred: see the import block
    found = reconcile.survey(root)
    stranded = [row for row in found if row.actions]
    unreadable = [row.run_id for row in found if row.unreadable]
    for row in stranded:
        for action_id in row.actions:
            sys.stdout.write(f"{row.run_id} {action_id}\n")
    if stranded:
        print("\nclose one with: conduct reconcile --run <RUN> --action <ACTION>",
              file=sys.stderr)
    if unreadable:
        print(f"\n{len(unreadable)} run(s) could not be read, which is a "
              f"different repair: {chr(44).join(unreadable)}", file=sys.stderr)
        print("a journal that will not replay is not closed by reconcile; "
              "ADR 0002 records that recovery.", file=sys.stderr)
    if not stranded and not unreadable:
        print("no action in this project is waiting for reconcile",
              file=sys.stderr)
    return 0


def _cmd_reconcile(args: argparse.Namespace) -> int:
    """List the actions a crash stranded, or close exactly one of them.

    The operation itself is `ControlRuntime.reconcile`, and this command adds
    nothing to it but reach: every refusal it holds it still holds, no adapter
    is resolved, and the one record appended is a terminal `unknown`. What this
    adds is the half that made the documented procedure unusable -- a way to
    find out which run and which action, which nothing in the product would say.

    With neither `--run` nor `--action`, it lists. With both, it closes and
    writes the canonical receipt to stdout. With exactly one it refuses, because
    half a reference names an action of no run or a run with no action, and
    guessing the other half is the one thing a recovery command must not do.
    """
    _require_a_project(args.dir)
    from conductor.command import reconcile        # deferred: see the import block
    from conductor.command.contract_values import ContractError, canonical_json
    from conductor.command.runtime_values import ExecutionError
    from conductor.command.store_errors import StoreError
    if (args.run is None) != (args.action is None):
        missing = "--action" if args.action is None else "--run"
        print(f"reconcile needs --run and --action together; {missing} is missing",
              file=sys.stderr)
        return 1
    if args.run is None:
        return _reconcile_listing(args.dir)
    # The three the operation can raise, named rather than swallowed: a refusal
    # reconcile holds, a run that will not read, and an id the contract refuses.
    # CorruptRun is a StoreError, so an unreadable journal lands here too.
    try:
        receipt = reconcile.close(args.dir, args.run, args.action)
    except (ExecutionError, StoreError, ContractError) as e:
        print(str(e), file=sys.stderr)
        return 1
    sys.stdout.write(canonical_json(receipt.as_dict()) + "\n")
    return 0


#: The port `up` and `demo` bind, and the one `init` tells the user to open.
#: One constant, because init advising a port the panel is not on is worse
#: than init saying nothing about the panel at all.
DEFAULT_PORT = 7777


def _add_port(p: argparse.ArgumentParser) -> None:
    """Attach the shared `--port` option to a serving subparser."""
    p.add_argument("--port", type=int, default=DEFAULT_PORT,
                   help=f"TCP port on 127.0.0.1 (default: {DEFAULT_PORT})")


def _add_providers(p: argparse.ArgumentParser) -> None:
    """Attach `up`'s operator provider file, the one surface that configures a provider."""
    # Deliberately a PATH and nothing else. What may be inside that file is
    # closed by `conductor.command.operator_config`, so no provider setting is
    # ever spelled on a command line and no secret value can be. The default is
    # spelled out here rather than imported: importing the command package at
    # parser-build time would put it on `conduct init`'s import path, which
    # tests/test_init_probing_ban.py measures. The behaviour test in
    # tests/test_operator_provider_config.py holds the two spellings together.
    p.add_argument("--providers", metavar="PATH", default=None,
                   help="operator provider file pinning each provider's absolute "
                        "executable, protocol and environment NAMES "
                        "(default: conductor/providers.json; absent configures "
                        "nothing)")


def _add_stranded_ids(p: argparse.ArgumentParser) -> None:
    """Attach `reconcile`'s two ids: the run, and the action inside it.

    Two ids and a directory, and deliberately nothing else. No mode, no outcome
    and no detail: what the terminal receipt says is code-owned, and an operator
    who could word it could word a success for an effect nobody observed. Both
    default to `None` so the command can tell "list everything" from "close this
    one" without a separate flag, and half a reference is refused rather than
    completed by guesswork.
    """
    p.add_argument("--run", default=None, metavar="RUN_ID",
                   help="the run holding the stranded action")
    p.add_argument("--action", default=None, metavar="ACTION_ID",
                   help="the action to close; needs --run")


def _add_dir_and_func(p: argparse.ArgumentParser,
                      func: Callable[[argparse.Namespace], int]) -> None:
    """Attach the shared `--dir` option and the dispatch target to a subparser."""
    p.add_argument("--dir", default=".",
                   help="project root, the directory holding conductor/ (default: .)")
    p.set_defaults(func=func)


def _add_template(p: argparse.ArgumentParser) -> None:
    """Attach `init`'s `--template`, whose help lists the maps `templates` vends."""
    # Deliberately NOT argparse `choices`: that raises a usage error (exit 2)
    # and hardcodes a second copy of the list. The explicit check in
    # `init.run` exits 1 with templates.get()'s own message, so the available
    # names can never drift from the module that vends them.
    p.add_argument("--template", metavar="NAME",
                   help="starting map: " + ", ".join(n for n, _ in templates.names())
                        + f" (default: {templates.DEFAULT}; omit it in a terminal "
                          "to be asked instead)")


def _add_role_and_author(p: argparse.ArgumentParser) -> None:
    """Attach `prompt`'s role addressing, keeping the positional spelling deprecated."""
    # ADR 0001: the positional is the DEPRECATED spelling of --role and its
    # meaning must NEVER be silently redefined (e.g. to an instance id in v2) —
    # any new addressing scheme gets its own flag.
    p.add_argument("role_positional", nargs="?", metavar="role", default=None,
                   help="deprecated positional form of --role")
    p.add_argument("--role", help="a cycle.roles id from map.toml")
    p.add_argument("--author",
                   help="your lane author id — fills conductor/lanes/<author>.json "
                        "into the prompt")
    p.set_defaults(prompt_parser=p)   # lets _cmd_prompt raise argparse usage errors


def _add_instance_and_adapter(p: argparse.ArgumentParser) -> None:
    """Attach `preview`'s addressing; the frozen config, not this flag, binds the adapter."""
    p.add_argument("--instance", default="claude-dev",
                   help="the configured instance to propose against (default: claude-dev)")
    p.add_argument("--adapter", default=None,
                   help="cross-check the adapter the frozen config binds to the instance")


def _add_map_commands(sub: argparse._SubParsersAction) -> None:
    """The five verbs that read or write the project's own documents.

    Split from `_build_parser` for the project's function-length limit, along
    the seam the CLI already has: these five touch `map.toml` and the lanes and
    reach no run store, which is why none of them is deferred-imported.
    """
    p = sub.add_parser("validate",
                       help="check map.toml and lane files; report errors and warnings")
    _add_dir_and_func(p, _cmd_validate)

    p = sub.add_parser("init", help="scaffold conductor/ and print the bootstrap prompt")
    p.set_defaults(default_port=DEFAULT_PORT)   # init advises it, never binds it
    _add_template(p)
    _add_dir_and_func(p, init.run)

    p = sub.add_parser("doctor",
                       help="check whether this project is set up to work, and how to fix it")
    _add_dir_and_func(p, doctor.run)

    p = sub.add_parser("prompt", help="print the working prompt for one cycle role")
    _add_role_and_author(p)
    _add_dir_and_func(p, _cmd_prompt)

    p = sub.add_parser("report", help="print a Markdown report of the merged state")
    _add_dir_and_func(p, _cmd_report)


def _cmd_ownership(args):
    from conductor.ownership_cli import ownership_command
    return ownership_command(args)


def _add_ownership(sub):
    parser = sub.add_parser("ownership", help="explicit ownership status and maintenance")
    parser.add_argument("operation", choices=("status", "activate", "rollback", "recover", "recover-login"))
    parser.add_argument("--legacy-writers-stopped", action="store_true")
    parser.add_argument("--auth-home", default=None)
    _add_dir_and_func(parser, _cmd_ownership)


def _build_parser() -> argparse.ArgumentParser:
    """Build the `conduct` argument parser: one explicit block per subcommand."""
    parser = argparse.ArgumentParser(
        prog="conduct",
        description="A local, decision-centric control plane for AI coding agents.")
    sub = parser.add_subparsers(dest="command", required=True)
    _add_map_commands(sub)
    _add_ownership(sub)

    p = sub.add_parser(
        "preview",
        help="propose one dispatch and print its canonical preview (no execution)")
    _add_instance_and_adapter(p)
    _add_dir_and_func(p, _cmd_preview)

    p = sub.add_parser(
        "integration-smoke",
        help="run the synthetic Day-1 owned-process loop (not Human Confirm)")
    _add_dir_and_func(p, _cmd_integration_smoke)

    p = sub.add_parser(
        "reconcile",
        help="list the actions a crash stranded, or close one with a terminal "
             "'unknown' (executes nothing, never reports success)")
    _add_stranded_ids(p)
    _add_dir_and_func(p, _cmd_reconcile)

    p = sub.add_parser(
        "providers",
        help="configure a harness this machine can run; asks for paths and "
             "environment variable NAMES, never a credential")
    _add_dir_and_func(p, _cmd_providers)

    p = sub.add_parser("up", help="serve the panel on loopback HTTP with live updates")
    _add_port(p)
    _add_providers(p)
    _add_dir_and_func(p, _cmd_up)

    # No --dir: demo materializes its own throwaway root.
    p = sub.add_parser(
        "demo", help="serve the bundled demo: a workflow, a run and a "
                     "project map, in a throwaway directory")
    _add_port(p)
    p.set_defaults(func=_cmd_demo)

    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the `conduct` CLI.

    Args:
        argv: Command-line arguments without the program name; None means
            `sys.argv[1:]` (argparse's default).

    Returns:
        Process exit code: 0 on success, 1 on any reported failure
        (schema errors, missing conductor/, unknown role, broken map).
    """
    # Windows consoles/pipes default to the ANSI code page; the messages and
    # prompts we emit contain non-ASCII punctuation. capsys-style substitute
    # streams may lack reconfigure — hence the hasattr guard.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    args = _build_parser().parse_args(argv)
    try:
        from conductor.ownership_cli import dispatch
        return dispatch(args)
    except store.StoreError as e:
        print(str(e), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
