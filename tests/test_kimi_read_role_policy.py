"""Probe the tool-call guard shipped in the exact CLI without a prompt or a tool execution."""
import hashlib
import json
import os
import shutil
import subprocess
import tomllib
from zipfile import ZipFile

import pytest

from tests.test_kimi_session_state_native import EXE_SHA, READ_ROLE_POLICY, native_files


def region(binary, name):
    marker = b"//#region ../../packages/agent-core-v2/src/agent/toolPolicy/" + name + b".ts\n"
    assert binary.count(marker) == 1
    start = binary.index(marker) + len(marker)
    end = binary.index(b"//#endregion", start)
    return binary[start:end].decode("utf-8")


@pytest.mark.skipif(os.name != "nt", reason="the pinned CLI is the Windows release")
def test_shipped_guard_allows_only_read_from_the_fixed_global_config(native_files, tmp_path):
    node = shutil.which("node")
    if node is None:
        pytest.skip("set PATH to a local Node runtime for the offline policy witness")
    archive, _ = native_files
    with ZipFile(archive) as vendor:
        binary = vendor.read("kimi.exe")
    assert hashlib.sha256(binary).hexdigest() == EXE_SHA
    evaluator = region(binary, b"evaluate").partition("function resolveActiveToolNames")[0]
    service = region(binary, b"toolPolicyService")
    start = service.index("class AgentToolPolicyService extends Disposable")
    end = service.index("AgentToolPolicyService = __decorate", start)
    constructor = service[start:end].strip()
    # The runtime guard registers itself against the supplied executor.
    js = """
const TOOLS_SECTION = "tools";
class Disposable { _register(value) { return value; } }
""" + evaluator + constructor + """
function decisions(tools) {
    let guard;
    const scope = new AgentToolPolicyService(
        {data: () => ({})}, {get: name => { if (name === "tools") return tools; }},
        {disabledTools: () => []}, {disabledTools: []},
        {registerToolCallGuard: callback => { guard = callback; }});
    return Object.fromEntries(names.map(name => [name, guard({name, source: "builtin"}) ?? null]));
}
"""
    config = tomllib.loads(READ_ROLE_POLICY)["tools"]
    names = ["Read", "Bash", "Write", "Edit", "Agent", "select_tools"]
    js += ("const names = " + json.dumps(names) + ";\n"
           "console.log(JSON.stringify([decisions(" + json.dumps(config) + "), decisions({})]));")
    proc = subprocess.run(
        [node, "--permission", "--no-warnings", "-"], input=js.encode(), cwd=tmp_path,
        env={k: os.environ[k] for k in ("SystemRoot", "WINDIR") if k in os.environ},
        check=True, capture_output=True, timeout=10)
    restricted, unrestricted = json.loads(proc.stdout)
    assert unrestricted == dict.fromkeys(names)
    assert restricted["Read"] is None
    assert {n: restricted[n] for n in names[1:]} == {
        n: f'Tool "{n}" is disabled by the active tool policy' for n in names[1:]}
