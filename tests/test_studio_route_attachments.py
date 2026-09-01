"""What the inspector may honestly claim about a step's attachments.

Split out of ``test_studio_completeness`` when that module crossed the line cap.
It is a real circuit rather than a convenient line: the census next door asks
whether every FIELD on the six sections is finished, and this asks whether one
finished field's SENTENCES are true -- which is a different question with a
different owner. The vocabulary and the mechanism both belong to
``conductor.command.containment``, and every assertion here is read out of that
module rather than written down beside the screen.

The rule this file exists to keep is narrow and absolute: on Windows this build
has no operating-system isolation of any kind, and the word `sandbox` -- which
is the contract's own kind name and cannot be renamed without moving every
shipped document -- must never be allowed to imply that it does. What the
product really has is a structural route walk, and the screen says so in the
walk's own words: `os.lstat` from the project root, refusing a symlink, a
junction, a reparse point, a hard link, or anything not strictly beneath it,
with the two things that walk cannot see stated beside it.

The five kinds this build does not spend get the other half of the same rule.
They are recorded and inert, the screen says exactly that, and the census here
is what stops the sentence quietly becoming false when one of them grows a
consumer.
"""
from __future__ import annotations

import re

from conductor.command.graph_definition import RESOURCE_KINDS
from tests.test_studio_canvas import INSPECTOR, ROOT, _code, _text



def _sentences() -> str:
    """The route section's prose, joined the way a reader sees it.

    A JS string long enough to say something true is written across several
    source lines, so every assertion below would otherwise be about where the
    concatenation happens to fall rather than about what the screen says. The
    joins are removed and the sentences are read whole.
    """
    inspector = _code(*INSPECTOR)
    body = re.search(r"function routeAttachments\(box, form\) \{(.*?)\n\}",
                     inspector, re.DOTALL).group(1)
    return re.sub(r'"\s*\n\s*\+ "', "", body)


def test_the_route_control_offers_the_words_the_python_layer_owns():
    """`containment.SANDBOX_ROUTES`, read out of the layer that enforces it.

    A window offering a second route would offer a plan the run-open door
    refuses; one that dropped `project-root` would make every shipped starter
    unopenable. Both directions.
    """
    from conductor.command.containment import SANDBOX_ROUTES

    inspector = _code(*INSPECTOR)
    declared = re.search(
        r"export const SANDBOX_ROUTES = Object\.freeze\(\[(.*?)\]\)",
        inspector, re.DOTALL).group(1)

    assert set(re.findall(r'"([a-z-]+)"', declared)) == set(SANDBOX_ROUTES)


def test_the_screen_states_the_mechanism_in_the_words_that_enforce_it():
    """What `project-root` BUYS, named as the walk rather than as a promise.

    The refusals listed on screen are ones `containment.RouteViolationCode`
    really carries, so a person reading the sentence is reading this build's
    own door rather than a description of one.
    """
    said = _sentences()

    assert "ROUTE CONTAINMENT" in said, said
    assert "walked from the project root" in said, said
    for refusal in ("symlink", "junction", "reparse point", "hard link",
                    "strictly beneath the root"):
        assert refusal in said, refusal
    assert "refused before anything is spawned" in said, said
    assert "when the run is opened" in said, said
    assert "when an attempt is authorized" in said, said
    assert "routeAttachments(box, form);" in _code(*INSPECTOR)


def test_the_screen_never_claims_an_isolation_this_build_does_not_have():
    """The Windows-honesty rule, asserted in both directions.

    The word `sandbox` may appear -- it is the contract's own kind name -- but
    never as a claim of OS isolation. What is REQUIRED is the disclaimer, and
    the two things `containment`'s own docstring puts outside its door.
    """
    said = _sentences()

    assert "NOT operating-system isolation" in said, said
    assert "no privilege drop and no filesystem jail" in said, said
    assert "alternate data stream" in said, said
    assert "at the instant it walks it" in said, said
    # And the words a screen would reach for if it were claiming more than this
    # build has. `sandbox` is not among them: it is the contract's own kind
    # name, and the sentences above are what stop it being read as a promise.
    for lie in ("isolated", "jailed", "container", "virtual machine",
                "chroot", "namespace"):
        assert lie not in said.lower(), lie


def test_the_five_kinds_this_build_does_not_spend_are_said_to_be_inert():
    """The census, and it is what stops the sentence quietly becoming false.

    The screen states that five of the six kinds change nothing. That is
    checked against the CONTRACT's own vocabulary rather than a list typed
    here, so a seventh kind arriving without a sentence reds -- and the second
    assertion holds the claim itself, because a kind that grew a consumer while
    the screen still called it inert is the lie this whole slice removes.
    """
    from conductor.command.containment import SANDBOX_KIND

    said = _sentences()
    inert = sorted(RESOURCE_KINDS - {SANDBOX_KIND})

    assert len(inert) == 5, inert
    assert "The other five kinds" in said, said
    for kind in inert:
        assert kind in said, kind
    assert "does nothing else with them" in said, said
    # The one reader really is keyed on the one kind. If it stopped filtering,
    # the five would start being judged and the sentence above would be false
    # without anyone editing the file it is written in.
    walk = _text(ROOT / "src" / "conductor" / "command" / "containment.py")
    assert "kind != SANDBOX_KIND" in walk, (
        "the one reader stopped filtering on the one kind, so the five "
        "the screen calls inert are being judged")
