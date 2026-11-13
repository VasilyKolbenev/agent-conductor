"""Show the bundled training project using the installed Studio in read-only mode."""
import argparse
from pathlib import Path

from conductor import server
from conductor.command.project_claim import Launch


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dir", type=Path, required=True, help="Extracted offline demo folder")
    parser.add_argument("--port", type=int, default=0, help="Loopback port (0 picks a free port)")
    args = parser.parse_args()
    if not 0 <= args.port <= 65535:
        parser.error("port must be between 0 and 65535")
    with server.build(args.dir.resolve(), args.port, launch=Launch(mode="view")) as http:
        print(f"http://127.0.0.1:{http.server_port}/#session=demo-codex-grok&lang=ru", flush=True)
        print("Offline training reconstruction. Press Ctrl+C to close.", flush=True)
        try:
            http.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
