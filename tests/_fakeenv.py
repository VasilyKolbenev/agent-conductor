"""What a fake child may honestly say about the environment it was handed.

The four native-pin suites used to assert that the child's environment held
EXACTLY the names this build put there. That reads like the strongest possible
statement and is not a statement about this build at all: on POSIX the Python
runtime adds ``LC_CTYPE`` on the far side of the interpreter, and macOS adds
``__CF_USER_TEXT_ENCODING`` with it. ``ProcessRunner`` never passed either.
So the equality was measuring the interpreter's own startup, and it failed on
Linux and macOS for a reason that has nothing to do with containment.

The question those tests meant to ask is narrower and answerable: **did anything
of the parent's reach the child?** So the parent plants ONE token, and the child
reports whether it arrived -- by NAME or by VALUE, because a copied environment
leaks through both channels and a scan of one would miss the other.

**No value is ever recorded.** A pin may legitimately allow a real credential
through, and these logs are test artefacts that nothing sweeps; a log holding
values would hold a live key on any machine that has one. The child answers with
two booleans and nothing else.

The token is a CONSTANT shared by both sides rather than something handed over
at spawn time. A knob carrying it would be found by the child's own scan, and
the answer would be yes for a reason that proves nothing.
"""
from __future__ import annotations

import os
from collections.abc import Mapping

#: The one token this suite plants in a parent environment to prove it reaches
#: no child. Shaped as a valid environment NAME so the same string can be
#: planted in both channels, and long enough that finding it anywhere is proof
#: rather than coincidence.
ENV_PROBE = "CONDUCT_ENV_PROBE_" + "7F" * 16


def probe_report(environ: Mapping[str, str] | None = None) -> dict[str, bool]:
    """Whether the probe reached this process, as two booleans and no content.

    Both channels are scanned WITHOUT exception -- including this fake's own
    knobs, because the token is never carried in one, so nothing here needs an
    exemption and none is granted.
    """
    live = os.environ if environ is None else environ
    return {
        "in_names": any(ENV_PROBE in name for name in live),
        "in_values": any(ENV_PROBE in value for value in live.values()),
    }


#: What a clean spawn answers. Named once so four suites cannot drift on it.
NO_PROBE = {"in_names": False, "in_values": False}
