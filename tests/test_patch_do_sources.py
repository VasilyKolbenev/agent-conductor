"""A real bounded Do request at the Codex stdin boundary, with no model."""
import hashlib
import json
import os

import pytest

from conductor.command.artifacts import ArtifactDocument
from tests.relay_roads import CODEX, Site
from tests.test_patch_do_policy import NOW, one_grant, reply


def doc(ref, text):
    return ArtifactDocument("doc-" + ref, ref, "run", NOW, "text/plain", text)


BRIEF = ("Исправь runstats/counts.py: проверь `tests/test_counts.py`. "
         "Добавь регрессию. Не используй ../private.py и /private.py.")
SOURCES = {"runstats/counts.py": "def count_succeeded(rows):\r\n    return len(rows)\r\n",
           "tests/test_counts.py": "# Исходный тест\nassert count_succeeded([]) == 0\n"}


def test_patch_preparation_receives_only_named_current_task_sources(tmp_path):
    site = Site(tmp_path, CODEX)
    seen = []
    with site.owned():
        work = site.adapter._workspace.work_dir("item", "one")
        other = site.adapter._workspace.work_dir("item", "two")
        for name, content in SOURCES.items():
            f = work / name
            f.parent.mkdir()
            f.write_bytes(content.encode())
            neighbor = other / name
            neighbor.parent.mkdir()
            neighbor.write_bytes(b"SIBLING-CANARY")
        (work / "extra.py").write_bytes(b"PLAN-ONLY-CANARY")
        (work / "private.py").write_bytes(b"UNREQUESTED-CANARY")
        original = site.runner.run

        def capture(spec):
            if "doer-model" not in spec.argv:
                return original(spec)
            assert spec.boundary and "read-only" in spec.argv
            seen.append(spec.stdin_bytes)
            return reply(b"", code=1)  # The assertion concerns the input, before any patch.

        site.runner.run = capture
        chosen = [*SOURCES, "tests/new.py"]
        instruction = "Prepare a patch.\n\nconduct.patch-sources.v1\n" + json.dumps(chosen)
        docs = (doc("artifact-brief", BRIEF), doc("artifact-plan", "Inspect extra.py."))
        one_grant(site, instruction=instruction, documents=docs)
    payload, = seen
    files = [json.loads(line) for line in payload.decode().splitlines()
             if line.startswith('{"path":')]
    assert files[-1] == {"path": "tests/new.py", "state": "absent"}
    assert {f["path"]: f["content"] for f in files[:-1]} == SOURCES
    assert len(files) == len(chosen)
    for f in files[:-1]:
        assert f["sha256"] == hashlib.sha256(SOURCES[f["path"]].encode()).hexdigest()
    assert b"CANARY" not in payload


@pytest.mark.parametrize("case", ["hard_link", "binary", "oversize", "protected"])
def test_unreadable_named_source_refuses_before_codex_exec(tmp_path, case, monkeypatch):
    site = Site(tmp_path, CODEX)
    with site.owned():
        work = site.adapter._workspace.work_dir("item", "one")
        target = work / "counts.py"
        if case == "hard_link":
            other = tmp_path / "outside.py"
            other.write_bytes(b"OUTSIDE-CANARY")
            os.link(other, target)
        elif case == "binary":
            target.write_bytes(b"hello\x00world")
        elif case == "oversize":
            target.write_bytes(b"x" * (128 * 1024 + 1))
        else:
            target.write_bytes(b"token=protected-example")
            monkeypatch.setattr(site.adapter, "_sensitive_values",
                                lambda *args: (b"protected-example",))
        original = site.runner.run
        calls = []

        def capture(spec):
            if "doer-model" in spec.argv:
                calls.append("prepare")
                return reply(b"", code=1)
            return original(spec)

        site.runner.run = capture
        get, _ = one_grant(site, instruction='Prepare.\n\nconduct.patch-sources.v1\n["counts.py"]',
                           documents=(doc("artifact-brief", "Read counts.py."),))
        assert calls == []
        result, = get("action_result")
        assert result.outcome == "failed" and "source" in result.detail
        assert "CANARY" not in result.detail and "protected-example" not in result.detail


def test_legacy_instruction_and_model_output_do_not_share_sources(tmp_path):
    from conductor.command.adapters.codex_patch_sources import source_section
    marked = "Prepare.\n\nconduct.patch-sources.v1\n[\"counts.py\"]"
    site = Site(tmp_path, CODEX)
    with site.owned():
        ws = site.adapter._workspace
        work = ws.work_dir("item", "one")
        (work / "counts.py").write_bytes(b"UNREVIEWED")
        before = ws.digest_work_tree()
        model = ArtifactDocument("output", "instruction-plan", "run", NOW, "text/plain",
                                 marked, source_action_id="model-action")
        for instruction in (None, doc("instruction-plan", "Open counts.py."), model):
            assert source_section(ws, None, work, before, instruction, lambda: ()) == ""


def test_changed_file_or_an_invalid_source_list_cannot_fall_back_to_a_shell(tmp_path):
    from conductor.command.adapters.codex_patch import PatchRefused
    from conductor.command.adapters.codex_patch_sources import source_section
    from conductor.command.adapters.deep_commands import DeepDispatchArgs
    site = Site(tmp_path, CODEX)
    with site.owned():
        ws = site.adapter._workspace
        work = ws.work_dir("item", "one")
        target = work / "counts.py"
        target.write_bytes(b"old")
        before = ws.digest_work_tree()
        target.write_bytes(b"replacement")
        args = DeepDispatchArgs("item", "brief", "implement-patch-v1", [], "normal",
                                work_scope="one")
        for names, reason in ((["counts.py"], "changed"), (["../counts.py"], "invalid"),
                              ([".codex/auth.json"], "invalid"), (["C:/counts.py"], "invalid")):
            item = doc("instruction-plan", "Do.\n\nconduct.patch-sources.v1\n" + json.dumps(names))
            with pytest.raises(PatchRefused, match=reason):
                source_section(ws, args, work, before, item, lambda: ())
