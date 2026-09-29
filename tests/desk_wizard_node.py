"""Run the real wizard modules under Node and read what they answer back as JSON.

The wizard's model is pure: state in, state out, asks as values. So its tests
import the packaged module itself with `node --input-type=module`, hand it JSON
as data and print the answer as JSON -- the pattern `tests/test_studio_automation.py`
uses for the automation model. The script goes in on stdin, not on the command
line, because a flow fixture is several kilobytes and a Windows command line is
not.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

PANEL = Path(__file__).resolve().parents[1] / "src" / "conductor" / "panel"
FIXTURES = Path(__file__).resolve().parent / "fixtures"
MODEL = "desk-wizard-model.js"

#: A wizard opened on a fresh task, and the few helpers every model test shares: `run` folds
#: events through the reducer, `typed` fills step 1, `started` moves to step 2, `opened` asks
#: for the reads, `reply` answers one of the asks the state wants, `show` prints JSON, `land`
#: answers the outstanding flow ask with one payload and then the write that answer made due
#: (a cycle's expectation is read before its first write).
PRELUDE = """
const open = (over = {}) => wiz.initialWizard(
  {starterId: null, viewMode: false, newTaskId: "task-t1", ...over});
const run = (state, ...events) => events.reduce((now, one) => wiz.reduceWizard(now, one), state);
const typed = (over = {}) => run(open(over),
  {type: "edit-title", value: "Fix login"}, {type: "edit-brief", value: "Make it work."});
const started = (over = {}) => run(typed(over), {type: "next"});
const opened = (state = started()) => wiz.stepWizard(state, {type: "open"}).state;
const askOf = (state, name, subject) => wiz.wantedAsks(state)
  .find((ask) => ask.name === name && (subject === undefined || ask.subject === subject));
const reply = (state, name, payload, over = {}) => wiz.reduceWizard(state, {type: "answered",
  ask: askOf(state, name, over.subject),
  result: {status: over.status ?? "accepted", code: over.code, payload}});
const show = (value) => console.log(JSON.stringify(value));
const flowAsk = (state) => wiz.wantedAsks(state).find(
  (ask) => ask.name === "flow" || ask.name === "flow_read");
const landAsk = (state, ask, payload) => wiz.reduceWizard(state, {type: "answered", ask,
  result: {status: "accepted", payload}});
const land = (state, payload) => {
  const first = flowAsk(state), next = landAsk(state, first, payload), then = flowAsk(next);
  return then && then.id !== first.id ? landAsk(next, then, payload) : next;
};
"""


def fixture(*parts: str) -> Any:
    """One JSON fixture under `tests/fixtures/`, parsed."""
    return json.loads(FIXTURES.joinpath(*parts).read_text(encoding="utf-8"))


def run_js(body: str, data: Any = None, modules: dict[str, str] | None = None) -> Any:
    """Evaluate `body` next to the wizard's modules and return its printed JSON.

    Args:
        body: JavaScript that prints one JSON value with `console.log`.
        data: A JSON-serializable value, visible to `body` as the constant `d`.
        modules: Alias to packaged file name; defaults to `wiz` for the model.

    Returns:
        The parsed JSON the script printed.
    """
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is needed to run the real wizard modules")
    wanted = modules or {"wiz": MODEL}
    imports = "\n".join(f"import * as {alias} from {json.dumps((PANEL / name).as_uri())};"
                        for alias, name in wanted.items())
    source = f"{imports}\nconst d = {json.dumps(data)};\n{body}\n"
    result = subprocess.run([node, "--input-type=module"], input=source, capture_output=True,
                            text=True, encoding="utf-8", timeout=30, check=False)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)
