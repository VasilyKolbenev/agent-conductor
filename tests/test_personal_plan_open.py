"""The opt-in editing path addresses the saved pair; regular open stays read-only."""
import json
from unittest.mock import patch

import pytest

from tests.test_pilot_project_paths import CREATE, personal_project


@pytest.mark.parametrize(("action", "mode"), [("edit", "active"), ("open", "view")])
def test_pair_mode_receives_the_saved_task_and_project(action, mode, tmp_path, monkeypatch):
    from runpy import run_path
    from conductor import server, server_drain

    tools = run_path(str(CREATE.with_name("studio.py")))
    with personal_project(False, tmp_path) as root:
        parent = root.parent
        (parent / "tasks.json").write_text(json.dumps({"first": "run-a", "second": "task-b"}))
        observed = []

        def serve(*args, **kwargs):
            observed.append((args[0], kwargs["launch"].mode))
            raise StopIteration

        monkeypatch.setattr(server, "build", serve)
        monkeypatch.setattr(server_drain, "enable_ctrl_c", lambda: None)
        with patch("sys.argv", ["studio.py", action, str(parent), "--no-browser"]):
            with pytest.raises(StopIteration):
                tools["main"]()
        assert observed == [(parent / "project", mode)]
