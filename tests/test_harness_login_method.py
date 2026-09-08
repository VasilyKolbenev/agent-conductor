"""WHICH login a subscription run is really using, and what its directory holds.

Split out of `test_harness_subscription_login` when that module crossed the
800-line cap. The seam is a subject: next door proves where a child is pointed
and what a spawn may leave behind it; this proves the two questions asked BEFORE
a task is allowed to start.

Both were defects a review found, and both are measured facts about the pinned
binaries rather than design preferences. An exit code says a credential was
found and never which kind: a directory holding only an API key answers the
status question with success on both harnesses, and a Codex file holding a
subscription AND a key answers with the key. A login directory that also holds
configuration gives back the isolation a per-attempt empty directory provided:
a trusted-project entry there made the vendor read the work tree's own config.
"""
from __future__ import annotations

import pytest

from tests import _fakeclaude
from tests.test_command_claude_transport import a_request, run_once
from tests.test_harness_subscription_login import (
    a_codex_harness,
    a_harness,
    a_login_home,
)


@pytest.mark.parametrize("method", [
    "api_key", "quiet_key", "key_source", "vertex", "none", "stale",
    "methodless", "scalar", "garbage",
    # A method this build has never seen, and an empty one. Neither is a known
    # refusal, and a rule written as exclusions admitted both.
    "unknown_method", "empty_method",
    # The same method, plane and exit code as a real subscription, differing
    # only in the plan it names -- which is the road the vendor's own login
    # command offers as the alternative to one. And an answer that names no
    # plan: it cannot say it is not that road.
    "console_plan", "planless", "empty_plan", "loud_console"])
def test_a_login_that_is_not_a_subscription_refuses_the_run(tmp_path, method):
    """An exit code says a credential was found, never which kind.

    MEASURED on both reviewed binaries: a directory holding nothing but an API
    key answers the status question with exit 0. The first version of this seam
    read only that code, so a subscription pin ran on API billing -- the silent
    fallback the pin exists to refuse. `vertex` and `garbage` are here because a
    billing plane this build does not know, and an answer it cannot read, are
    refusals for the same reason: neither is a subscription this build can
    vouch for.
    """
    home = a_login_home(tmp_path)
    adapter, _root, log = a_harness(
        tmp_path, auth="subscription", auth_home=str(home),
        **{_fakeclaude.LOGIN_METHOD: method})

    receipt = run_once(adapter, a_request())

    assert receipt.outcome == "failed"
    assert "reports no subscription login" in receipt.detail
    assert "api" not in receipt.detail.lower().replace("api key", "")
    assert _fakeclaude.prompt_spawns(log) == [], "a task ran on the wrong login"


def test_the_subscription_answer_the_vendor_really_gives_is_admitted(tmp_path):
    """The positive control: the refusals above are the METHOD being read, not
    this build refusing every login."""
    home = a_login_home(tmp_path)
    adapter, _root, log = a_harness(
        tmp_path, auth="subscription", auth_home=str(home),
        **{_fakeclaude.LOGIN_METHOD: "subscription"})

    assert run_once(adapter, a_request()).outcome == "succeeded"

    assert len(_fakeclaude.prompt_spawns(log)) == 1


@pytest.mark.parametrize("method,admitted", [
    ("subscription", True), ("api_key", False), ("none", False),
    # Three answers that exit 0 and are not the sentence this build knows: a
    # wording it has never seen, a method it has never seen, and one that
    # contains the admitting words inside a sentence saying the opposite.
    ("unrecognised", False), ("unknown_method", False), ("almost", False)])
def test_codex_reads_its_own_sentence_about_which_login_it_found(
        tmp_path, method, admitted):
    """The same rule on the other harness, in that vendor's own words -- and its
    words are the only thing that separates the two, since both exit 0."""
    from tests import _fakecodex

    home = tmp_path / "auth" / "codex"
    home.mkdir(parents=True)
    adapter, _root, log = a_codex_harness(
        tmp_path, auth="subscription", auth_home=str(home),
        **{_fakecodex.LOGIN_METHOD: method})

    receipt = run_once(adapter, a_request())

    assert (receipt.outcome == "succeeded") is admitted, receipt.detail
    assert bool(_fakecodex.task_spawns(log)) is admitted


def test_a_status_answer_this_build_could_not_read_whole_is_refused(tmp_path):
    """The refusing phrase is a suffix of the admitting one on Codex, so a
    capture cut inside it would turn an API key into a subscription. Every other
    reader of child output in this build refuses a truncated capture; so does
    this one."""
    from conductor.command.adapters import headless_login

    home = a_login_home(tmp_path)
    adapter, _root, log = a_harness(
        tmp_path, auth="subscription", auth_home=str(home))
    real = headless_login.LoginRoad._attempt_login_status

    def cut(self, request):
        from dataclasses import replace

        return replace(real(self, request), output_truncated=True)

    headless_login.LoginRoad._attempt_login_status = cut
    try:
        receipt = run_once(adapter, a_request())
    finally:
        headless_login.LoginRoad._attempt_login_status = real

    assert receipt.outcome == "failed"
    assert "reports no subscription login" in receipt.detail
    assert _fakeclaude.prompt_spawns(log) == []


def test_a_claude_login_directory_holding_customization_refuses(tmp_path):
    """The same rule on the other harness, whose forbidden names are pure
    customization: anything at all in them is settings this build cannot vouch
    for, so the NAME is the grant."""
    home = a_login_home(tmp_path)
    (home / "settings.json").write_text(
        '{"hooks": {}}', encoding="utf-8", newline="\n")
    adapter, _root, log = a_harness(
        tmp_path, auth="subscription", auth_home=str(home))

    receipt = run_once(adapter, a_request())

    assert receipt.outcome == "failed"
    assert "also holds" in receipt.detail
    assert _fakeclaude.spawns(log) == [], (
        "a spawn was pointed at a directory this build refuses")


def test_a_login_directory_that_also_holds_configuration_refuses_first(tmp_path):
    """MEASURED on Codex 0.112.0: a `config.toml` in the login directory naming
    the work tree as a trusted project made the vendor read that tree's own
    `.codex/config.toml` -- the very layer an empty per-attempt home excluded,
    and this transport's stated isolation basis.

    Refused BEFORE the status spawn, because asking the status question is
    itself a full startup pointed at that directory.
    """
    from tests import _fakecodex

    home = tmp_path / "auth" / "codex"
    home.mkdir(parents=True)
    (home / "config.toml").write_text(
        '[projects."C:\\\\work"]\ntrust_level = "trusted"\n',
        encoding="utf-8", newline="\n")
    adapter, _root, log = a_codex_harness(
        tmp_path, auth="subscription", auth_home=str(home))

    receipt = run_once(adapter, a_request())

    assert receipt.outcome == "failed"
    assert "also holds" in receipt.detail and "configuration" in receipt.detail
    assert _fakecodex.spawns(log) == [] or not [
        row for row in _fakecodex.spawns(log)
        if _fakecodex.login_question(row["argv"])], (
        "the status question was asked of a directory this build refuses")


def test_a_configuration_this_build_cannot_read_is_refused_not_admitted(tmp_path):
    """A configuration whose contents cannot be established is not one this
    build can say is harmless -- and the whole point of reading the file rather
    than the name is that unreadable must not become 'no keys found'."""
    from tests import _fakecodex

    home = tmp_path / "auth" / "codex"
    home.mkdir(parents=True)
    (home / "config.toml").write_text(
        "this is not TOML at all [[[", encoding="utf-8", newline="\n")
    adapter, _root, log = a_codex_harness(
        tmp_path, auth="subscription", auth_home=str(home))

    receipt = run_once(adapter, a_request())

    assert receipt.outcome == "failed"
    assert "also holds" in receipt.detail
    assert _fakecodex.spawns(log) == []


@pytest.mark.parametrize("body,refused", [
    ('profile = "x"\n[profiles.x]\nmodel_provider = "elsewhere"\n', True),
    ('[projects."C:\\\\work"]\ntrust_level = "trusted"\n', True),
    ('[tui]\nnotifications = true\n[history]\npersistence = "none"\n', False),
])
def test_a_configuration_is_judged_at_every_depth_it_can_hide_in(
        tmp_path, body, refused):
    """The top level is not where a format that nests keeps its authority.

    This vendor's own documentation puts a provider override inside a profile
    table, so a rule that read only the top level would call the same authority
    harmless one line lower -- while refusing an ordinary `[tui]` block would
    refuse a directory nobody should have to explain.
    """
    from tests import _fakecodex

    home = tmp_path / "auth" / "codex"
    home.mkdir(parents=True)
    (home / "config.toml").write_text(body, encoding="utf-8", newline="\n")
    adapter, _root, log = a_codex_harness(
        tmp_path, auth="subscription", auth_home=str(home))

    receipt = run_once(adapter, a_request())

    assert (receipt.outcome == "failed") is refused, receipt.detail
    assert (_fakecodex.task_spawns(log) == []) is refused


def test_every_name_a_profile_declares_is_really_read(tmp_path):
    """A second name added to the list would otherwise have no reader at all and
    be silently inert -- the defect this build calls a field with no consumer."""
    from dataclasses import replace

    from conductor.command.adapters.codex_cli import CODEX_PROFILE

    home = tmp_path / "auth" / "codex"
    home.mkdir(parents=True)
    (home / "other.toml").write_text(
        '[projects."C:\\\\work"]\ntrust_level = "trusted"\n',
        encoding="utf-8", newline="\n")
    adapter = a_codex_harness(
        tmp_path, auth="subscription", auth_home=str(home))[0]

    assert adapter._login_home_grants(str(home)) == ()
    adapter.profile = replace(
        CODEX_PROFILE, login_forbidden=("config.toml", "other.toml"))
    assert adapter._login_home_grants(str(home)) == ("projects",)


def test_a_subscription_protocol_that_cannot_be_asked_refuses(tmp_path):
    """The config door admits `subscription` for a protocol whose transport
    drives a login. A profile that declares no status question cannot establish
    one, and skipping the check quietly would be the loudest of the defects this
    seam exists to close, in silence."""
    from dataclasses import replace

    from conductor.command.adapters.claude_code import CLAUDE_PROFILE

    home = a_login_home(tmp_path)
    adapter, _root, log = a_harness(
        tmp_path, auth="subscription", auth_home=str(home))
    adapter.profile = replace(CLAUDE_PROFILE, login_argv=(), login_command=())

    receipt = run_once(adapter, a_request())

    assert receipt.outcome == "failed"
    assert "cannot establish a subscription login" in receipt.detail
    assert _fakeclaude.prompt_spawns(log) == []


def test_the_bound_is_shared_by_every_declared_name(tmp_path, monkeypatch):
    """Two per-run names with a budget apiece is two budgets. What the limit is
    meant to bound is what this build will read of one directory in all."""
    from conductor.command.adapters import login_home

    home = a_login_home(tmp_path)
    for name in ("sessions", ".last-cleanup"):
        (home / name).mkdir()
        for index in range(3):
            (home / name / f"{index}.json").write_text(
                "{}", encoding="utf-8", newline="\n")
    monkeypatch.setattr(login_home, "MEASURE_LIMIT", 8)

    # Three entries under each name, four top-level names: over the bound only
    # when the two are counted together.
    assert login_home._walk(home / "sessions", "sessions", 8) != [None]
    assert login_home.measure(str(home), ("sessions", ".last-cleanup")) is None


def test_a_top_level_listing_too_large_to_finish_is_unknown(tmp_path, monkeypatch):
    """The walk is not the only place a directory can be too big to read: the
    top level is listed first, and a bound applied to one and not the other
    bounds nothing."""
    from conductor.command.adapters import login_home

    home = a_login_home(tmp_path)
    for index in range(6):
        (home / f"row-{index}").write_text("", encoding="utf-8", newline="\n")
    monkeypatch.setattr(login_home, "MEASURE_LIMIT", 3)

    assert login_home.entries(str(home)) is None
    assert login_home.measure(str(home), ("sessions",)) is None


def test_a_configuration_naming_nothing_dangerous_is_left_alone(tmp_path):
    """The positive control, and the reason the KEYS are read rather than the
    name: the vendor writes its own configuration beside its own login, and
    refusing that name would refuse the directory this build asked for."""
    from tests import _fakecodex

    home = tmp_path / "auth" / "codex"
    home.mkdir(parents=True)
    (home / "config.toml").write_text(
        'model = "gpt-5.3-codex"\nhide_agent_reasoning = true\n',
        encoding="utf-8", newline="\n")
    adapter, _root, log = a_codex_harness(
        tmp_path, auth="subscription", auth_home=str(home))

    assert run_once(adapter, a_request()).outcome == "succeeded"

    assert len(_fakecodex.task_spawns(log)) == 1


def test_a_directory_this_build_cannot_read_is_not_called_free_of_configuration(
        tmp_path, monkeypatch):
    """"I could not establish what is there" is not "there is nothing there",
    and this is the door where believing the second starts a vendor inside a
    directory whose contents were never established."""
    from conductor.command.adapters import login_home

    home = a_login_home(tmp_path)
    adapter, _root, log = a_harness(
        tmp_path, auth="subscription", auth_home=str(home))
    monkeypatch.setattr(login_home, "entries", lambda _home: None)

    receipt = run_once(adapter, a_request())

    assert receipt.outcome == "failed"
    assert "also holds" in receipt.detail
    assert _fakeclaude.spawns(log) == []


def test_a_provider_that_declared_no_reader_admits_no_answer():
    """A programming fault reported as a refusal, not as an exception: a
    provider that asked the question and never said how to read the answer must
    not have its runs reported as unknown attempts."""
    from conductor.command.adapters.headless_login import LoginRoad

    assert LoginRoad._login_method_admitted(object(), b'{"loggedIn": true}') is False


def test_the_bound_counts_the_whole_walk_and_not_each_directory(
        tmp_path, monkeypatch):
    """A limit applied afresh to every directory bounds nothing: a tree of a
    thousand small directories passes it a thousand times. What must be bounded
    is the walk."""
    from conductor.command.adapters import login_home

    home = a_login_home(tmp_path)
    (home / "sessions").mkdir()
    for branch in ("a", "b"):
        (home / "sessions" / branch).mkdir()
        for index in range(2):
            (home / "sessions" / branch / f"{index}.json").write_text(
                "{}", encoding="utf-8", newline="\n")
    monkeypatch.setattr(login_home, "MEASURE_LIMIT", 4)

    # Six paths in all, and no single directory holds more than two: only a
    # bound that carries across directories can see it.
    assert login_home._walk(home / "sessions", "sessions") == [None]
    monkeypatch.setattr(login_home, "MEASURE_LIMIT", 5000)
    assert len(login_home._walk(home / "sessions", "sessions")) == 6


def test_the_read_itself_stops_and_not_only_the_answer(tmp_path, monkeypatch):
    """The bound has to be on the READING. A limit applied to a listing that has
    already been made describes an unbounded read and then trims its result --
    which gives exactly the same answer, so only counting what was consumed can
    tell the two apart.
    """
    from conductor.command.adapters import login_home

    home = a_login_home(tmp_path)
    (home / "sessions").mkdir()
    for index in range(40):
        (home / "sessions" / f"{index}.json").write_text(
            "{}", encoding="utf-8", newline="\n")
    seen = []
    real = login_home.os.scandir

    class Counting:
        def __init__(self, where):
            self._rows = real(where)

        def __enter__(self):
            return self

        def __exit__(self, *_leaving):
            self._rows.close()
            return False

        def __iter__(self):
            for row in self._rows:
                seen.append(row.name)
                yield row

    monkeypatch.setattr(login_home.os, "scandir", Counting)
    monkeypatch.setattr(login_home, "MEASURE_LIMIT", 5)

    assert login_home._walk(home / "sessions", "sessions") == [None]
    assert len(seen) <= 6, (
        f"the whole directory was consumed before the bound applied: {len(seen)}")


def test_a_directory_too_large_to_finish_reading_is_unknown(tmp_path, monkeypatch):
    """The bound is the answer to "what if this never ends", so it has to BE a
    bound: a walk that listed everything and trimmed afterwards would have
    already done the unbounded thing."""
    from conductor.command.adapters import login_home

    home = a_login_home(tmp_path)
    (home / "sessions").mkdir()
    for index in range(6):
        (home / "sessions" / f"{index}.json").write_text(
            "{}", encoding="utf-8", newline="\n")
    monkeypatch.setattr(login_home, "MEASURE_LIMIT", 3)

    # The WALK's own answer, not the caller's. A walk that listed everything
    # and let the caller trim afterwards would give the same measurement and
    # would already have done the unbounded thing.
    assert login_home._walk(home / "sessions", "sessions") == [None]
    assert login_home.measure(str(home), ("sessions",)) is None
    monkeypatch.setattr(login_home, "MEASURE_LIMIT", 5000)
    assert len(login_home._walk(home / "sessions", "sessions")) == 6
    assert login_home.measure(str(home), ("sessions",)) is not None


def test_a_login_directory_holding_only_its_login_is_not_refused(tmp_path):
    """The positive control for the refusal above."""
    from tests import _fakecodex

    home = tmp_path / "auth" / "codex"
    home.mkdir(parents=True)
    (home / "auth.json").write_text("{}", encoding="utf-8", newline="\n")
    adapter, _root, _log = a_codex_harness(
        tmp_path, auth="subscription", auth_home=str(home))

    assert run_once(adapter, a_request()).outcome == "succeeded"
