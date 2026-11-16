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
    parser.add_argument("action", choices=("create", "open", "demo"))
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
    demo = args.action == "demo"
    if demo:
        location = {"session": "demo-codex-grok", "lang": "ru"}
    else:
        ids = json.loads(metadata.read_text(encoding="utf-8"))
        location = {"task": ids["second"], "lang": "ru"}
    server_drain.enable_ctrl_c()
    stopper = server_drain.Stopper()
    if args.stop_on_stdin_eof:
        stopper.watch_stdin(sys.stdin.fileno())
    http = server.build(project, args.port, launch=Launch(mode="view"))
    origin = f"http://127.0.0.1:{http.server_port}/#"
    url = origin + urlencode(location)

    def announce():
        if demo:
            print("Учебная реконструкция Codex + Grok:", url, flush=True)
            print("Для двух своих задач выполните START.cmd new.", flush=True)
        else:
            print("Вторая задача:", url, flush=True)
            print("Источник первой задачи:", origin + urlencode({"session": ids["first"],
                                                                 "lang": "ru"}), flush=True)
        print("Для закрытия Studio нажмите Ctrl+C в этом окне.", flush=True)
        if not args.no_browser:
            try:
                os.startfile(url)
            except OSError:
                print("Откройте адрес Studio в браузере.", flush=True)

    return server_drain.serve_until_stopped(http, up_status.NullStatus(), stopper, announce=announce)


if __name__ == "__main__":
    raise SystemExit(main())
