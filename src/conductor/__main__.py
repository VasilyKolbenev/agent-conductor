"""The `conduct` command-line interface.

Subcommands: `validate` (schema errors → exit 1, merge warnings → stdout),
`init` (scaffold conductor/ and print the bootstrap prompt), `prompt <role>`
(vend a role's working prompt), `up` (serve the panel on 127.0.0.1 with SSE
live updates; Ctrl-C → exit 0), `demo` (materialize the bundled fixture
into a temp directory and serve it — takes `--port` but no `--dir`). Every
other command takes `--dir` (the project root, default `.`). Exit codes
flow through `main`'s return value (0 ok, 1 failure); argparse exits 2 on
usage errors.
"""
from __future__ import annotations

import argparse
import sys
import tempfile
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from conductor import demo, merge, prompts, server, store


def _merged_state(loaded: store.Loaded) -> dict:
    """Merge a `Loaded` snapshot into a state dict at the current time."""
    return merge.merge(loaded.map_data, loaded.map_error, loaded.lanes,
                       loaded.events, loaded.skipped_events,
                       datetime.now(timezone.utc),
                       extra_warnings=loaded.warnings)


def _cmd_validate(args: argparse.Namespace) -> int:
    """Print schema errors (exit 1) or merge warnings (exit 0)."""
    loaded = store.load(args.dir)
    errors = [entry["error"] for entry in loaded.lanes if entry["error"] is not None]
    if loaded.map_error is not None:
        errors.insert(0, loaded.map_error)
    if errors:
        for error in errors:          # already self-prefixed (lane <stem>: / map...)
            print(error)
        return 1
    state = _merged_state(loaded)
    for warning in state["warnings"]:
        print(warning)
    return 0


def _cmd_init(args: argparse.Namespace) -> int:
    """Scaffold conductor/ (map.toml stub, lanes/, events.jsonl); print bootstrap."""
    cdir = Path(args.dir) / "conductor"
    if cdir.exists():
        print(f"{cdir} already exists — refusing to touch it", file=sys.stderr)
        return 1
    (cdir / "lanes").mkdir(parents=True)
    (cdir / "events.jsonl").write_text("", encoding="utf-8", newline="\n")
    (cdir / "map.toml").write_text(prompts.MAP_EXAMPLE + "\n",
                                   encoding="utf-8", newline="\n")
    print(f"scaffolded {cdir}: map.toml (edit me), lanes/, events.jsonl\n")
    print(prompts.bootstrap_prompt())
    return 0


def _cmd_prompt(args: argparse.Namespace) -> int:
    """Render the role prompt; broken map or unknown role → stderr, exit 1."""
    loaded = store.load(args.dir)
    if loaded.map_error is not None:  # a substitute empty map would mislead the agent
        print(f"cannot vend a prompt: {loaded.map_error}", file=sys.stderr)
        return 1
    try:
        text = prompts.role_prompt(_merged_state(loaded), args.role)
    except prompts.UnknownRole as e:
        print(str(e), file=sys.stderr)
        return 1
    print(text)
    return 0


def _serve(root: Path | str, port: int) -> int:
    """Serve the panel for `root` on 127.0.0.1; Ctrl-C shuts down cleanly."""
    try:
        srv = server.build(root, port=port)
    except OSError as e:                  # port busy / unbindable → exit 1
        print(f"cannot serve on 127.0.0.1:{port}: {e}", file=sys.stderr)
        return 1
    host, bound = srv.server_address[:2]
    print(f"serving http://{host}:{bound}/ — Ctrl+C to stop")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
    return 0


def _cmd_up(args: argparse.Namespace) -> int:
    """Serve the panel on 127.0.0.1; Ctrl-C shuts down cleanly (exit 0)."""
    return _serve(args.dir, args.port)


def _cmd_demo(args: argparse.Namespace) -> int:
    """Materialize the bundled demo fixture into a temp dir and serve it."""
    try:
        root = demo.materialize(Path(tempfile.mkdtemp(prefix="conduct-demo-")))
    except OSError as e:                  # unwritable temp dir / broken package data
        print(f"cannot materialize the demo fixture: {e}", file=sys.stderr)
        return 1
    print(f"demo fixture materialized in {root} (throwaway copy)")
    return _serve(root, args.port)


def _add_dir_and_func(p: argparse.ArgumentParser,
                      func: Callable[[argparse.Namespace], int]) -> None:
    """Attach the shared `--dir` option and the dispatch target to a subparser."""
    p.add_argument("--dir", default=".",
                   help="project root, the directory holding conductor/ (default: .)")
    p.set_defaults(func=func)


def _build_parser() -> argparse.ArgumentParser:
    """Build the `conduct` argument parser: one explicit block per subcommand."""
    parser = argparse.ArgumentParser(
        prog="conduct",
        description="A local, decision-centric control plane for AI coding agents.")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("validate",
                       help="check map.toml and lane files; report errors and warnings")
    _add_dir_and_func(p, _cmd_validate)

    p = sub.add_parser("init", help="scaffold conductor/ and print the bootstrap prompt")
    _add_dir_and_func(p, _cmd_init)

    p = sub.add_parser("prompt", help="print the working prompt for one cycle role")
    p.add_argument("role", help="a cycle.roles id from map.toml")
    _add_dir_and_func(p, _cmd_prompt)

    p = sub.add_parser("up", help="serve the panel on loopback HTTP with live updates")
    p.add_argument("--port", type=int, default=7777,
                   help="TCP port on 127.0.0.1 (default: 7777)")
    _add_dir_and_func(p, _cmd_up)

    # No --dir: demo materializes its own throwaway root.
    p = sub.add_parser("demo", help="serve the bundled demo fixture")
    p.add_argument("--port", type=int, default=7777,
                   help="TCP port on 127.0.0.1 (default: 7777)")
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
        return args.func(args)
    except store.StoreError as e:
        print(str(e), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
