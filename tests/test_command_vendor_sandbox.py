"""A declared vendor sandbox is worth what the argv spends, and nothing more.

A profile may say a vendor pins `--sandbox workspace-write`. That sentence
reaches a person's screen before they confirm a run, so the only thing that
makes it honest is the command line the transport really builds. These witnesses
read the ARGV -- not the constant the declaration was written from -- because a
declaration and a constant can agree with each other while the launch has moved
away from both.

The three answers are kept apart here too. `None` is an integration that
declares nothing and is not a finding about the vendor; `()` is a measured
absence; pairs are a measured presence. A plugin adapter with no profile at all
lands on the first, and none of this may be read as "no sandbox".
"""
from __future__ import annotations

import pytest

from conductor.command.adapters.claude_code import CLAUDE_PROFILE
from conductor.command.adapters.codex_cli import CODEX_PROFILE

from tests.test_command_codex_transport import a_harness as a_codex
from tests.test_command_claude_transport import a_harness as a_claude


def _declared(profile) -> dict[str, str]:
    return {road: tokens for road, tokens in (profile.vendor_sandbox or ())}


def _dispatch_argv(adapter) -> list[str]:
    """The argv this transport really builds for a dispatch, home and all.

    Both reviewed providers declare the stdin channel, so this is the builder
    their spawn actually calls -- the task never reaches the command line.
    """
    from pathlib import Path

    return list(adapter._stdin_argv(Path("home"), None))


def _review_argv(adapter) -> list[str]:
    from pathlib import Path

    return list(adapter._review_argv(Path("home"), None))


@pytest.mark.parametrize("road,builder", [
    ("dispatch", _dispatch_argv), ("review", _review_argv)])
def test_every_declared_sandbox_road_is_spent_by_that_roads_own_argv(
        tmp_path, road, builder):
    """The condition this whole field exists under.

    The declaration names a road and the tokens that road pins; the argv that
    road builds must carry those tokens, in order, as adjacent words. Read off
    the built command line, so removing the flag from the launch while leaving
    the declaration alone -- which is exactly how a promise goes stale -- fails
    here rather than reaching a screen.
    """
    declared = _declared(CODEX_PROFILE)
    assert road in declared, f"the Codex profile declares no {road} sandbox"
    wanted = declared[road].split()
    argv = builder(a_codex(tmp_path)[0])

    assert any(argv[index:index + len(wanted)] == wanted
               for index in range(len(argv))), (road, wanted, argv)


def test_a_measured_absence_is_declared_and_the_argv_agrees_with_it(tmp_path):
    """The other half, and it is not "no assertion".

    This vendor ships no sandbox flag, so the profile says so with an EMPTY
    declaration -- and the argv is asked too: an integration that declared none
    while the transport quietly pinned one would be understating what runs, and
    a person reading "none" would be reading something false.
    """
    assert CLAUDE_PROFILE.vendor_sandbox == ()
    argv = _dispatch_argv(a_claude(tmp_path)[0])

    assert not [word for word in argv if "sandbox" in word], argv


def test_declaring_nothing_and_declaring_none_are_different_answers():
    """`None` is not `()`, and a screen may not read the first as the second.

    An adapter without a profile -- every plugin in the test roster -- declares
    nothing. That is a fact about this integration, never a finding about the
    vendor, and collapsing the two would turn "we did not look" into "there is
    no sandbox" for every provider nobody has measured.
    """
    from conductor.command.adapters.dsh_harness import DSH_PROFILE
    from conductor.command.adapters.grok_build import GROK_PROFILE
    from conductor.command.adapters.kimi_code import KIMI_PROFILE
    from tests.test_command_adapters import FakeAdapter

    assert getattr(FakeAdapter, "profile", None) is None
    assert CLAUDE_PROFILE.vendor_sandbox is not None
    assert CLAUDE_PROFILE.vendor_sandbox == ()
    assert CODEX_PROFILE.vendor_sandbox
    # And the field's DEFAULT is the first answer, not the second. Three
    # harnesses carry a profile and nobody has measured their vendor for a
    # sandbox; a default of `()` would have made this build claim, for each of
    # them, that their vendor ships none.
    for profile in (DSH_PROFILE, GROK_PROFILE, KIMI_PROFILE):
        assert profile.vendor_sandbox is None, profile.tool_noun


def test_the_declaration_a_real_class_carries_reaches_the_wire_row_itself():
    """The link between the profile and the row, with a REAL adapter class.

    Every other row in this build's roster declares nothing, so a registry that
    had quietly stopped reading the profile would answer `null` everywhere and
    every one of those expectations would still pass. This registers the real
    Codex transport CLASS -- as an unavailable provider, so no instance is built
    and nothing is spawned -- and reads the wire row the Studio route sends.

    The identity values are the module's own published constants; what is under
    test is the DECLARATION, which is read off the class by the door and by
    nothing here.
    """
    from conductor.command.adapters.codex_cli import (
        CODEX_CAPABILITIES, CODEX_DISPLAY_NAME, CODEX_LIFECYCLE, CODEX_PROTOCOL,
        CODEX_PROVIDER_ID, CODEX_SCHEMA_PAIRS, CodexCliTransport,
    )
    from conductor.command.adapters.provider import (
        ProviderCatalogEntry, ProviderRegistry, provider_projection,
    )
    from tests.test_command_provider_registry import PluginAdapter, _entry

    door = ProviderRegistry()
    door.register(ProviderCatalogEntry(
        provider_id=CODEX_PROVIDER_ID, display_name=CODEX_DISPLAY_NAME,
        vendor="OpenAI", protocol=CODEX_PROTOCOL,
        capabilities=CODEX_CAPABILITIES, schema_pairs=CODEX_SCHEMA_PAIRS,
        lifecycle=CODEX_LIFECYCLE, adapter_class=CodexCliTransport),
        availability="executable_absent")
    door.register(_entry(), availability="available", adapter=PluginAdapter())

    rows = {row["provider_id"]: row["vendor_sandbox"]
            for row in provider_projection(door.contracts())}

    assert rows[CODEX_PROVIDER_ID] == [
        [road, tokens] for road, tokens in CODEX_PROFILE.vendor_sandbox]
    assert rows[CODEX_PROVIDER_ID] == [["dispatch", "--sandbox workspace-write"],
                                       ["review", "--sandbox read-only"]]
    # And the class beside it that carries no profile is `null` in the same
    # answer: one projection, two different states, neither borrowed.
    assert rows["plugin"] is None


def test_reading_the_declaration_spawns_nothing_and_asks_no_login():
    """It is read off the CLASS, so a screen costs no process.

    A person opening Confirm may not trigger a version probe, a login question
    or any other vendor call, so the declaration is a class attribute and is
    asked for without constructing a transport.
    """
    from conductor.command.adapters.codex_cli import CodexCliTransport

    declared = CodexCliTransport.profile.vendor_sandbox

    assert declared == CODEX_PROFILE.vendor_sandbox
    assert dict(declared).keys() == {"dispatch", "review"}
