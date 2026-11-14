"""One offline Windows Do with the real 0.164.0 stdin patcher and fixed inference replies."""
from contextlib import contextmanager
import hashlib
import shutil
from types import SimpleNamespace

from conductor import ownership
from conductor.command import operator_config
from conductor.command.adapters.codex_cli import CODEX_PROTOCOL
from conductor.command.adapters.provider import ProviderConfig
from tests.test_codex_native_compat import _site, verified_exe  # noqa: F401 -- opt-in fixture
from tests.test_patch_do_policy import ACTUAL, PATCH, REGRESSION, one_grant, work_and_calls


def _hash(path):
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def test_offline_native_patch_and_independent_check(tmp_path, verified_exe):
    from conductor.command.adapters import _winlaunch

    destination = tmp_path / "harnesses" / "codex" / "0.164.0" / "vendor"
    vendor = verified_exe.parent.parent
    shutil.copytree(vendor, destination)
    for source in vendor.rglob("*"):
        if source.is_file():
            assert _hash(source) == _hash(destination / source.relative_to(vendor))
    binary = destination / "bin" / "codex.exe"
    root, login, adapter = _site(tmp_path, binary, True)
    runner = adapter._runner
    open_profile = runner.container_profile
    entries = []

    @contextmanager
    def offline(**kwargs):
        with open_profile(**{**kwargs, "internet_client": False}) as (boundary, paths):
            assert not boundary.internet_client
            entries.append((boundary.sid, paths["parent"]))
            yield boundary, paths
    runner.container_profile = offline
    with ownership.acquire_owner(root):
        config = ProviderConfig(provider_id="codex", executable=str(binary),
                                protocol=CODEX_PROTOCOL,
                                env_allow=("SystemRoot", "windir"), auth="subscription",
                                auth_home=str(login))
        operator_config.save_provider_configs(
            operator_config.provider_config_path(ownership.data_root(root)), [config],
            project_root=root)
        site = SimpleNamespace(root=root, adapter=adapter)
        work, calls = work_and_calls(site, PATCH, use_native=True)
        get, request = one_grant(site)
        receipt, = get("action_result")
        assert receipt.outcome == "succeeded", receipt.detail
        assert (work / "count.py").read_bytes() == ACTUAL
        assert (work / "test_count.py").read_bytes() == REGRESSION
        assert [p.verifier_instance_id for p in get("evidence")] == ["checker"]
        assert adapter.execute(adapter.prepare(request)).outcome == "unknown"
        assert calls == ["prepare", "apply", "check"]
    assert entries and not runner.active_tokens()
    assert all(_winlaunch.inspect_profile(sid) is None and not path.exists()
               for sid, path in entries)
