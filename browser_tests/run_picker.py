"""Choose a run through the same native disclosure a person opens."""
from playwright.sync_api import Page


def reveal_runs(page: Page) -> None:
    picker = page.locator("#bodyRuns .studio-run-picker")
    if picker.get_attribute("open") is None:
        picker.locator("summary").click()


def choose_run(page: Page, run_id: str) -> None:
    reveal_runs(page)
    page.locator(f'[data-focus-key="run:{run_id}"]').click()
