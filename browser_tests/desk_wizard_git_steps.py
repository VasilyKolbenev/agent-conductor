"""The steps every browser module of the wizard's git block shares.

Not a test module (pytest does not collect it). `at_materials` installs the route with a memory
(`desk_wizard_git_server.py`) in front of the bench host and opens the wizard on step 2; the rest
are the small things a test says again and again about what is on the page.
"""
from __future__ import annotations

from typing import Any

from playwright.sync_api import expect

from browser_tests.desk_wizard_bench import Bench, to_step
from browser_tests.desk_wizard_git_server import GitWorld


def at_materials(bench: Bench, lang: str, start: str = "git_unborn", *, actor: str = "Anna",
                 starter: str | None = None, view: bool = False, setup_door: bool = True,
                 **options: Any) -> GitWorld:
    """Install the route, open the wizard on step 2, wait for the git read, return the world.

    `setup_door` is what the real host says about its transport: whether the target the setup
    route is reached by is there. The bench host says nothing, which the model reads as there."""
    world = GitWorld.install(bench, start, **options)
    opening = {"actor": actor, **({} if setup_door else {"setupDoor": False})}
    to_step(bench, lang, "materials", starter=starter, view=view, opening=opening)
    expect(bench.page.locator("[data-git-state]")).not_to_have_attribute("data-git-state",
                                                                         "reading")
    return world


def set_door(bench: Bench, open_: bool) -> None:
    """The desk's own switch is a literal in the product, copied into the slice once at the
    opening, so a test that cares which way it stands sets the copy and redraws. No test depends
    on what the shipped literal is, which keeps the day it is flipped a one-literal change."""
    bench.page.evaluate("""(open) => {
      const wizard = window.host.state.wizard;
      window.host.state = {...window.host.state,
        wizard: {...wizard, git: {...wizard.git, open}}};
    }""", open_)
    bench.dispatch(type="close-cancel")


def open_door(bench: Bench) -> None:
    set_door(bench, True)


def close_door(bench: Bench) -> None:
    set_door(bench, False)


def to_preview(bench: Bench, mode: str = "snapshot") -> None:
    """Open the first-commit panel and prepare the preview for `mode`."""
    bench.control("wizard:git:first_commit").click()
    if mode != "snapshot":
        bench.control(f"wizard:git:mode:{mode}").click()
    bench.control("wizard:git:preview").click()
    expect(bench.page.locator("[data-git-preview]")).to_have_attribute("data-git-preview", mode)


def result(bench: Bench):
    return bench.page.locator("[data-git-result]")


def writes(world: GitWorld) -> list[str]:
    return [post["name"] for post in world.posts()]


def write_asks(bench: Bench) -> list[str]:
    """The ids of the write asks the model made, whether or not the route has answered them."""
    return [row[0] for row in bench.asks() if row[0].startswith("write:git:")]


def reason_beside(bench: Bench, key: str) -> str:
    """The words written beside a control that is drawn disabled."""
    return bench.page.locator(f'[data-blocked="{key}"] small').inner_text()


def patch_preview(bench: Bench, patch: dict[str, Any]) -> None:
    bench.page.evaluate("(patch) => { window.host.world.preview_patch = patch; }", patch)
