"""Fix M through real spawns: one Claude adapter's quota read and its task differ by one switch.

Codex ruling (CODEX-REVIEW-OPUS-LIVE-2026-09-23.md): the quota control spawn, and only it, runs without
CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC; DISABLE_AUTOUPDATER and every task spawn keep the profile.
"""
import json

from conductor.command.adapters.claude_code import (
    CLAUDE_AUTOUPDATER_ENV, CLAUDE_NONESSENTIAL_ENV, CONTROL_QUOTA_RPC)
from tests import _fakeclaude
from tests.test_claude_quota import LIMITS, transcript
from tests.test_command_claude_transport import a_harness, a_request, run_once

FORCED = {CLAUDE_AUTOUPDATER_ENV: "1", CLAUDE_NONESSENTIAL_ENV: "1"}


def _harness(tmp_path, **knobs):
    login = tmp_path / "login"
    login.mkdir()
    cache = {"fetchedAtMs": 1790000000000, "utilization": LIMITS}
    adapter, root, log = a_harness(tmp_path, auth="subscription", auth_home=str(login), **{
        _fakeclaude.EMIT_HEX: transcript().hex(),
        _fakeclaude.HOME_FILE: ".claude.json:" + json.dumps({"cachedUsageUtilization": cache}),
        **knobs})
    return adapter, log, login, cache


def test_a_real_quota_read_and_a_real_task_of_one_adapter_differ_only_by_the_nonessential_switch(tmp_path):
    adapter, log, login, cache = _harness(tmp_path)
    sample = adapter.quota_connection().read()
    assert sample.observed_at_ms == cache["fetchedAtMs"]
    run_once(adapter, a_request())
    rows = _fakeclaude.spawns(log)
    control = [row for row in rows if "stream-json" in row["argv"]]
    others = [row for row in rows if "stream-json" not in row["argv"]]
    assert len(control) == 1
    assert control[0]["switches"] == {CLAUDE_AUTOUPDATER_ENV: "1", CLAUDE_NONESSENTIAL_ENV: None}
    assert CLAUDE_NONESSENTIAL_ENV not in control[0]["env_names"]
    assert control[0]["claude_home"] == str(login)
    assert len(others) >= 3 and all(row["switches"] == FORCED for row in others)
    assert _fakeclaude.prompt_spawns(log), "the task prompt spawn must be among the rows that keep both"


def test_an_allowed_operator_value_cannot_bring_the_switch_back_into_the_control_spawn(tmp_path):
    """Through a real Popen at the attempt level.

    A whole read() cannot show this: once the operator allows the name, the forced "1" becomes a
    scanned value, and the version print ("2.1.239 ...") trips the leak scan before the control spawn
    runs. That predates fix M; the drop itself is what this proves.
    """
    adapter, log, _login, _cache = _harness(tmp_path, **{CLAUDE_NONESSENTIAL_ENV: "operator-value"})
    adapter._workspace.work_root()
    adapter._attempt(CONTROL_QUOTA_RPC.argv, "work", timeout=15, stdin_bytes=CONTROL_QUOTA_RPC.payload,
                     separate_stderr=True, unset_env=CONTROL_QUOTA_RPC.unset_env)
    row = _fakeclaude.spawns(log)[-1]
    assert row["switches"] == {CLAUDE_AUTOUPDATER_ENV: "1", CLAUDE_NONESSENTIAL_ENV: None}
    assert CLAUDE_NONESSENTIAL_ENV not in row["env_names"]
