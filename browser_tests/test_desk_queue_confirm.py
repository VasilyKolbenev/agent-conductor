"""The Pult renews a changed queue entry from the server's reviewed terms (spec 4.4.8)."""
from __future__ import annotations

from pathlib import Path

import pytest

from browser_tests import desk_queue_rig as rig

A, B = "task-a-r1", "task-b-r1"
SEEDS = [rig.Seed(A, "task-a", "Alpha", final_gate=True),
         rig.Seed(B, "task-b", "Bravo")]


def _world(served: rig.Project) -> None:
    rig.hold(served, A, "g-a")
    rig.enqueue(served, B, "g-b")
    rig.publish(served, B, "doc-new")
    assert served.queue()["entries"][0]["state"] == "confirmation_required"


@pytest.mark.parametrize("language, words", [
    ("en", ("Confirm", "Confirm these terms", "Give your name above to confirm this entry.")),
    ("ru", ("Подтвердить", "Подтвердить эти условия",
            "Укажите имя выше, чтобы подтвердить эту запись."))])
def test_a_changed_entry_shows_reviewed_terms_then_keeps_its_place_with_a_new_permission(
        chromium, tmp_path: Path, language, words):
    with rig.project(tmp_path, SEEDS) as served:
        _world(served)
        window = rig.open_desk(chromium, served, language)
        row = window.facts()["entries"][0]
        assert row["state"] == "confirmation_required"
        assert next(button for button in row["buttons"] if button["key"] == f"queue:confirm:{B}")[
            "disabled"] is True
        assert words[2] in window.page.locator(f'[data-run-id="{B}"]').inner_text()
        window.name("vasya")
        window.press(f"queue:confirm:{B}")
        window.page.locator(f'[data-focus-key="queue:confirm:accept:{B}"]')\
            .wait_for(state="visible")
        dialog = window.page.locator('[data-pult-dialog="confirm"]')
        assert words[0] in dialog.inner_text() and words[1] in dialog.inner_text()
        assert "3" in dialog.inner_text()
        assert served.queue()["entries"][0]["state"] == "confirmation_required"
        window.press(f"queue:confirm:accept:{B}")
        served.wait("the renewed entry", lambda: served.queue()["entries"][0]["state"]
                    == "preauthorized")
        window.page.wait_for_function(
            "() => document.querySelector('[data-pult-dialog]') === null")
        puts = [body for path, body in window.posted if path == "/command/queue"]
        assert len(puts) == 1 and puts[0]["run_id"] == B
        assert puts[0]["start"]["authorization_id"] != "g-b"
        assert puts[0]["start"]["supersedes"] is None
        assert puts[0]["start"]["authorized_by"] == "vasya"
        assert served.queue()["entries"][0]["run_id"] == B
        assert window.errors() == []


def test_a_lost_confirmation_is_not_called_success_when_another_window_removed_the_entry(
        chromium, tmp_path: Path):
    with rig.project(tmp_path, SEEDS) as served:
        _world(served)

        def remove_then_lose(route) -> None:
            if route.request.method != "POST":
                route.continue_()
                return
            status, _answer = served.call("POST", f"/command/queue/{B}/withdraw", {})
            assert status == 200
            route.abort()

        window = rig.open_desk(chromium, served, "en", before=lambda page: page.route(
            "**/command/queue", remove_then_lose))
        window.name("vasya")
        window.press(f"queue:confirm:{B}")
        window.press(f"queue:confirm:accept:{B}")
        window.until("the refused readback", lambda: window.facts()["notice"] is not None)
        assert window.facts()["notice"] == (
            "The change could not be confirmed. This is the queue the server holds.")
        assert window.facts()["dialog"] is None
        assert served.queue()["entries"] == []
