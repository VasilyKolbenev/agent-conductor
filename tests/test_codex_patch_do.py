"""The versioned Do profile admits only a bounded, named patch against its own task."""
import pytest

from conductor.command.adapters.deep_commands import DeepDispatchArgs


PROFILE = "implement-patch-v1"
PATCH = b"*** Begin Patch\n*** Update File: src/count.py\n@@\n-old\n+new\n*** End Patch\n"


def test_patch_profile_round_trips_and_keeps_older_arguments_distinct():
    args = dict(work_item_id="item", instruction_ref="brief", profile=PROFILE,
                artifact_refs=[], output_limit_profile="normal", work_scope="task")
    assert DeepDispatchArgs.from_dict(args).as_dict() == args
    old = {**args, "profile": "implement"}
    assert DeepDispatchArgs.from_dict(old).as_dict() == old


def test_stage_names_replace_only_validated_headers(tmp_path):
    from conductor.command.adapters.codex_patch import parse_patch

    ops = parse_patch(PATCH)
    assert [(op.kind, op.name) for op in ops] == [("Update", "src/count.py")]
    framed = ops[0].for_stage(tmp_path / "f0")
    assert framed == "*** Update File: " + (tmp_path / "f0").as_posix() + "\n@@\n-old\n+new"


@pytest.mark.parametrize("bad", [
    PATCH.replace(b"src/count.py", b"../elsewhere"),
    PATCH.replace(b"src/count.py", b".git/config"),
    PATCH.replace(b"src/count.py", b"bad:stream"),
    PATCH.replace(b"@@", b"*** Move to: escaped"),
    PATCH.replace(b"*** End Patch", b"*** Delete File: SRC/COUNT.PY\n*** End Patch"),
    b"comment\n" + PATCH, PATCH + b"comment", PATCH.replace(b"+new", b"*** Arbitrary"),
])
def test_untrusted_patch_is_refused_before_any_write(bad):
    from conductor.command.adapters.codex_patch import PatchRefused, parse_patch

    with pytest.raises(PatchRefused):
        parse_patch(bad)


def test_partial_publication_restores_the_first_file_on_failure(tmp_path, monkeypatch):
    from time import monotonic
    from conductor.command.adapters import patch_publish
    from tests.relay_roads import CODEX, Site

    site = Site(tmp_path, CODEX)
    workspace = site.adapter._workspace
    args = DeepDispatchArgs.from_dict(dict(work_item_id="item", instruction_ref="brief",
        profile=PROFILE, artifact_refs=[], output_limit_profile="normal", work_scope="one"))
    with site.owned():
        work = workspace.work_dir("item", "one")
        for name in ("first", "second"):
            (work / name).write_bytes(b"before")
        originals = {n: patch_publish.file_image(workspace, args, n)[1]
                     for n in ("first", "second")}
        changes = {n: (mode, b"after") for n, (mode, _) in originals.items()}
        write = patch_publish._change
        def fail_second(ws, arguments, name, expected, desired):
            if name == "second":
                assert (work / "first").read_bytes() == b"after"
                raise OSError("fixture publication error")
            write(ws, arguments, name, expected, desired)
        monkeypatch.setattr(patch_publish, "_change", fail_second)
        with pytest.raises(patch_publish.PatchRefused, match="no proposed changes remain"):
            patch_publish.publish(workspace, args, originals, changes, monotonic() + 30)
        assert {p.name: p.read_bytes() for p in work.iterdir()} == {
            "first": b"before", "second": b"before"}


def test_deadline_stops_even_after_the_last_publication(tmp_path, monkeypatch):
    from conductor.command.adapters import patch_publish
    from tests.relay_roads import CODEX, Site

    site = Site(tmp_path, CODEX)
    ws = site.adapter._workspace
    args = DeepDispatchArgs("item", "brief", PROFILE, [], "normal", work_scope="one")
    with site.owned():
        file = ws.work_dir("item", "one") / "count.py"
        file.write_bytes(b"before")
        before = patch_publish.file_image(ws, args, file.name)[1]
        ticks = iter((1, 2))
        def remaining(_deadline):
            if next(ticks) == 2:
                assert file.read_bytes() == b"after"
                raise patch_publish.PatchRefused("deadline")
        monkeypatch.setattr(patch_publish, "remaining", remaining)
        with pytest.raises(patch_publish.PatchRefused):
            patch_publish.publish(ws, args, {file.name: before},
                                  {file.name: (before[0], b"after")}, 1)
        assert file.read_bytes() == b"before"


def test_failed_deletion_preserves_original_file_identity(tmp_path, monkeypatch):
    from time import monotonic
    from conductor.command.adapters import patch_publish
    from tests.relay_roads import CODEX, Site

    site = Site(tmp_path, CODEX)
    ws = site.adapter._workspace
    args = DeepDispatchArgs("item", "brief", PROFILE, [], "normal", work_scope="one")
    with site.owned():
        work = ws.work_dir("item", "one")
        file = work / "remove.py"
        file.write_bytes(b"before")
        before = patch_publish.file_image(ws, args, file.name)[1]
        # File identity distinguishes restoring the metadata from recreating the same bytes.
        original = file.stat().st_ino
        def fail_after_delete(_):
            if not file.exists():
                raise patch_publish.PatchRefused("deadline")
        monkeypatch.setattr(patch_publish, "remaining", fail_after_delete)
        with pytest.raises(patch_publish.PatchRefused, match="no proposed changes remain"):
            patch_publish.publish(ws, args, {file.name: before}, {file.name: None},
                                  monotonic() + 30)
        assert list(work.iterdir()) == [file] and file.read_bytes() == b"before"
        assert file.stat().st_ino == original


def test_a_hard_link_to_another_file_is_not_an_admissible_target(tmp_path):
    import os
    from conductor.command.adapters.codex_patch import file_image
    from conductor.command.adapters.harness_workspace import WorkspaceNotContained
    from tests.relay_roads import CODEX, Site

    site = Site(tmp_path, CODEX)
    ws = site.adapter._workspace
    args = DeepDispatchArgs("item", "brief", PROFILE, [], "normal", work_scope="one")
    outside = tmp_path / "external-source"
    outside.write_bytes(b"external")
    with site.owned():
        work = ws.work_dir("item", "one")
        os.link(outside, work / "linked.py")
        with pytest.raises(WorkspaceNotContained):
            file_image(ws, args, "linked.py")
        assert outside.read_bytes() == b"external"


def test_swap_preserves_a_files_distinct_windows_dacl(tmp_path):
    import os
    import subprocess
    if os.name != "nt":
        pytest.skip("Windows DACL")
    from conductor import atomic_replace
    from conductor.command.adapters import _winlaunch
    from conductor.ownership_native import NativeHold
    from tests.test_process_loans_native import same_acl

    def acl(path):
        hold = NativeHold(path)
        try:
            return _winlaunch.acl_snapshot(hold)
        finally:
            hold.close()

    file = tmp_path / "restricted.txt"
    file.write_bytes(b"before")
    subprocess.run(["icacls", str(file), "/inheritance:d"], capture_output=True, check=True)
    prior = acl(file)
    other = tmp_path / "stage"
    other.write_bytes(b"after")
    assert not same_acl(acl(other), prior)
    atomic_replace.replace_existing(other, file)
    assert file.read_bytes() == b"after" and same_acl(acl(file), prior)
