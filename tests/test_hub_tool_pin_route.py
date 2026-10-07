"""`POST /hub/tools/<tool>/pin`: the human picks a candidate the hub found, the hub pins it (8.8).

The route answers at once (a version probe of at most ten seconds, as `conduct tools pin` makes),
refuses in the closed codes of the table, writes `tools.json` only through `tool_pins.pin_tool`, and
holds no path in any answer. The search and the version probe are stand-ins; the pin, its file, its
lock and the refusals of the pin file are the real library over a real folder.
"""
from __future__ import annotations

import json
import os
import re

import pytest

from conductor import tool_pins
from tests._hub_stack import A, B, Stack
from tests.test_hub_handlers_http import Command, _code, _envelope, _name_a_login, _settled
from tests.test_hub_tool_candidates import BIN, GH, GIT, Verdicts, build, write_pins


class Rig:
    """A stack whose candidates are git at `GIT` and gh at `GH`, shown at the versions given.

    `says` is what each tool answers to `--version` when the pin is made; it starts as the
    version that was shown, and a test changes it to move the tool after the person saw it.
    """

    def __init__(self, tmp_path, git: str, gh: str) -> None:
        self.found, _probe = build(tmp_path / "candidates", which={"git": GIT, "gh": GH},
                                   files=(GIT, GH), versions={GIT: git, GH: gh})
        self.found.discover()
        self.says = {GIT: f"git version {git}\n", GH: f"gh version {gh}\n"}
        self.verdicts = Verdicts()
        self.command = Command()
        self.stack = Stack(tmp_path, owner_popen=self.command, candidates=self.found,
                           verify_tool=self.verdicts, pin_run=self._run)
        self.command.world = self.stack.world

    def _run(self, argv, env):
        return self.says[argv[0]]

    def ident(self, tool: str) -> str:
        return self.found.offered(tool, settled=False)[0]["candidate_id"]

    def pin(self, tool: str, ident: str | None = None):
        return self.stack.post(f"/hub/tools/{tool}/pin", {
            "candidate_id": self.ident(tool) if ident is None else ident})

    def tools_bytes(self) -> bytes | None:
        path = self.stack.world.home / "tools.json"
        return path.read_bytes() if path.is_file() else None


@pytest.fixture
def rig(tmp_path):
    made = []

    def build(git: str = "2.47.1", gh: str = "2.62.0") -> Rig:
        one = Rig(tmp_path / f"rig{len(made)}", git, gh)
        made.append(one)
        return one

    yield build
    for one in made:
        one.stack.close()


# -- the pin itself ----------------------------------------------------------------------------


def test_pin_writes_the_pin_through_pin_tool_and_the_setup_then_reads_pinned_with_no_candidates(
        rig):
    one = rig()
    reply = one.pin("git")
    assert reply.status == 200 and set(reply.json()) == {"tool", "state", "display", "version"}
    assert reply.json() == {"tool": "git", "state": "pinned", "version": "2.47.1",
                            "display": f"{os.path.basename(BIN)}{os.sep}{os.path.basename(GIT)}"}
    assert tool_pins.read_pin("git", one.stack.world.home) == tool_pins.ToolPin(
        "git", GIT, "2.47.1")
    git = one.stack.get("/hub/setup").json()["tools"]["git"]
    assert (git["state"], git["version"], git["candidates"]) == ("pinned", "2.47.1", [])
    assert one.stack.get("/hub/setup").json()["tools"]["gh"]["candidates"] != []


def test_pin_tells_the_page_to_read_the_setup_again(rig):
    one = rig()
    frames = []
    one.stack.bus.publish = lambda name, *rest, **more: frames.append(name)
    assert one.pin("gh").status == 200
    assert "setup" in frames


def test_pin_refuses_a_version_that_moved_since_it_was_shown_and_writes_nothing(rig):
    one = rig()
    one.says[GH] = "gh version 2.70.0\n"
    before = one.tools_bytes()
    assert _code(one.pin("gh"), 409) == "gh_changed"
    assert one.tools_bytes() == before
    one.says[GIT] = "git version 2.50.0\n"
    assert _code(one.pin("git"), 409) == "git_changed"
    assert one.tools_bytes() == before


def test_pin_refuses_an_old_git_and_an_unreadable_tool_in_their_own_codes(rig):
    old = rig(git="2.30.9")
    assert _code(old.pin("git"), 409) == "git_too_old"
    assert old.tools_bytes() is None
    unreadable = rig()
    unreadable.says[GH] = "hello\n"
    reply = unreadable.pin("gh")
    assert _code(reply, 409) == "tool_version_unreadable"
    assert _envelope(reply)["detail"] == {}, "a version nobody can read carries no pin-file reason"
    assert unreadable.tools_bytes() is None


def test_pin_with_an_unknown_candidate_is_candidate_not_found_and_a_malformed_id_is_contract_invalid(  # noqa: E501
        rig):
    one = rig()
    before = one.tools_bytes()
    assert _code(one.pin("git", "cand-" + "0" * 32), 404) == "candidate_not_found"
    for malformed in ("cand-" + "0" * 31, "cand-" + "G" * 32, "x", "", GIT):
        assert _code(one.pin("git", malformed), 422) == "contract_invalid", malformed
    assert _code(one.stack.post("/hub/tools/git/pin", {"candidate_id": 5}), 422
                 ) == "contract_invalid"
    assert one.tools_bytes() == before


def test_a_candidate_of_the_other_tool_is_candidate_not_found(rig):
    one = rig()
    assert _code(one.pin("git", one.ident("gh")), 404) == "candidate_not_found"
    assert one.tools_bytes() is None


def test_a_body_that_names_a_place_or_adds_a_key_is_refused_before_a_pin_is_tried(rig):
    one = rig()
    ident = one.ident("git")
    for body in ({"candidate_id": ident, "path": GIT}, {"path": GIT}, {},
                 {"candidate_id": ident, "tool": "git"}):
        assert _code(one.stack.post("/hub/tools/git/pin", body), 422) == "contract_invalid"
    assert one.tools_bytes() is None


# -- a pin file that is the problem ------------------------------------------------------------


def _break_the_file(one: Rig, breakage: str, monkeypatch) -> None:
    home = one.stack.world.home
    if breakage == "corrupt":
        (home / "tools.json").write_bytes(b"{ not the schema")
    elif breakage == "unreadable":
        (home / "tools.json").mkdir(parents=True)
    else:
        def refuse(path, payload, **options):
            raise PermissionError(13, "read-only")
        monkeypatch.setattr("conductor.atomic_replace.replace_bytes", refuse)


@pytest.mark.parametrize("reason", ["corrupt", "unreadable", "unwritable"])
def test_a_pin_file_problem_answers_tool_version_unreadable_with_the_reason_of_the_file(
        rig, reason, monkeypatch):
    one = rig()
    _break_the_file(one, reason, monkeypatch)
    reply = one.pin("git")
    assert _code(reply, 409) == "tool_version_unreadable"
    assert _envelope(reply)["detail"] == {"reason": reason}
    text = reply.body.decode("utf-8")
    assert str(one.stack.world.home) not in text and "tools.json" not in text
    assert "denied" not in text and "read-only" not in text


def test_every_code_the_pin_library_proposes_for_its_file_is_mapped_to_a_reason():
    from conductor.hub import service

    assert set(service.PIN_FILE_REASONS) == set(tool_pins.PROPOSED_CODES)
    assert set(service.PIN_FILE_REASONS.values()) == {"corrupt", "unreadable", "unwritable"}


def test_a_corrupt_file_is_left_as_the_owner_wrote_it(rig):
    one = rig()
    write_pins(one.stack.world.home)
    (one.stack.world.home / "tools.json").write_bytes(b"{ the owner's own edit")
    assert _code(one.pin("git"), 409) == "tool_version_unreadable"
    assert one.tools_bytes() == b"{ the owner's own edit"


# -- what the hub believed about the old pin -----------------------------------------------------


def test_a_new_pin_drops_the_verification_cached_for_the_old_one(rig):
    one = rig()
    write_pins(one.stack.world.home, git={"path": GIT, "version": "2.47.1"})
    one.verdicts.refuse["git"] = "tool_version_unreadable"
    assert one.stack.get("/hub/setup").json()["tools"]["git"]["state"] == "unreadable"
    del one.verdicts.refuse["git"]                  # the tool answers again; the pin is the same
    assert one.stack.get("/hub/setup").json()["tools"]["git"]["state"] == "unreadable", (
        "the verdict of an unchanged pin is kept until the pin changes")
    assert one.pin("git").status == 200
    assert one.stack.get("/hub/setup").json()["tools"]["git"]["state"] == "pinned"


# -- no path in any answer ------------------------------------------------------------------------


def test_no_answer_of_the_four_routes_nor_the_setup_holds_a_path(rig, tmp_path, monkeypatch):
    one = rig()
    stack = one.stack
    deep = stack.world.roots["a"]
    login, _box = _name_a_login(stack, tmp_path, monkeypatch, leased=True)
    (entry,) = stack.get("/hub/setup").json()["logins"]
    stack.world.gone("a", "stop_uncertain", head="opened")
    one.command.err = f"recovery_refused: {deep} {login} is somewhere\n"
    one.command.code, one.command.out = 1, ""
    answers = [stack.get("/hub/setup"), one.pin("git")]
    recover = stack.post(f"/hub/projects/{A}/recover")
    login_recover = stack.post(f"/hub/logins/{entry['login_key']}/recover")
    providers = stack.post(f"/hub/projects/{B}/providers")
    answers += [recover, login_recover, providers]
    rows = [_settled(stack, reply.json()["operation_id"])
            for reply in (recover, login_recover, providers)]
    answers.append(stack.get("/hub/setup"))
    texts = [reply.body.decode("utf-8") for reply in answers] + [json.dumps(row) for row in rows]
    forbidden = [deep, str(login), str(stack.world.home), os.path.dirname(GIT), GIT,
                 "a-distinctive-login", "is somewhere"]
    for text in texts:
        for word in forbidden:
            assert word not in text and json.dumps(word)[1:-1] not in text, (word, text[:200])
        assert not re.search(r"[A-Za-z]:[\\/]", text.replace("http://", "")), text[:200]
