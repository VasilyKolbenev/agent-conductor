"""Install or reopen the local two-task Arachnid pilot on Windows."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile


HERE = Path(__file__).resolve().parent
WHEEL = "agent_conductor-0.1.0-py3-none-any.whl"
MEMBERS = (WHEEL, "pilot.py", "first_task.py", "studio.py", "START.cmd", "START-HERE.txt")
FLAGS = ("-I", "-B", "-X", "utf8")


def verify():
    entries = {}
    for line in (HERE / "SHA256SUMS.txt").read_text(encoding="ascii").splitlines():
        digest, name = line.split("  ", 1)
        if name not in MEMBERS or name in entries or not re.fullmatch("[0-9a-f]{64}", digest):
            raise ValueError("Invalid SHA256SUMS.txt entry")
        entries[name] = digest
    if set(entries) != set(MEMBERS):
        raise ValueError("Incomplete SHA256SUMS.txt")
    for name, expected in entries.items():
        if hashlib.sha256((HERE / name).read_bytes()).hexdigest() != expected:
            raise ValueError("SHA-256 mismatch: " + name)
    return entries[WHEEL]


def field(prompt, limit, optional=False):
    while True:
        value = input(prompt + " ").strip()
        if (value or optional) and len(value) <= limit and (not value or value.isprintable()):
            return value
        print(f"Введите одну строку длиной до {limit} знаков.")


def collect_record():
    print("Выберите завершённую задачу и следующую, для которой пригодится её опыт.")
    first = field("Первая задача:", 200)
    second = field("Вторая задача:", 200)
    print("Запишите по порядку проверки, которые вы действительно выполнили в первой задаче.")
    checks = []
    for number in range(1, 13):
        question = f"Проверка {number}" + (" (Enter — закончить)" if checks else "") + ":"
        label = field(question, 160, optional=bool(checks))
        if not label:
            break
        checks.append((label, field("Что показала эта проверка?", 600)))
    performer = field("Кто выполнил работу? (Enter — пропустить)", 100, optional=True)
    outcome = field("Итог первой задачи (Enter — пропустить):", 600, optional=True)
    reviewer = field("Кто подтверждает запись? Укажите имя или псевдоним:", 100)
    print(f"\nПервая задача — {first}\nВторая задача — {second}\nИсточник: со слов оператора.")
    for index, (label, observation) in enumerate(checks, 1):
        print(f"{index}. {label}\n   Наблюдение: {observation}")
    if performer:
        print("Исполнитель:", performer)
    if outcome:
        print("Итог:", outcome)
    print("Запись подтверждает:", reviewer)
    answer = input("Введите ПРИНЯТЬ, чтобы сохранить эту запись, или Enter для отмены: ")
    if answer.strip().casefold() not in ("принять", "accept"):
        return None
    return dict(first=first, second=second, checks=checks, reviewer=reviewer,
                performer=performer, outcome=outcome, accepted=True)


def child_env(work):
    env = {key: os.environ[key] for key in
           ("SYSTEMROOT", "WINDIR", "COMSPEC", "PATH", "PATHEXT",
            "PROCESSOR_ARCHITECTURE", "NUMBER_OF_PROCESSORS") if key in os.environ}
    profile = work / "profile"
    folders = {"HOME": profile, "USERPROFILE": profile, "APPDATA": profile / "Roaming",
               "LOCALAPPDATA": profile / "Local", "TEMP": work / "tmp", "TMP": work / "tmp",
               "CONDUCT_HOME": work / "hub"}
    for key, path in folders.items():
        path.mkdir(parents=True, exist_ok=True)
        env[key] = str(path)
    env.update(PIP_CONFIG_FILE=os.devnull, PIP_NO_INDEX="1", PIP_DISABLE_PIP_VERSION_CHECK="1")
    return env


def install_pair(base, record, wheel_sha):
    base.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="p-", dir=base))
    env = child_env(work)
    print("Папка пилота:", work, flush=True)
    venv = work / "venv"
    subprocess.run([sys.executable, *FLAGS, "-m", "venv", str(venv)], env=env, cwd=work, check=True)
    python = str(venv / "Scripts/python.exe")
    subprocess.run([python, *FLAGS, "-m", "pip", "--isolated", "--disable-pip-version-check",
                    "install", "--no-index", "--no-deps", "--no-cache-dir", str(HERE / WHEEL)],
                   env=env, cwd=work, check=True)
    subprocess.run([python, *FLAGS, str(HERE / "studio.py"), "create", str(work)],
                   env=env, cwd=work, input=json.dumps(record).encode("ascii"), check=True)
    (work / "wheel.sha256").write_text(wheel_sha, encoding="ascii")
    with tempfile.NamedTemporaryFile(dir=base, delete=False) as pointer:
        pointer.write(work.name.encode("ascii"))
    Path(pointer.name).replace(base / "latest.txt")
    return work


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("open", "new", "verify"), nargs="?", default="open")
    parser.add_argument("--port", type=int, choices=range(65536), default=0, metavar="0..65535")
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--stop-on-stdin-eof", action="store_true",
                        help="close Studio normally when the controlling input pipe closes")
    parser.add_argument("--work-parent", type=Path, default=Path.home() / "ArachnidPilot2")
    options = parser.parse_args()
    wheel_sha = verify()
    print("Wheel SHA-256:", wheel_sha, flush=True)
    if options.mode == "verify":
        return 0
    if os.name != "nt" or sys.version_info[:2] not in ((3, 11), (3, 12)):
        raise ValueError("Use Python 3.11 or 3.12 on Windows.")
    base = options.work_parent.resolve()
    latest = base / "latest.txt"
    if options.mode == "new" or not latest.exists():
        record = collect_record()
        if record is None:
            print("Создание пары отменено.")
            return 0
        work = install_pair(base, record, wheel_sha)
    else:
        name = latest.read_text(encoding="ascii").strip()
        if not re.fullmatch(r"p-[a-z0-9_]+", name):
            raise ValueError("Invalid latest.txt. Use START.cmd new to start a separate pair.")
        work = base / name
        if (work / "wheel.sha256").read_text(encoding="ascii") != wheel_sha:
            raise ValueError("Open this pair with its original pilot or use START.cmd new.")
    print("Открываем сохранённую пару:", work, flush=True)
    cmd = [str(work / "venv/Scripts/python.exe"), *FLAGS, str(HERE / "studio.py"),
           "open", str(work), "--port", str(options.port)]
    if options.no_browser:
        cmd.append("--no-browser")
    if options.stop_on_stdin_eof:
        cmd.append("--stop-on-stdin-eof")
    process = subprocess.Popen(cmd, env=child_env(work), cwd=work)
    try:
        return process.wait()
    except KeyboardInterrupt:
        return process.wait()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (EOFError, OSError, ValueError, subprocess.CalledProcessError) as exc:
        print("Pilot:", exc, file=sys.stderr)
        raise SystemExit(1)
