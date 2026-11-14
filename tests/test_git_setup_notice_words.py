"""The words of the shared notice that a branch already holds a commit the operation cannot accept.

`git_setup.reason.head_exists` is one sentence for every road that ends in that refusal: a plain
confirm, a wait for a signature, a retry after a restart. It is read by the old panel and by the
desk's wizard alike. What the operation can say for certain is only that the commit on the branch
is not one it can accept: it cannot say who made it, and it must not call it a first commit as if
the step had worked. What the person does next is said by the desk's own next-step lines.
"""
from __future__ import annotations

import json
import re

from tests.desk_node import run_js

MODULES = {"i18n": "studio-i18n.js"}
KEY = "git_setup.reason.head_exists"


def _said() -> dict[str, str]:
    return run_js(f"console.log(JSON.stringify(i18n.MESSAGES[{json.dumps(KEY)}]));", MODULES)


def test_the_head_exists_notice_says_the_branch_holds_a_commit_this_operation_cannot_accept():
    said = _said()
    assert said["en"] == "The branch already holds a commit this operation cannot accept."
    assert said["ru"] == "Ветка уже содержит коммит, который эта операция не может принять."


def test_the_head_exists_notice_does_not_say_who_made_the_commit_or_that_it_is_the_first_one():
    said = _said()
    assert re.search(r"product|first|made|created", said["en"], re.IGNORECASE) is None, said["en"]
    assert re.search(r"продукт|перв|сделал|создал", said["ru"], re.IGNORECASE) is None, said["ru"]
