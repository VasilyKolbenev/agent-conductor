"""What a confined child can do to a vendor's executable configuration in an OPEN login loan.

A CHARACTERISATION of the first review round's finding, not a property the product wants. The gate
of the leased login home is closed as shipped (`test_process_login_closed.py`); here it is opened
on a THROWAWAY home, in a real AppContainer, to measure what the rights of a credential refresh
leave writable: every name the harness profiles declare as vendor configuration can be created in
the home, the files a vendor keeps beside its own login and an operator's own nested object can be
rewritten in place, and all of it stays after the return takes the profile's entries away. A
present object whose inheritance is cut (the way the loan already treats Grok's two hook objects)
stays untouched whatever its name. When a variant that narrows the grant lands, the first two
tests fail and are replaced by their opposite: that is what they are for.
"""
from __future__ import annotations

import os

import pytest

from conductor.command.adapters.claude_code import CLAUDE_PROFILE
from conductor.command.adapters.codex_cli import CODEX_PROFILE
from conductor.command.adapters.grok_build import GROK_PROFILE
from conductor.command.adapters.kimi_code import KIMI_PROFILE
from tests._ps1 import describe
from tests.login_gate import login_loan_open_module  # noqa: F401 -- a fixture
from tests.test_process_loans_native import entries_naming
from tests.test_process_login_native import LoginSite, _q, _tries, facts, run_child

pytestmark = [pytest.mark.skipif(os.name != "nt", reason="native AppContainer ACL loans"),
              pytest.mark.usefixtures("login_loan_open_module")]

PLANT = "planted by the child"
OPERATOR = "written by the operator"
#: Every name any of the harness profiles declares as vendor configuration in a login home.
DECLARED = sorted({name for profile in (CLAUDE_PROFILE, CODEX_PROFILE, GROK_PROFILE, KIMI_PROFILE)
                   for name in profile.login_forbidden})
#: Present before the attempt: the files a vendor writes beside its own login, and three declared
#: objects made protected (inheritance cut: `LoginSite` does it for the two hook objects).
BESIDE_LOGIN = {"config.toml": "model = 'x'", ".claude.json": "{}"}
PROTECTED = ("hooks", "hooks-paths", "mcp.json")
#: A name with a dot is a file, one without is a directory; `skills` holds an operator's own object.
FILES = [name for name in DECLARED
         if "." in name and name not in BESIDE_LOGIN and name not in PROTECTED]
DIRECTORIES = [name for name in DECLARED
               if "." not in name and name not in PROTECTED and name != "skills"]


def child_script(site: LoginSite) -> str:
    from tests.os_boundary_box import WITHOUT_CMDLETS
    home, write = site.login, "[IO.File]::WriteAllText({},'" + PLANT + "')"
    make = "$null = [IO.Directory]::CreateDirectory({}); "
    steps = [_tries("make_" + name, write.format(_q(home / name))) for name in FILES]
    steps += [_tries("make_" + name, make.format(_q(home / name)) + write.format(
        _q(home / name / "x"))) for name in DIRECTORIES]
    steps += [_tries("rewrite_" + name, write.format(_q(home / name))) for name in BESIDE_LOGIN]
    skills = home / "skills"
    steps += [_tries("rewrite_operators_skill", write.format(_q(skills / "mine" / "S.md"))),
              _tries("make_skills_evil", make.format(_q(skills / "evil")) + write.format(
                  _q(skills / "evil" / "x")))]
    mcp = _q(home / "mcp.json")
    steps += [_tries("protected_overwrite", write.format(mcp)),
              _tries("protected_delete", f"[IO.File]::Delete({mcp})"),
              _tries("protected_move", f"[IO.File]::Move({mcp},{_q(home / 'mcp2.json')})")]
    return WITHOUT_CMDLETS + "$o = ''; " + "".join(steps) + "[Console]::Out.Write($o)"


@pytest.fixture(scope="module")
def open_loan(tmp_path_factory, login_loan_open_module):
    from tests import os_boundary_windows as ac
    site = LoginSite(tmp_path_factory.mktemp("login-config"))
    for name, text in BESIDE_LOGIN.items():
        (site.login / name).write_text(text, encoding="utf-8")
    (site.login / "skills" / "mine").mkdir(parents=True)
    (site.login / "skills" / "mine" / "S.md").write_text(OPERATOR, encoding="utf-8")
    (site.login / "mcp.json").write_text(OPERATOR, encoding="utf-8")
    ac.protect_entry(site.login / "mcp.json")
    return site, run_child(site, "dispatch", child_script(site))


def test_while_the_loan_is_open_a_child_creates_every_name_the_profiles_declare(open_loan):
    site, seen = open_loan
    assert FILES and DIRECTORIES, "the witness tried nothing"
    outcome = seen["outcome"]
    assert outcome.status == "completed" and outcome.exit_code == 0, describe(outcome)
    for name in FILES:
        assert facts(seen)["make_" + name] == "ok", name
        assert (site.login / name).read_text(encoding="utf-8") == PLANT
    for name in DIRECTORIES:
        assert facts(seen)["make_" + name] == "ok", name
        assert (site.login / name / "x").read_text(encoding="utf-8") == PLANT


def test_while_the_loan_is_open_a_child_rewrites_what_the_vendor_and_the_operator_keep_there(
        open_loan):
    site, seen = open_loan
    for name in BESIDE_LOGIN:
        assert facts(seen)["rewrite_" + name] == "ok", name
        assert (site.login / name).read_text(encoding="utf-8") == PLANT
    assert facts(seen)["rewrite_operators_skill"] == "ok"
    assert (site.login / "skills" / "mine" / "S.md").read_text(encoding="utf-8") == PLANT
    assert facts(seen)["make_skills_evil"] == "ok", "a new object in an operator's own directory"


def test_everything_the_child_made_stays_in_the_home_after_the_return_took_the_profile_away(
        open_loan):
    site, seen = open_loan
    assert entries_naming(site.login, seen["sid"]) == []
    for name in (*FILES, *(f"{d}/x" for d in DIRECTORIES), "config.toml", "skills/evil/x"):
        assert (site.login / name).read_text(encoding="utf-8") == PLANT, name


def test_a_present_object_with_its_inheritance_cut_is_not_touched_whatever_its_name(open_loan):
    site, seen = open_loan
    names = ("protected_overwrite", "protected_delete", "protected_move")
    assert {k: facts(seen)[k] for k in names} == dict.fromkeys(names, "denied")
    assert (site.login / "mcp.json").read_text(encoding="utf-8") == OPERATOR
    assert not (site.login / "mcp2.json").exists()
