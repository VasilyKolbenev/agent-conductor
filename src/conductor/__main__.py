"""The `conduct` command-line interface.

Subcommands: `validate` (schema errors → exit 1, merge warnings → stdout),
`init` (scaffold conductor/ and print the bootstrap prompt), `prompt <role>`
(vend a role's working prompt). `up` and `demo` are declared but land in
later tasks. Every command takes `--dir` (the project root, default `.`).
Exit codes flow through `main`'s return value (0 ok, 1 failure), with two
exceptions: the up/demo stubs raise SystemExit("not yet implemented"), and
argparse exits 2 on usage errors.
"""
from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from conductor import merge, prompts, store


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


def _cmd_not_implemented(args: argparse.Namespace) -> int:
    """Placeholder body for subcommands that land in later tasks."""
    raise SystemExit("not yet implemented")


def _build_parser() -> argparse.ArgumentParser:
    """Build the `conduct` argument parser with all subcommands."""
    parser = argparse.ArgumentParser(
        prog="conduct",
        description="A local, decision-centric control plane for AI coding agents.")
    sub = parser.add_subparsers(dest="command", required=True)
    commands: list[tuple[str, str, Callable[[argparse.Namespace], int]]] = [
        ("validate", "check map.toml and lane files; report errors and warnings",
         _cmd_validate),
        ("init", "scaffold conductor/ and print the bootstrap prompt", _cmd_init),
        ("prompt", "print the working prompt for one cycle role", _cmd_prompt),
        ("up", "serve the dashboard (not yet implemented)", _cmd_not_implemented),
        ("demo", "run the scripted demo (not yet implemented)", _cmd_not_implemented),
    ]
    for name, help_text, func in commands:
        p = sub.add_parser(name, help=help_text)
        if name == "prompt":
            p.add_argument("role", help="a cycle.roles id from map.toml")
        p.add_argument("--dir", default=".",
                       help="project root, the directory holding conductor/ (default: .)")
        p.set_defaults(func=func)
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
