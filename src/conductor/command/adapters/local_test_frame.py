"""Bind a completed local test protocol to the exact independent-check frame."""
from .deep_commands import PATCH_PROFILE
from .independent_check import CheckFrameError
from .local_test_plan import plan_for
from .local_test_receipt import valid_report


def report_for(request, material, *, work_modes=None):
    if request.capability != "dispatch" or request.arguments.get("profile") != PATCH_PROFILE:
        if material.test_report is not None:
            raise CheckFrameError("test_report_refused")
        return None
    try:
        plan = plan_for(material.instruction_document, material.instruction)
        if plan is None:
            if material.test_report is not None:
                raise ValueError("unrequested test protocol")
            return None
        if work_modes is None:
            raise ValueError("missing test tree modes")
        report = valid_report(request, material.test_report, policy=plan,
                              tree=material.after, modes=work_modes)
        if report["policy"] != plan.as_dict():
            raise ValueError("test protocol does not bind the checked tree")
        return report
    except (ValueError, TypeError, KeyError, OSError):
        raise CheckFrameError("test_report_refused") from None


def test_status(report):
    """Only a complete positive test execution can accompany an ACCEPT."""
    if report is None:
        return None
    status = report["status"]
    if status in {"passed", "failed"}:
        return status
    return "unavailable"
