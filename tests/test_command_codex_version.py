"""The one form Codex CLI's version print takes, and the one this build refuses.

Its own module from the start. Grok Build's version cases lived in its transport
suite until two more were added and the file crossed the 800-line cap, and this
provider's version question is larger than Grok's was, not smaller.

**It is larger because the source and the binary disagree, and the source is the
one that misleads.** `codex-rs/cli/src/main.rs` declares `#[clap(author, version,
bin_name = "codex")]`, so a parser written by reading the entry point spells
`codex 0.112.0` -- and refuses every real install, while the catalog row goes on
advertising the provider as available and every dispatch fails the preflight
forever. What the reviewed binary really prints is the PACKAGE name: clap renders
the crate, the crate is `codex-cli`, and the observed print is exactly 19 bytes,
`codex-cli 0.112.0\\r\\n`. So `codex ` is refused HERE, by name, as its own case.

**And the reviewed number itself is an observation.** `codex-rs/Cargo.toml`
carries `version = "0.0.0"` for the whole workspace and `CHANGELOG.md` is a line
pointing at a releases page, so unlike every other provider in this roster there
is no pinned file to read it from. That makes the accepted form below the only
written-down statement of what this build was reviewed against, which is why it
is SPELLED here and cross-checked against the adapter's constant rather than
built from it: a reviewed version that moved without a review would otherwise
move this expectation with it.

Every case is driven end to end through a real child, because a refusal that
still spawned would be no refusal at all -- so what each one asserts is the
child's own spawn log, not the receipt alone.
"""
from __future__ import annotations

import pytest

from conductor.command.adapters.codex_cli import (
    REVIEWED_CODEX_VERSION,
    CodexCliTransport,
)

from tests import _fakecodex
from tests.test_command_codex_transport import a_harness, a_request, run_once

#: The form the reviewed binary really prints, SPELLED whole. Both halves: the
#: package name that clap renders, and the semver this build was reviewed
#: against. Built from `REVIEWED_CODEX_VERSION` it would move whenever that
#: constant moved, and the one thing this module most needs to catch would move
#: with it. The constant is cross-checked against the spelling instead.
ACCEPTED_FORM = "codex-cli 0.112.0"

#: Grouped by WHAT is wrong, so a failure names its category. Every row is one
#: edit away from the accepted form, so each fails for the reason it is filed
#: under and not for a second reason it happens to also have.
REFUSED_FORMS = (
    # a different version, dressed correctly
    ("version", "codex-cli 0.112.1"),
    ("version", "codex-cli 0.1120"),
    ("version", "codex-cli 0.112.0.1"),
    ("version", "codex-cli 00.112.0"),
    ("version", "codex-cli 0.112.0-rc.1"),
    # the PROGRAM name, which the source's `bin_name` describes and the binary
    # does not print. This is the whole reason this module exists.
    ("program", "codex 0.112.0"),
    ("program", "Codex 0.112.0"),
    ("program", "codex-cli-0.112.0"),
    ("program", "codexcli 0.112.0"),
    ("program", "codex-cli"),
    # a bare semver, which any executable at all could print
    ("bare", "0.112.0"),
    ("bare", "v0.112.0"),
    # the order, and the dressing another vendor in this roster uses
    ("order", "0.112.0 (codex-cli)"),
    ("order", "0.112.0 codex-cli"),
    # anything else on the line
    ("extra", "codex-cli 0.112.0 (abc1234)"),
    ("extra", "codex-cli  0.112.0"),
    ("extra", "the codex-cli 0.112.0 release"),
    ("extra", ""),
    ("extra", "warning: config is stale"),
)


def test_the_one_observed_form_of_the_version_print_is_accepted(tmp_path):
    """Driven end to end through a child, because that is where it matters."""
    adapter, _root, log = a_harness(
        tmp_path, **{_fakecodex.VERSION: ACCEPTED_FORM})

    receipt = run_once(adapter, a_request())

    assert receipt.outcome == "succeeded", receipt.detail
    assert len(_fakecodex.task_spawns(log)) == 1
    assert ACCEPTED_FORM == f"codex-cli {REVIEWED_CODEX_VERSION}", (
        "the reviewed version moved without this module's spelling moving with it")


@pytest.mark.parametrize(
    "category,printed", REFUSED_FORMS,
    ids=[f"{c}-{i}" for i, (c, _) in enumerate(REFUSED_FORMS)])
def test_no_other_shape_is_read_as_the_reviewed_version(
        tmp_path, category, printed):
    """Zero task spawns is the assertion that matters.

    A refusal that still spawned would be no refusal, so every case is checked
    against the child's own spawn log rather than against the receipt alone.
    """
    adapter, _root, log = a_harness(tmp_path, **{_fakecodex.VERSION: printed})

    receipt = run_once(adapter, a_request())

    assert receipt.outcome == "failed", f"ACCEPTED[{category}]={printed!r}"
    assert REVIEWED_CODEX_VERSION in receipt.detail
    assert _fakecodex.task_spawns(log) == [], (
        f"TASK_SPAWNED_ON[{category}]={printed!r}")


def test_a_version_print_the_build_cannot_answer_spawns_zero_tasks(tmp_path):
    adapter, _root, log = a_harness(tmp_path, **{_fakecodex.VERSION_FAILS: "1"})

    receipt = run_once(adapter, a_request())

    assert receipt.outcome == "failed"
    assert "version preflight" in receipt.detail
    assert _fakecodex.task_spawns(log) == []


def test_the_reviewed_version_is_proved_before_any_task_is_spawned(tmp_path):
    adapter, _root, log = a_harness(tmp_path)

    run_once(adapter, a_request())

    rows = _fakecodex.spawns(log)
    assert rows[0]["argv"] == ["--version"], "THE_PREFLIGHT_IS_NOT_FIRST=True"


def test_the_preflight_asks_the_bare_cli_and_never_the_subcommand(tmp_path):
    """`--version` at the top level, which is what the observed print came from.

    `codex exec --version` prints too, and it is a DIFFERENT entry point. The
    form this parser reads was observed from the bare CLI, so that is the one the
    preflight asks -- a version proved through one entry point and a task run
    through another would be proving the wrong thing about the wrong road.
    """
    adapter, _root, log = a_harness(tmp_path)

    run_once(adapter, a_request())

    preflight = _fakecodex.spawns(log)[0]["argv"]
    assert preflight == ["--version"], preflight
    assert "exec" not in preflight


def test_a_secret_planted_where_a_version_belongs_never_reaches_a_receipt(tmp_path):
    """The observed token is raw child output and may not be echoed anywhere."""
    secret = "sk-proj-planted-where-a-version-belongs"
    adapter, _root, _log = a_harness(tmp_path, **{_fakecodex.VERSION: secret})

    receipt = run_once(adapter, a_request())

    assert receipt.outcome == "failed"
    assert secret not in (receipt.detail or "")
    assert secret not in repr(receipt.as_dict())


#: A form the vendor really could print, at a version this build never reviewed.
#: It is the ONE case that separates "read the form and refused the version"
#: from "could not read the form at all", because both come back False.
VALID_BUT_UNREVIEWED = "codex-cli 9.9.9"


def test_a_valid_form_at_an_unreviewed_version_is_read_and_then_refused(tmp_path):
    """The parse and the comparison are two answers, and both are checked here.

    `_version_matches` is a boolean, and a boolean cannot say WHICH question it
    answered. `False` means either "a different build" -- correct, refuse -- or
    "this parser read nothing at all", which is a defect no refusal repairs. A
    production parser replaced with one matching NOTHING behaves identically to a
    correct one on every input except this: a valid form whose version differs.
    """
    adapter, _root, log = a_harness(
        tmp_path, **{_fakecodex.VERSION: VALID_BUT_UNREVIEWED})

    receipt = run_once(adapter, a_request())

    printed = (VALID_BUT_UNREVIEWED + "\n").encode("utf-8")
    assert adapter._parsed_version(printed) == "9.9.9", (
        "the parser could not read a form this vendor really prints")
    assert adapter._version_matches(printed) is False
    assert receipt.outcome == "failed"
    assert REVIEWED_CODEX_VERSION in receipt.detail
    assert _fakecodex.task_spawns(log) == []


def test_the_parser_reads_the_reviewed_form_into_the_reviewed_semver():
    """The positive control: reading and agreeing are still two separate steps.

    The three inputs are the three answers this parser can give, and the middle
    one is the trap: `codex 0.112.0` is what the source's `bin_name` describes,
    and reading it would mean this parser was written from the wrong statement.
    """
    unbound = CodexCliTransport.__new__(CodexCliTransport)

    assert CodexCliTransport._parsed_version(
        unbound, b"codex-cli 0.112.0\r\n") == "0.112.0"
    assert CodexCliTransport._parsed_version(unbound, b"codex 0.112.0\n") is None
    assert CodexCliTransport._parsed_version(unbound, b"0.112.0\n") is None


def test_the_observed_print_is_carried_whole_including_its_line_ending(tmp_path):
    """19 bytes, CRLF and all, because that is what the binary really produced.

    The version token is taken from the first non-empty LINE, so a print that
    ends `\\r\\n` must not leave a stray carriage return inside the token. That is
    not hypothetical for this provider: the print was observed on Windows and the
    bytes were counted.
    """
    observed = b"codex-cli 0.112.0\r\n"
    unbound = CodexCliTransport.__new__(CodexCliTransport)

    assert len(observed) == 19
    assert CodexCliTransport._parsed_version(unbound, observed) == "0.112.0"
    assert CodexCliTransport._version_matches(unbound, observed) is True
