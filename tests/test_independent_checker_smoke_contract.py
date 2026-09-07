"""Exercise the opt-in smoke's hidden body without pretending the fake is a vendor."""
import pytest

from tests import _fakeclaude
from tests import test_command_independent_real_smoke as smoke
from tests.test_command_claude_transport import a_harness


@pytest.mark.parametrize("correct", [True, False])
def test_skipped_smoke_body_remains_runnable_and_checks_a_real_transport(
        tmp_path, monkeypatch, correct):
    def install(path, names):
        adapter, root, _ = a_harness(path, **{_fakeclaude.EMIT_VERDICT:
            "enabled-verdict-accept" if correct else "enabled-verdict-reject"})
        return adapter, root

    monkeypatch.setitem(smoke.INSTALLS, "CLAUDE", install)
    monkeypatch.setattr(smoke, "_allowed_names", lambda provider: ())
    monkeypatch.delenv("CONDUCT_CHECKER_MODEL", raising=False)
    recorded = {}
    smoke.test_real_checker_judges_the_file_not_just_the_process_exit(
        tmp_path, monkeypatch, recorded.__setitem__, "CLAUDE", correct)
    assert recorded == {"checker_first_line":
                        "VERDICT: accept" if correct else "VERDICT: reject"}


def test_install_and_key_alone_never_opt_the_owner_into_paid_checking(monkeypatch):
    monkeypatch.delenv("CONDUCT_CLAUDE_REAL_CHECKER", raising=False)
    monkeypatch.setenv("CONDUCT_CLAUDE_KEY_NAME", "SMOKE_PRIVATE_KEY")
    monkeypatch.setenv("SMOKE_PRIVATE_KEY", "not-a-real-credential")
    with pytest.raises(pytest.skip.Exception, match="not opted in"):
        smoke._allowed_names("CLAUDE")
