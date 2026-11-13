"""Start a fresh Arachnid Studio project for local utility exchanges on Windows."""
import argparse
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
import sys

from conductor.__main__ import main as conduct


def start():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dir", type=Path, required=True, help="new or empty project directory")
    parser.add_argument("--port", type=int, default=0, help="loopback port (0 chooses a free port)")
    args = parser.parse_args()
    if not 0 <= args.port <= 65535:
        parser.error("port must be between 0 and 65535")
    try:
        project = args.dir.absolute()
        if project.resolve() != project:
            parser.error("choose a project path without links or junctions")
        project.mkdir(parents=True, exist_ok=True)
        if any(project.iterdir()):
            parser.error("choose a fresh empty project directory")
    except OSError as error:
        parser.error(str(error))
    for command in (["init", "--template", "default-orbit"],
                    ["ownership", "activate", "--legacy-writers-stopped"]):
        output = StringIO()
        with redirect_stdout(output), redirect_stderr(output):
            code = conduct([*command, "--dir", str(project)])
        if code:
            print(output.getvalue(), file=sys.stderr, end="")
            return code
    print("Откройте локальный адрес ниже. В Studio выберите «Подключить харнесс».",
          file=sys.stderr, flush=True)
    return conduct(["up", "--dir", str(project), "--port", str(args.port)])


if __name__ == "__main__":
    raise SystemExit(start())
