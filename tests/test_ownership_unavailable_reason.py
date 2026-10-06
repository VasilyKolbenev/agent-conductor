"""When the OS boot cannot be measured nothing opens, and every surface says why.

A review ruling accepted the refusal: no owner session and no login lease is opened when the boot
counter cannot be read, and there is no fallback to the old string or to a clock. The refusal is
only as good as its reason: a person who sees "the ownership state cannot be read" cannot tell that
it is the OS boot counter that is unreadable. Each surface that shows the code is witnessed here:
the writer commands, `conduct up`, the shared login lease, and the hub's words in both languages.
The hub receives only the closed code (the child writes the sentence to its own log), so its words
name the two conditions the code stands for.
"""
from __future__ import annotations

import json
import os

import pytest

from conductor import __main__ as cli, ownership, ownership_boot, ownership_login, server
from conductor import ownership_records as records
from conductor.boot_witness import BootRefused
from conductor.command.adapters.process import OwnershipError, ProcessRunner
from tests._boot_world import counter, measure
from tests._drain_harness import DrainProject
from tests.test_command_task_store import durable_bytes
from tests.test_hub_copy import js
from tests.test_project_ownership import activated

READER_CODES = ("native_unavailable", "layout_unknown", "partial_read", "value_empty",
                "counter_overflow")
SENTENCE = "the shared page is not the documented layout of this build"


def unreadable(code="layout_unknown"):
    def reader():
        raise BootRefused(code, SENTENCE)
    return reader


@pytest.mark.parametrize("code", READER_CODES)
def test_a_writer_command_says_which_reader_refusal_stopped_the_owner_session(
        tmp_path, capsys, monkeypatch, code):
    activated(tmp_path)
    measure(monkeypatch, unreadable(code))
    before = durable_bytes(tmp_path / "conductor.v3")
    assert cli.main(["integration-smoke", "--dir", str(tmp_path)]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith("ownership_unavailable: ")
    assert f"{code}: {SENTENCE}" in captured.err and "no owner session is opened" in captured.err
    assert records.chain(tmp_path)["phase"] == "active"
    assert durable_bytes(tmp_path / "conductor.v3") == before


def test_up_refuses_on_one_line_that_names_the_reader_refusal_and_keeps_the_closed_code(
        tmp_path, capsys, monkeypatch):
    project = DrainProject.build(tmp_path)
    monkeypatch.setenv("CONDUCT_HOME", str(project.home))
    monkeypatch.setattr("conductor.server.build", _build_that_must_refuse(server.build))
    measure(monkeypatch, unreadable("partial_read"))
    argv = ["up", "--dir", str(project.root), "--port", "0", "--project-id", project.project_id,
            "--hub-origin", "http://127.0.0.1:7700", "--status-file", str(project.status_file),
            "--stop-on-stdin-eof"]
    assert cli.main(argv) == 1
    err = capsys.readouterr().err
    assert len(err.splitlines()) == 1
    assert err.startswith("conduct up: refused ownership_unavailable: ")
    assert f"partial_read: {SENTENCE}" in err
    written = json.loads(project.status_file.read_text(encoding="utf-8"))
    assert written["state"] == "refused" and written["code"] == "ownership_unavailable"
    assert project.head_phase() == "active"


def _build_that_must_refuse(real):
    """The real build, which opens the owner first; a build that succeeds fails the test."""
    def build(*args, **kwargs):
        built = real(*args, **kwargs)
        built.server_close()
        raise AssertionError("the server was built although the owner could not be opened")
    return build


def test_a_login_lease_says_which_reader_refusal_stopped_it_and_opens_nothing(
        tmp_path, monkeypatch):
    project, home = tmp_path / "project", tmp_path / "login"
    project.mkdir()
    home.mkdir()
    activated(project)
    measure(monkeypatch, counter(42))
    with ownership.acquire_owner(project):
        measure(monkeypatch, unreadable("value_empty"))
        with pytest.raises(OwnershipError) as caught:
            with ProcessRunner.login_write_guard(project, str(home)):
                raise AssertionError("the login lease opened without a boot")
        _, box = ownership_login._route(str(home))
        assert not (box / "active.json").exists()
    message = str(caught.value)
    assert "ownership_unavailable" in message and "shared login lease" in message
    assert f"value_empty: {SENTENCE}" in message


@pytest.mark.skipif(os.name != "nt", reason="the counter reader is the Windows boot source")
def test_an_unreadable_counter_is_never_replaced_by_the_old_string_on_windows(monkeypatch):
    from conductor import boot_kuser, ownership_native
    monkeypatch.setattr(boot_kuser, "current_witness", unreadable("layout_unknown"))
    asked = []
    monkeypatch.setattr(ownership_native, "boot_identity", lambda: asked.append("old") or "x")
    with pytest.raises(ownership.OwnerRefused) as caught:
        ownership_boot.measured("owner session")
    assert caught.value.code == "ownership_unavailable" and asked == []
    assert f"layout_unknown: {SENTENCE}" in caught.value.detail


@pytest.mark.parametrize("locale, index", [("en", 0), ("ru", 1)])
def test_the_hub_words_for_the_code_name_the_boot_counter_as_one_of_the_reasons(locale, index):
    rows = js("show(copy.HUB_COPY);")
    clause = rows["hub.code.ownership_unavailable"][index]
    other = rows["hub.code.transition_conflict"][index]
    named = {"en": ("boot counter", "ownership state"),
             "ru": ("счётчик загрузки", "состояние владения")}[locale]
    assert all(part in clause for part in named), clause
    assert clause != other, "the two codes must not be said with one sentence"
    said = js(f'show(copy.codeWords("{locale}", "ownership_unavailable"));')
    assert said == clause
