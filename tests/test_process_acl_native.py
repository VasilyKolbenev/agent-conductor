"""One controlled Windows child exercises the owned ACL door and its cleanup."""
import os

import pytest

from conductor import ownership, ownership_transition
from conductor.command.adapters.process import CommandSpec, ProcessRunner


def test_owned_appcontainer_attempt_can_write_work_but_not_source_or_git(tmp_path):
    if os.name != "nt":
        pytest.skip("native AppContainer ACL witness requires Windows")
    from tests import os_boundary_windows as ac
    from tests.os_boundary_box import WITHOUT_CMDLETS, base_environment

    source = tmp_path / "source.txt"
    source.write_text("owner", encoding="utf-8")
    git = tmp_path / ".git"
    git.mkdir()
    index = git / "index"
    index.write_text("index", encoding="utf-8")
    (tmp_path / "conductor").mkdir()
    ownership_transition.activate(tmp_path, legacy_writers_stopped=True)

    with ownership.acquire_owner(tmp_path):
        runner = ProcessRunner(tmp_path)
        with runner.container_profile(mode="dispatch") as (boundary, paths):
            root = str(tmp_path).replace("'", "''")
            script = (WITHOUT_CMDLETS
                + "[IO.File]::WriteAllText('owned.txt','yes'); "
                + f"try {{ [IO.File]::WriteAllText('{root}\\source.txt','bad'); "
                + "[Console]::Out.Write('source-writable;') } "
                + "catch { [Console]::Out.Write('source-denied;') }; "
                + f"try {{ [IO.File]::WriteAllText('{root}\\.git\\index','bad'); "
                + "[Console]::Out.Write('git-writable') } "
                + "catch { [Console]::Out.Write('git-denied') }")
            spec = CommandSpec((str(ac.POWERSHELL), "-NoProfile", "-NonInteractive",
                                "-Command", script),
                               str(paths["work"].relative_to(tmp_path)),
                               env=base_environment(paths["runtime"]), boundary=boundary,
                               timeout_seconds=20)
            result = runner.run(spec)
            assert result.status == "completed" and result.exit_code == 0
            assert result.output == b"source-denied;git-denied"
            assert (paths["work"] / "owned.txt").read_text() == "yes"
        assert not paths["parent"].exists()
    assert source.read_text(encoding="utf-8") == "owner"
    assert index.read_text(encoding="utf-8") == "index"
