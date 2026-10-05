"""Boot-measurement stand-ins for the ownership tests: one seam, any platform.

A recovery test needs "the machine restarted". The product asks one question, "what is the boot
measurement now" (`ownership_boot.current_boot`), so a test answers it here and nowhere else.
"""
from __future__ import annotations

import uuid

from conductor import boot_witness

GUID = "13de2a5e-e1a6-11f0-aee0-91aa266ec2fd"
OTHER_GUID = "00000000-1111-4222-8333-444444444444"


def counter(value, scope=GUID):
    """The new Windows witness text for a counter value."""
    return boot_witness.counter_text(scope, value)


def later_boot(recorded):
    """A measurement taken after a restart, of the same scheme as `recorded`."""
    found = boot_witness.parse(recorded)
    if found.kind == "counter":
        return boot_witness.counter_text(found.scope, found.counter + 1)
    return f"{found.scheme}:{uuid.uuid4()}"


# What the OS does with the counter across sleep, hibernate and a Fast Startup shutdown is not
# measured yet, so no product text may state it as fact.
UNMEASURED_CLAIMS = ("sleep", "hibernat", "fast startup", "keep the same boot")


def assert_plain_restart_advice(text):
    """The text advises a full Restart and says nothing about how other power states act."""
    lowered = text.lower()
    assert "full restart" in lowered, f"no plain advice to do a full Restart in: {text!r}"
    found = [word for word in UNMEASURED_CLAIMS if word in lowered]
    assert not found, f"states unmeasured OS behaviour {found} in: {text!r}"


def measure(monkeypatch, value):
    """From now on the product measures `value`; a callable is asked every time."""
    from conductor import ownership_boot
    monkeypatch.setattr(ownership_boot, "current_boot",
                        value if callable(value) else (lambda: value))
