"""Create a pair or open its second task with Studio from the installed wheel."""
import argparse
import json
import os
from pathlib import Path
import runpy
import sys
from urllib.parse import urlencode

from conductor import server, server_drain, up_status
from conductor.command.project_claim import Launch


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("create", "open"))
    parser.add_argument("work", type=Path)
    parser.add_argument("--port", default=0, type=int)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--stop-on-stdin-eof", action="store_true")
    args = parser.parse_args()
    project, metadata = args.work / "project", args.work / "tasks.json"
    if args.action == "create":
        create = runpy.run_path(str(Path(__file__).with_name("first_task.py")))["create"]
        first, second = create(project, **json.load(sys.stdin))
        with metadata.open("x", encoding="utf-8") as out:
            json.dump({"first": first, "second": second}, out)
        return 0
    ids = json.loads(metadata.read_text(encoding="utf-8"))
    server_drain.enable_ctrl_c()
    stopper = server_drain.Stopper()
    if args.stop_on_stdin_eof:
        stopper.watch_stdin(sys.stdin.fileno())
    http = server.build(project, args.port, launch=Launch(mode="view"))
    origin = f"http://127.0.0.1:{http.server_port}/#"
    second_url = origin + urlencode({"task": ids["second"], "lang": "ru"})
    first_url = origin + urlencode({"session": ids["first"], "lang": "ru"})

    def announce():
        print("Вторая задача:", second_url, flush=True)
        print("Источник первой задачи:", first_url, flush=True)
        print("Для закрытия пилота нажмите Ctrl+C в этом окне.", flush=True)
        if not args.no_browser:
            try:
                os.startfile(second_url)
            except OSError:
                print("Откройте адрес второй задачи в браузере.", flush=True)

    return server_drain.serve_until_stopped(http, up_status.NullStatus(), stopper, announce=announce)


if __name__ == "__main__":
    raise SystemExit(main())
