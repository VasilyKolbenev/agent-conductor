"""Create and choose a task through Studio's actual form."""
from playwright.sync_api import Page


def create_task(page: Page, title: str = "Same task name") -> str:
    disclosure = page.locator("#studioTasks details").first
    if disclosure.get_attribute("open") is None:
        disclosure.locator("summary").click()
    page.locator('[data-focus="task-title"]').fill(title)
    with page.expect_response(lambda response: response.request.method == "POST"
                              and response.url.endswith("/command/tasks")) as created:
        page.get_by_role("button", name="Create task", exact=True).click()
    assert created.value.status == 201, created.value.json()
    task_id = created.value.json()["task"]["task_id"]
    expect_selected_task(page, task_id)
    page.wait_for_function("() => !document.querySelector('[data-task-notice]')"
                           ".textContent.includes('Reading')")
    if disclosure.get_attribute("open") is not None:
        disclosure.locator("summary").click()
    return task_id


def choose_task(page: Page, task_id: str | None) -> None:
    picker = page.locator('[data-focus="task-picker"]')
    if picker.count():
        picker.select_option(task_id or "")
    else:
        page.locator(f'[data-task-id="{task_id or ""}"]').click()


def selected_task(page: Page) -> str:
    return page.evaluate("""() => {
      const picker = document.querySelector('[data-focus="task-picker"]');
      return picker ? picker.value : document.querySelector('[data-task-id][aria-pressed="true"]').dataset.taskId;
    }""")


def expect_selected_task(page: Page, task_id: str) -> None:
    page.wait_for_function("""id => {
      const picker = document.querySelector('[data-focus="task-picker"]');
      const row = document.querySelector('[data-task-id][aria-pressed="true"]');
      return picker ? picker.value === id : row && row.dataset.taskId === id;
    }""", arg=task_id)
