"""A failed git read can say why the tool was not usable (spec 9.3, 9.5).

The refusal a desk route will throw for an unusable tool (`tool_unavailable`, 503) has to name
the reason (`not_pinned`, `version_changed`, `missing`) without the route reading an attribute
through `getattr`: the base class of every failed read carries an optional `reason`. A failure
of any other kind has none, and the two positional arguments every caller already passes do not
move.
"""
from __future__ import annotations

import pytest

from conductor import server_git
from conductor.command.project_git import GitReadFailed


def test_a_git_read_failure_has_no_reason_unless_one_is_given():
    failed = GitReadFailed("git_failed", 1)
    assert (failed.code, failed.exit_code, failed.reason) == ("git_failed", 1, None)
    assert str(failed) == "git_failed"


def test_a_git_read_failure_carries_the_reason_it_was_given():
    failed = GitReadFailed("tool_unavailable", reason="version_changed")
    assert (failed.code, failed.exit_code, failed.reason) == (
        "tool_unavailable", None, "version_changed")


@pytest.mark.parametrize("reason", server_git.REASONS)
def test_the_unavailable_tool_failure_keeps_its_reason_and_is_a_git_read_failure(reason):
    failed = server_git.ToolUnavailable(reason)
    assert isinstance(failed, GitReadFailed)
    assert (failed.code, failed.exit_code, failed.reason) == ("tool_unavailable", None, reason)
