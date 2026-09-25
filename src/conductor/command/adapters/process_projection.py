"""Pure command argument and outcome projection, injected with the validated spec factory."""
from __future__ import annotations

from collections.abc import Mapping
from ..dispatch import DispatchArgumentError, validate_dispatch_arguments
from .base import AdapterContractError


def _spec_from_arguments(
        arguments: Mapping[str, object], timeout_seconds: int, spec_type, default_limit, spec_error):
    """Read a dispatch request's structured command; refuse a malformed one."""
    if not isinstance(arguments, Mapping):
        raise AdapterContractError("dispatch arguments must be a JSON object")
    try:
        validate_dispatch_arguments(arguments)
        return spec_type(
            argv=arguments.get("argv"),
            cwd=arguments.get("cwd"),
            env_allow=arguments.get("env_allow", ()),
            output_limit=arguments.get("output_limit", default_limit),
            timeout_seconds=timeout_seconds)
    except (spec_error, DispatchArgumentError, TypeError, ValueError) as e:
        raise AdapterContractError(
            f"dispatch arguments are not a valid command: {e}") from e


def _payload_from_spec(spec: CommandSpec) -> dict[str, object]:
    """The adapter payload: a plain-JSON echo of the validated command."""
    return {
        "argv": list(spec.argv), "cwd": spec.cwd,
        "env_allow": list(spec.env_allow),
        "output_limit": spec.output_limit,
    }


def _spec_from_payload(payload: Mapping[str, object], timeout_seconds: int, spec_type, spec_error):
    return spec_type(
        argv=tuple(payload["argv"]), cwd=payload["cwd"],
        env_allow=payload["env_allow"],
        output_limit=payload["output_limit"], timeout_seconds=timeout_seconds)


def _detail(outcome: ProcessOutcome, summary: str) -> str:
    note = f"{summary}; captured {len(outcome.output)} bytes"
    if outcome.output_truncated:
        note += f", truncated at the {outcome.output_limit}-byte capture bound"
    return note


def _map_outcome(outcome, incomplete_state) -> tuple[str, str]:
    """Project a process outcome onto the receipt vocabulary; timeout is not success.

    Undelivered input is checked inside the ``completed`` arm rather than ahead
    of everything, so a timeout stays a timeout and a stop stays a cancellation:
    those two already say the run did not succeed, and overwriting them would
    trade one true fact for another. What may never happen is a ZERO becoming a
    success while the child never received what it was meant to act on.
    """
    if outcome.status == "completed":
        if outcome.exit_code == 0:
            if outcome.stdin_state == incomplete_state:
                return "failed", _detail(
                    outcome,
                    "the process exited zero, but the input it was to act on "
                    "was never delivered whole, so the zero answers a question "
                    "this build never finished asking")
            return "succeeded", _detail(outcome, "the process exited zero")
        return "failed", _detail(outcome, f"the process exited {outcome.exit_code}")
    if outcome.status == "timed_out":
        return "failed", _detail(
            outcome, "the process exceeded its timeout and was terminated")
    if outcome.status == "stopped":
        return "cancelled", _detail(outcome, "the process was stopped by the runner")
    raise AdapterContractError(f"unknown process status {outcome.status!r}")
