"""How Grok Build's version print is READ, and what may never be read as one.

Its own module because it is one closed circuit with many exits, and because the
transport suite it came out of crossed the line cap when this slice added two
tests to it. What lives here is every question about the PRINT: which forms are
accepted, which are refused and with how many prompt spawns, which byte
sequences are not versions at all, and -- added by the Codex slice's opening
microfix -- what the parser MADE of what it read, which a boolean cannot say.

The harness is the transport suite's, imported rather than copied: these tests
drive the same real provider door, the same owned-process runner and the same
real child.
"""
from __future__ import annotations

import pytest

from conductor.command.adapters.grok_build import (
    REVIEWED_GROK_VERSION,
    GrokBuildAdapter,
)

from tests import _fakegrok
from tests.test_command_grok_transport import (
    SECRET,
    _recorded,
    a_harness,
    a_request,
    run_once,
)


# --- the version is PARSED, and only its semver counts ------------------------


#: Every shape the vendor's own composition can produce -- and only those -- built
#: as an explicit cross-product so a form cannot be dropped by editing prose.
#:
#: Two of the three parts do NOT vary, and the sources are what say so: the entry
#: point wraps the crate's string as `format!("grok {}\n", ...)`, so the program
#: name is on every line; and `set_full_version(env!("VERSION_WITH_COMMIT"))` is
#: `main`'s FIRST statement, ahead of argument parsing and therefore ahead of the
#: `--version` dispatch, so the commit is always already set. Only the channel
#: varies, because only `channel_label()` really returns "".
#:
#: So the cross-product runs over the commit CONTENTS and the channel. The
#: contents are not this suite's invention either: `build.rs` writes `git
#: rev-parse --short HEAD` or falls back to the literal `unknown`, and
#: `core.abbrev` picks the length between two bounds git enforces ITSELF -- it
#: refuses a setting below 4 outright ("abbrev length out of range", so the
#: build script's fallback writes `unknown` instead), and clamps one above the
#: object name, which is 40 digits in the SHA-1 tree this module is pinned
#: against. So both ENDS of the published range are here as well as a middle,
#: and `UNPUBLISHED_COMMITS` stands just outside each end.
_COMMITS = ("abc1234", "unknown", "def0", "0123456789abcdef" * 2 + "01234567")
_CHANNELS = ("", " [stable]", " [alpha]")
ACCEPTED_FORMS = tuple(
    f"grok 1.0.5 ({commit}){channel}"
    for commit in _COMMITS for channel in _CHANNELS)


def test_the_accepted_set_is_the_whole_cross_product_and_nothing_was_dropped():
    """A count, so editing the lists above cannot silently narrow coverage.

    Two members are named as well, and deliberately the two a reader would not
    think to write: a commit with no channel at all, and the word the build
    script falls back to when it cannot reach git.
    """
    assert len(ACCEPTED_FORMS) == len(_COMMITS) * len(_CHANNELS)
    assert len(ACCEPTED_FORMS) == 12
    assert "grok 1.0.5 (abc1234)" in ACCEPTED_FORMS, "a commit with no channel"
    assert "grok 1.0.5 (unknown)" in ACCEPTED_FORMS, "the git-less fallback"
    assert all(form.startswith("grok 1.0.5 (") for form in ACCEPTED_FORMS), (
        "the program name and the commit are not optional in any published form")


@pytest.mark.parametrize("printed", ACCEPTED_FORMS)
def test_every_published_form_of_the_version_print_is_accepted(tmp_path, printed):
    """Every shape a real install can print, driven end to end through a child.

    This list is the correction of a defect that would have shipped: the first
    version of this adapter modelled the version CRATE and never read the entry
    point that adds the `grok ` prefix, so it refused every string a real Grok
    Build prints -- while the row still reported itself available. The provider
    could not have dispatched once.

    Its guard against over-correction is `REFUSED_FORMS`, and the two must be
    read together: this test alone is passed by a parser that accepts anything.
    """
    adapter, _root, log = a_harness(tmp_path, FAKEGROK_VERSION=printed)

    receipt = run_once(adapter, a_request())

    assert receipt.outcome == "succeeded", f"REFUSED_A_PUBLISHED_FORM={printed!r}"
    assert len(_fakegrok.prompt_spawns(log)) == 1


#: Forms the version CRATE can build and the PROGRAM never prints. They are
#: named together rather than scattered through the matrix because what they
#: share is not a shape: each is what you get by reading `full_version()`'s
#: `unwrap_or(VERSION)` fallback, or a direct call to
#: `display_version_with_commit`, as if it were a published form. Neither is
#: reachable through the binary, and a probe on `dcfd7af` found this preflight
#: ADMITTING all four -- which is the whole reason they are written down here.
CRATE_ONLY_FORMS = (
    "1.0.5",
    "grok 1.0.5",
    "1.0.5 [alpha]",
    "1.0.5 (abc1234)",
    "1.0.5 (abc1234) [stable]",
    "grok 1.0.5 [stable]",
)
#: Commit CONTENTS no road through `build.rs` can emit. `git rev-parse --short`
#: writes lowercase hex of 4 to 40 digits, and the one fallback writes one
#: lowercase word, so anything else between those parentheses was printed by
#: something that is not a Grok Build.
#:
#: Two kinds are here. The wrong ALPHABET: `..` and a bare semver, because a
#: parenthesised run of any non-space characters -- which this parser accepted
#: once -- reads a path fragment and a version number as a commit just as
#: happily as a hash. And the wrong LENGTH, just outside each end of the range:
#: 1 and 3 below it, where git refuses the setting and the fallback takes over,
#: and 41 and 200 above the object name git clamps to. A run of hex with no
#: length at all is what this parser accepted next, so both ends are witnessed
#: rather than argued.
UNPUBLISHED_COMMITS = (
    "zzzzzzz", "ABC1234", "Unknown", "unknown2", "../../etc", "1.0.5", "abc 1234",
    "",
    "a", "aaa", "a" * 41, "a" * 200,
)
#: The refusal matrix, grouped by WHAT is wrong, so a failure names its category
#: rather than one string among many. Every row outside `crate-only` is dressed
#: in the published form and wrong in exactly ONE part -- otherwise a row could
#: keep passing for a reason its category does not name.
REFUSED_FORMS = (
    # a form only the crate can build
    *(("crate-only", form) for form in CRATE_ONLY_FORMS),
    # a different version, dressed correctly in every other part
    ("version", "grok 1.0.4 (abc1234) [stable]"),
    ("version", "grok 1.0.50 (abc1234)"),
    ("version", "grok 1.0.5.1 (abc1234)"),
    ("version", "grok 1.0.5-rc.1 (abc1234)"),
    ("version", "grok 1.0.5+meta (abc1234)"),
    ("version", "grok 01.0.5 (abc1234)"),
    ("version", "grok 1.0 (abc1234)"),
    # a prefix that is not the program name
    ("prefix", "krog 1.0.5 (abc1234)"),
    ("prefix", "grok  1.0.5 (abc1234)"),
    ("prefix", "GROK 1.0.5 (abc1234)"),
    ("prefix", "Grok 1.0.5 (abc1234)"),
    ("prefix", "grok-build 1.0.5 (abc1234)"),
    ("prefix", "the grok 1.0.5 (abc1234)"),
    ("prefix", "grok v1.0.5 (abc1234)"),
    # a commit whose CONTENTS the build script cannot emit
    *(("commit", f"grok 1.0.5 ({commit})") for commit in UNPUBLISHED_COMMITS),
    # a commit that is not a parenthesised token at all
    ("commit-shape", "grok 1.0.5 abc1234"),
    ("commit-shape", "grok 1.0.5 (abc1234"),
    ("commit-shape", "grok 1.0.5 ((abc1234))"),
    ("commit-shape", "grok 1.0.5(abc1234)"),
    # a channel the sources do not publish
    ("channel", "grok 1.0.5 (abc1234) [beta]"),
    ("channel", "grok 1.0.5 (abc1234) [STABLE]"),
    ("channel", "grok 1.0.5 (abc1234) stable"),
    ("channel", "grok 1.0.5 (abc1234) [stable] [alpha]"),
    ("channel", "grok 1.0.5 (abc1234)[stable]"),
    # anything extra on the line
    ("extra", "grok 1.0.5 (abc1234) extra"),
    ("extra", "grok 1.0.5 (abc1234) [stable] warning"),
    ("extra", "(1.0.5)"),
    ("extra", "abc1234"),
    ("extra", ""),
    ("extra", "warning: cache is stale"),
)


@pytest.mark.parametrize(
    "category,printed", REFUSED_FORMS,
    ids=[f"{category}-{index}" for index, (category, _) in enumerate(REFUSED_FORMS)])
def test_no_other_shape_is_read_as_the_reviewed_version(tmp_path, category, printed):
    """Zero prompt spawns is the assertion that matters.

    A refusal that still spawned would be no refusal, so every case is checked
    against the child's own spawn log rather than against the receipt alone.
    """
    adapter, _root, log = a_harness(tmp_path, FAKEGROK_VERSION=printed)

    receipt = run_once(adapter, a_request())

    assert receipt.outcome == "failed", f"ACCEPTED[{category}]={printed!r}"
    assert REVIEWED_GROK_VERSION in receipt.detail
    assert _fakegrok.prompt_spawns(log) == [], (
        f"PROMPT_SPAWNED_ON[{category}]={printed!r}")


#: Shapes that cannot travel through an environment variable, so they are put to
#: the parser as the RAW BYTES the transport really hands it. Multiline and
#: non-UTF-8 belong here: `_version_token` reads the first non-empty line and
#: decodes with `errors="replace"`, and both readings must refuse rather than
#: find a version somewhere in the noise.
#: Each carries a VALID commit wherever the noise is not the subject, so a row
#: still refuses for the reason its category names rather than for want of a
#: part that the tightened pattern now requires anyway.
REFUSED_BYTES = (
    ("multiline", b"warning: stale\ngrok 1.0.5 (abc1234)\n"),
    ("multiline", b"grok 1.0.4 (abc1234)\ngrok 1.0.5 (abc1234)\n"),
    ("non-utf8", b"\xff\xfegrok 1.0.5 (abc1234)"),
    ("non-utf8", b"grok \xc3(1.0.5)"),
    ("non-utf8", b"\xef\xbb\xbfgrok 1.0.5 (abc1234)"),
    ("non-utf8", "grok 1.0.5 (abc1234)".encode("utf-16-le")),
    ("control", b"grok 1.0.5 (abc1234)\x00"),
    ("control", b"\x1b[32mgrok 1.0.5 (abc1234)\x1b[0m"),
    ("digits", "grok \u0661.\u0660.\u0665 (abc1234)".encode("utf-8")),
)


@pytest.mark.parametrize(
    "category,raw", REFUSED_BYTES,
    ids=[f"{category}-{index}" for index, (category, _) in enumerate(REFUSED_BYTES)])
def test_no_byte_sequence_outside_the_published_form_is_a_version(
        tmp_path, category, raw):
    """Put to the parser directly, because these cannot pass through an env var.

    A multiline print must not have its version fished out of a later line, and
    a non-UTF-8 print must refuse rather than be repaired into something that
    parses. The answer is a BOOLEAN either way, so nothing derived from these
    bytes can reach a caller.
    """
    adapter, _runner, _exe = _recorded(tmp_path)

    assert adapter._version_matches(raw) is False, (
        f"ACCEPTED_BYTES[{category}]={raw!r}")


def test_the_one_byte_sequence_that_is_the_reviewed_version_is_accepted():
    """The positive control, so the test above cannot pass by refusing everything."""
    exe_free = GrokBuildAdapter.__new__(GrokBuildAdapter)

    assert GrokBuildAdapter._version_matches(
        exe_free, b"grok 1.0.5 (abc1234) [stable]\n") is True


#: A correct first line FOLLOWED by other output. Accepted, and named here rather
#: than left to be discovered: `_version_token` reads the first non-empty line,
#: which is a shared contract all three transports rest on and which this slice
#: did not invent. What matters is the direction -- a banner BEFORE the version is
#: never fished past, which the refusal matrix holds -- and that trailing chatter
#: from a reviewed build does not stop a dispatch it should not stop.
TOLERATED_TRAILING = (
    b"grok 1.0.5 (abc1234)\nsecond line\n",
    b"\n\ngrok 1.0.5 (unknown)\nmore\n",
    b"grok 1.0.5 (abc1234) [stable]\nwarning: cache is stale\n",
)


@pytest.mark.parametrize("raw", TOLERATED_TRAILING)
def test_output_after_a_correct_first_line_does_not_refuse_the_build(raw):
    """The boundary of the shared first-line reading, stated out loud.

    A build that prints the reviewed version and then a warning is still the
    reviewed build. Refusing it would be a false refusal of the kind that made
    this provider undispatchable in the first place, so the tolerance is
    deliberate -- and it is bounded on the side that matters by
    `test_no_byte_sequence_outside_the_published_form_is_a_version`, where a
    banner ahead of the version refuses.
    """
    unbound = GrokBuildAdapter.__new__(GrokBuildAdapter)

    assert GrokBuildAdapter._version_matches(unbound, raw) is True


def test_a_banner_before_the_version_is_never_fished_past(unused=None):
    """The other side of the same boundary, held as its own claim.

    This is the asymmetry: output AFTER a correct first line is tolerated, and
    output BEFORE it is fatal -- because the first non-empty line is the only
    line read, so a warning printed first IS the token.
    """
    unbound = GrokBuildAdapter.__new__(GrokBuildAdapter)

    assert GrokBuildAdapter._version_matches(
        unbound, b"warning: cache is stale\ngrok 1.0.5 (abc1234)\n") is False


def test_an_executable_that_prints_only_a_semver_never_clears_the_preflight():
    """The MAJOR this matrix was rebuilt for, held as one named claim.

    A pattern that made the program name and the commit optional accepted the
    five bytes `1.0.5` -- which is what an arbitrary executable prints when it
    is asked for a version and happens to have one, and which the vendor's entry
    point cannot produce at all. Its row still advertised itself available, so
    this single preflight was the only thing standing between a mistyped or
    substituted pin and a real prompt carrying the operator's instructions, and
    it was not standing.

    Its own positive control is here rather than in another test, because the
    cheap way to pass this one is to refuse everything -- which is the OTHER
    defect this parser has already shipped once.
    """
    unbound = GrokBuildAdapter.__new__(GrokBuildAdapter)

    for printed in CRATE_ONLY_FORMS:
        assert GrokBuildAdapter._version_matches(
            unbound, printed.encode("utf-8")) is False, f"ADMITTED={printed!r}"
    assert GrokBuildAdapter._version_matches(
        unbound, b"grok 1.0.5 (abc1234)\n") is True, "the real form must survive"


def test_a_commit_the_build_script_could_not_have_written_is_not_a_version():
    """The commit is a published alphabet AND a published length range.

    `git rev-parse --short HEAD` writes lowercase hex of 4 to 40 digits -- git
    refuses a `core.abbrev` below 4 and clamps one above the object name, which
    is 40 in this SHA-1 tree -- and the fallback writes `unknown`. Nothing else
    can appear between those parentheses.

    Held separately from the matrix above so the CONTENTS have a claim of their
    own, and its positive control is `_COMMITS` itself rather than a list
    written out again here: that is the published set, it carries both ends of
    the range and the fallback word, and a tightening that narrowed it would
    have to narrow the accepted cross-product too, which is loud.
    """
    unbound = GrokBuildAdapter.__new__(GrokBuildAdapter)

    for commit in UNPUBLISHED_COMMITS:
        printed = f"grok 1.0.5 ({commit})".encode("utf-8")
        assert GrokBuildAdapter._version_matches(unbound, printed) is False, (
            f"ADMITTED_COMMIT={commit!r} (len {len(commit)})")
    for commit in _COMMITS:
        printed = f"grok 1.0.5 ({commit})".encode("utf-8")
        assert GrokBuildAdapter._version_matches(unbound, printed) is True, (
            f"REFUSED_A_PUBLISHED_COMMIT={commit!r} (len {len(commit)})")
    assert {len(commit) for commit in _COMMITS} >= {4, 40}, (
        "the positive controls stopped covering both ends of the range")


def test_a_version_print_the_build_cannot_answer_spawns_zero_prompts(tmp_path):
    adapter, _root, log = a_harness(tmp_path, FAKEGROK_VERSION_FAILS="1")

    receipt = run_once(adapter, a_request())

    assert receipt.outcome == "failed"
    assert "version preflight" in receipt.detail
    assert _fakegrok.prompt_spawns(log) == []


def test_the_reviewed_version_is_proved_before_any_prompt_is_spawned(tmp_path):
    adapter, _root, log = a_harness(tmp_path)

    run_once(adapter, a_request())

    spawns = _fakegrok.spawns(log)
    assert spawns[0]["argv"] == ["--version"], "THE_PREFLIGHT_IS_NOT_FIRST=True"
    assert len(_fakegrok.prompt_spawns(log)) == 1


def test_a_secret_planted_where_a_version_belongs_never_reaches_a_receipt(tmp_path):
    """The observed token is parsed and compared, never reported."""
    adapter, _root, _log = a_harness(tmp_path, FAKEGROK_VERSION=SECRET)

    receipt = run_once(adapter, a_request())

    assert receipt.outcome == "failed"
    assert SECRET not in receipt.detail
    assert SECRET not in str(receipt)


#: A form the vendor really prints, at a version this build never reviewed. It
#: is the ONE input that separates "read the form and declined the version" from
#: "could not read the form at all", because both answer False.
VALID_BUT_UNREVIEWED = "grok 9.9.9 (abc1234) [stable]"


def test_a_valid_form_at_an_unreviewed_version_is_read_and_then_refused(tmp_path):
    """The parse and the comparison are two answers, and both are checked here.

    `_version_matches` is a boolean, and a boolean cannot say WHICH question it
    answered. A parser replaced with one matching NOTHING refuses everything,
    which looks exactly like working correctly -- it passes every refusal case
    in this file and it passed the opt-in smoke too, until the smoke started
    comparing parses instead of reading a yes/no.

    So this asserts the parser READ the published form, that it then declined
    the version, and that no prompt was spawned.
    """
    adapter, _root, log = a_harness(tmp_path, FAKEGROK_VERSION=VALID_BUT_UNREVIEWED)

    receipt = run_once(adapter, a_request())

    printed = (VALID_BUT_UNREVIEWED + "\n").encode("utf-8")
    assert adapter._parsed_version(printed) == "9.9.9", (
        "the parser could not read a form the vendor really prints")
    assert adapter._version_matches(printed) is False
    assert receipt.outcome == "failed"
    assert REVIEWED_GROK_VERSION in receipt.detail
    assert _fakegrok.prompt_spawns(log) == []


def test_the_parser_reads_the_published_form_into_its_semver_alone():
    """The positive control, and the commit and channel are DISCARDED not returned."""
    unbound = GrokBuildAdapter.__new__(GrokBuildAdapter)

    assert GrokBuildAdapter._parsed_version(
        unbound, b"grok 1.0.5 (abc1234) [stable]\n") == "1.0.5"
    assert GrokBuildAdapter._parsed_version(
        unbound, b"grok 1.0.5 (unknown)\n") == "1.0.5"
    assert GrokBuildAdapter._parsed_version(unbound, b"1.0.5\n") is None
    assert GrokBuildAdapter._parsed_version(unbound, b"grok 1.0.5\n") is None
