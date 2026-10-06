"""No product text says that the boot environment GUID never changes or that its time is an install.

A review ruling (05.10) found both statements unestablished: that the old Windows boot identifier
never changes, and that the time inside its UUID is the time of an installation or a setup. What is
established is narrower: a record that holds only that identifier cannot prove a restart, and the
counter is compared only inside one environment. The product says that and nothing more.

The scan reads the boot and ownership modules, the two other callers of the old identifier, the hub
copy and the first-run pages (both languages). Comment markers and line breaks are folded first,
because the claim that was found was split across two docstring lines. The patterns find the
phrasings known so far; they do not prove that no other phrasing exists.
"""
from __future__ import annotations

from pathlib import Path
import re

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCES = (
    sorted((ROOT / "src" / "conductor").glob("boot_*.py"))
    + sorted((ROOT / "src" / "conductor").glob("ownership*.py"))
    + [ROOT / "src" / "conductor" / "hub" / "clone.py",
       ROOT / "src" / "conductor" / "command" / "adapters" / "process_acl.py",
       ROOT / "src" / "conductor" / "panel" / "hub-copy.js",
       ROOT / "docs" / "first-run-v1.md", ROOT / "docs" / "first-run-v1.en.md"])

_IDENTIFIER = r"(?:guid|uuid(?:v\d)?|\bid\b|boot ?identifier|boot id|class[- ]?90|идентификатор)"
_NEVER = r"(?:never|does not|doesn't|do not|cannot|stays the same|remains the same)"
CLAIMS = {
    "the identifier never changes": re.compile(
        rf"{_IDENTIFIER}\b[^.;]{{0,100}}\b{_NEVER}\s+"
        r"(?:change|changes|vary|varies|differ|differs)\b"
        r"|\bnever (?:changes|varies|differs)\b[^.;]{0,60}\b(?:across|between|on) "
        r"(?:every |each |any )?(?:boot|restart|reboot)",
        re.IGNORECASE),
    "its time is the time of an install or a setup": re.compile(
        rf"{_IDENTIFIER}\b[^.;]{{0,120}}\b(?:time|timestamp|stamp)\b[^.;]{{0,80}}"
        r"\b(?:install|installation|setup|set-up)\b"
        r"|\b(?:install|installation|setup|set-up)(?: |-)(?:time|stamp)\b[^.;]{0,80}"
        rf"{_IDENTIFIER}",
        re.IGNORECASE),
    "по-русски: идентификатор не меняется или это время установки": re.compile(
        r"(?:guid|uuid|идентификатор)[^.;]{0,100}(?:никогда не меня|не меняется|не изменяется)"
        r"|(?:guid|uuid)[^.;]{0,120}(?:время установки|время настройки)",
        re.IGNORECASE),
}
#: The phrasings of the review and of the docstring this file replaced, as the scan sees them.
#: They are inputs of the detector, quoted so that it can be shown to find them; none is asserted.
KNOWN = (
    "`legacy` is the old Windows string (`windows:<uuid>`): it can be read, but it never "
    "proves anything, because the id it holds does not change with a boot.",
    "The GUID is a UUIDv1: its time field decodes to 2025-12-25 15:26:26, a setup-time stamp.",
    "It is a UUIDv1 whose time field decodes to 2025-12-25, a setup-time stamp.",
    "UUID time is the install time of the machine",
    "the old boot GUID never changes",
    "the boot identifier never changes across a restart",
)
#: Sentences that say what is established and must never trip the scan.
FINE = (
    "the boot has not changed since the record was written, so the OS has not restarted",
    "a record that holds only the old identifier cannot prove a restart",
    "the environment GUID is the scope: counters of different environments are not comparable",
    "a legacy boot value cannot prove a restart, whatever the other side holds",
    "restart the OS (do a full Restart, not a shutdown) and try again",
)


def flatten(text: str) -> str:
    """The text with comment markers, quotes and line breaks folded into single spaces."""
    return re.sub(r"[\s#*>`\"']+", " ", text)


@pytest.mark.parametrize("sentence", KNOWN)
def test_the_scan_finds_each_phrasing_of_the_two_claims_it_exists_for(sentence):
    folded = flatten(sentence)
    assert any(pattern.search(folded) for pattern in CLAIMS.values()), sentence


def test_the_scan_finds_a_claim_split_across_two_lines_of_a_docstring():
    split = '"""it proves nothing, because the id it holds does\nnot change with a boot.\n'
    assert any(pattern.search(flatten(split)) for pattern in CLAIMS.values())


@pytest.mark.parametrize("sentence", FINE)
def test_the_scan_leaves_alone_what_the_product_may_say(sentence):
    assert not [name for name, pattern in CLAIMS.items() if pattern.search(flatten(sentence))]


@pytest.mark.parametrize("path", SOURCES, ids=lambda path: path.name)
def test_no_product_text_claims_the_guid_never_changes_or_dates_from_an_install(path):
    folded = flatten(path.read_text(encoding="utf-8"))
    found = [(name, hit.group(0)) for name, pattern in CLAIMS.items()
             for hit in pattern.finditer(folded)]
    assert not found, f"{path.name}: {found}"


def test_the_scan_reads_the_files_it_names():
    assert len(SOURCES) >= 12 and all(path.is_file() for path in SOURCES)
