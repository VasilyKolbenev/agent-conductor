"""Focused macOS diagnostic. The release browser gate remains unchanged."""
import json
import os
from pathlib import Path

from browser_tests import gate

root = Path(__file__).resolve().parents[1]
modules = root / "browser_tests"
records = Path(os.environ["RUNNER_TEMP"]) / "editor-repro"
records.mkdir()
gate.probe_versions(records)
target = "test_studio_task_races.py"
reverse = gate.discover_modules(modules, True)
index = [p.name for p in reverse].index(target)
neighbours = reverse[index - 2:index + 1]
for sample in range(1):
    folder = records / f"reverse{sample}"
    folder.mkdir()
    for module in (neighbours if sample == 0 else [modules / target]):
        record = gate.run_module(module, folder, root, gate.MODULE_TIMEOUT_SECONDS)
        print("sample", sample, json.dumps(record), flush=True)
        proof = folder / "module-response.json"
        if proof.exists():
            print("native-one-shot-fault:", proof.read_text(encoding="utf-8"), flush=True)
        if gate.is_red(record):
            raise SystemExit(1)
