"""What a provider may DECLARE, proved at construction rather than at first spawn.

A ``HarnessProfile`` is code, written once per provider, so every fault in one is
a programming fault. They used to surface at the FIRST SPAWN instead: a malformed
``forced_env`` row reached ``dict()`` inside the transport's spawn and raised a
raw ``ValueError``, which sailed past the provider's own error type and reached a
caller under a sentence blaming the operator's pinned build. A code-owned mistake
reported as an operator's is worse than a crash, because the operator goes looking
at their install.

The relation that matters most is the home. ``home_env`` carries the value this
dispatch MINTS and DISCARDS -- the whole retention promise -- and ``forced_env``
is a set of literals this build sends alongside it. A pair named for ``home_env``
would relocate the child's home away from the minted one, so the tool would write
its config, sessions and credentials somewhere nothing sweeps. That is refused
here, at construction.

The transport also writes the minted home LAST, after unpacking ``forced_env``,
so the promise would hold even if this validation were bypassed. No test can
catch an inversion of that ordering, and deliberately so: construction refuses
the only configuration in which the order could matter. The defence in depth is
therefore documented rather than pinned, and what IS pinned is the refusal.
"""
from __future__ import annotations

import pytest

from conductor.command.adapters.harness_profile import (
    HarnessProfile,
    HeadlessCliError,
)
from conductor.command.providers import PROVIDER_CATALOG

#: Fields every profile below shares; only what a case is about varies.
BASE = dict(
    tool_noun="Probe", task_noun="Probe prompt", display_name="Probe (test)",
    vendor="nobody", docs_url="https://example.invalid/",
    reviewed_version="1.0.0", home_dir=".probe-home",
    marker_dir=".probe-marker", home_env="PROBE_HOME",
    version_argv=("--version",), exit_codes_published=False,
    home_id_kind="probe-home")


def a_profile(**changes) -> HarnessProfile:
    values = {**BASE, "forced_env": ()}
    values.update(changes)
    return HarnessProfile(**values)


def test_a_profile_that_declares_nothing_unusual_is_accepted():
    """The happy path, so every refusal below is about what it names."""
    profile = a_profile(forced_env=(("PROBE_TELEMETRY", "0"),))

    assert profile.forced_env == (("PROBE_TELEMETRY", "0"),)
    assert profile.home_env == "PROBE_HOME"


def test_forcing_the_home_variable_is_refused_because_it_would_relocate_the_home():
    """The one that would break the retention promise outright.

    A pair named for ``home_env`` overwrites the home this dispatch minted and
    discards, so the tool writes its config, sessions and credentials into a
    directory nothing sweeps -- and the receipt still says the home was taken
    back, because as far as the transport knows it discarded the one it made.
    """
    with pytest.raises(HeadlessCliError, match="relocate the child's home"):
        a_profile(forced_env=(("PROBE_HOME", "/somewhere/else"),))


def test_a_variable_forced_twice_is_refused_rather_than_silently_collapsed():
    """``dict()`` would keep the last and lose the first, saying nothing."""
    with pytest.raises(HeadlessCliError, match="forced twice"):
        a_profile(forced_env=(("PROBE_TELEMETRY", "0"), ("PROBE_TELEMETRY", "1")))


@pytest.mark.parametrize("name", ("", "9LEADING", "HAS-DASH", "HAS SPACE", "a=b"))
def test_a_forced_name_that_is_not_an_environment_variable_is_refused(name):
    with pytest.raises(HeadlessCliError, match="environment variable name"):
        a_profile(forced_env=((name, "0"),))


def test_a_home_variable_that_is_not_an_environment_variable_is_refused():
    with pytest.raises(HeadlessCliError, match="environment variable name"):
        a_profile(home_env="not a name")


@pytest.mark.parametrize("value", ("has\x00nul", 0, None, ("0",)))
def test_a_forced_value_that_is_not_nul_free_text_is_refused(value):
    with pytest.raises(HeadlessCliError, match="NUL-free text"):
        a_profile(forced_env=(("PROBE_TELEMETRY", value),))


@pytest.mark.parametrize("row", (
    ("ONLY_ONE",), ("A", "0", "extra"), "AB", ["A", "0"], None))
def test_a_row_that_is_not_a_name_value_pair_is_refused(row):
    """This is the shape that used to reach the first spawn as a ValueError."""
    with pytest.raises(HeadlessCliError, match="\\(name, value\\) pair"):
        a_profile(forced_env=(row,))


def test_every_catalogued_provider_carries_a_profile_this_module_would_accept():
    """The rules above are worth nothing if no shipped provider is held to them.

    Each catalogued transport's profile was built at import time, so it already
    passed; re-validating it here is what stops a future provider from being the
    one case nobody checked, and it fails at collection rather than at a spawn.
    """
    checked = 0
    for provider_id, entry in PROVIDER_CATALOG.items():
        profile = getattr(entry.adapter_class, "profile", None)
        if profile is None:
            continue  # a fixture adapter declares no transport profile
        rebuilt = HarnessProfile(**{
            field: getattr(profile, field)
            for field in profile.__dataclass_fields__})
        assert rebuilt == profile, f"{provider_id}'s profile did not survive a rebuild"
        assert profile.home_env not in dict(profile.forced_env), (
            f"{provider_id} forces its own home variable")
        checked += 1
    assert checked >= 3, f"only {checked} profiles were checked, so this proved little"
