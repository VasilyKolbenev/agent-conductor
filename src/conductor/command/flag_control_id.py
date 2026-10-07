"""The control ids that belong to the continue-after flag (spec 4.3.4, 4.4.4 step 3).

The control the pump writes for a run the flag lists is named `flag-` and 32 hex digits, one name
per (flag, run) (`queue_flag.control_id_of`). A control has no field that says the flag wrote it,
so the name is the mark: the desk reads «continued by the flag» from it. A mark says something
only while nobody else can make it, so the two doors through which a human's control id enters,
the automation control (`PolicyService.control`) and the resume of the queue (`parse_write`),
refuse the shape as `contract_invalid`, and the pump refuses to write it for a queue entry that
already holds it. Ids already in a journal are not judged again: this is a door, not a grammar.

A leaf module on purpose: `queue_flag` builds the name and `policy_service` guards it, and
`queue_flag` cannot be imported from `policy_service` (`queue_reading` imports the one and the
other imports it).
"""
from __future__ import annotations

import re

from .contract_values import ContractError

#: What the pump names its resume of a listed run: this prefix and `HEX_DIGITS` lowercase digits.
PREFIX = "flag-"
HEX_DIGITS = 32
_SHAPE = re.compile(f"{re.escape(PREFIX)}[0-9a-f]{{{HEX_DIGITS}}}")


def is_flag_control_id(control_id: object) -> bool:
    """True for a string that is exactly the shape the flag names its resume by."""
    return type(control_id) is str and _SHAPE.fullmatch(control_id) is not None


def refuse_flag_control_id(control_id: object) -> None:
    """Refuse a control id a human sent when it has the flag's shape.

    Raises:
        ContractError: The id is the shape of the flag's own (the API says `contract_invalid`).
    """
    if is_flag_control_id(control_id):
        raise ContractError("control ids of the shape flag- and 32 hex digits are the "
                            "continue-after flag's own")
