"""The hub runs the owner commands as a person would, and believes only what it can prove.

The runner starts `python -m conductor ownership recover | recover-login` and `providers
--from-profile` in a session of its own; the parsers read the one JSON object a success prints and
the FIRST line of a refusal, and nothing else. The table that tells four kinds of recovery refusal
apart is pinned from both sides: the hub's reading of each sentence here, and the real sentence
builders of the two recoveries below, so a rewording of the command cannot leave this table
reading a stale copy.
"""
from __future__ import annotations

import ast
import importlib
import json
import os
import subprocess
import sys
import threading
from pathlib import Path

import pytest

from conductor import boot_witness
from conductor.hub import refusals


@pytest.fixture
def owner_ops():
    """The module under test, imported when a test runs (so a missing module fails that test)."""
    from conductor.hub import owner_ops as module
    return module


class Finished:
    def __init__(self, code):
        self.returncode = code

    def poll(self):
        return self.returncode


def fake(out="", err="", code=0, seen=None):
    def launch(argv, **kwargs):
        if seen is not None:
            seen.append((argv, kwargs))
        kwargs["stdout"].write(out.encode("utf-8"))
        kwargs["stderr"].write(err.encode("utf-8"))
        return Finished(code)
    return launch


class Held:
    """A command that has started and keeps running until a test releases it.

    A real `Popen` returns at once and the command runs on; this one does the same, so a test
    can act (close the hub, ask for a second operation) while the command is still running.
    """

    def __init__(self, out="", err="", code=0):
        self.release, self.entered, self.started = threading.Event(), threading.Event(), []
        self._launch = fake(out=out, err=err, code=code)

    def __call__(self, argv, **kwargs):
        self.started.append(argv)
        process = self._launch(argv, **kwargs)
        self.entered.set()
        return _Running(process, self.release)


class _Running:
    def __init__(self, process, release):
        self._process, self._release = process, release

    def poll(self):
        return self._process.poll() if self._release.is_set() else None

    @property
    def returncode(self):
        return self._process.returncode


def test_a_command_starts_in_a_session_or_group_of_its_own_with_the_hubs_home_in_its_environment(
        owner_ops, tmp_path):
    seen = []
    ran = owner_ops.run_command(["ownership", "recover", "--dir", "X"], home=tmp_path,
                                popen=fake(seen=seen), policy=lambda: "none")
    ((argv, kwargs),) = seen
    assert argv[:3] == [sys.executable, "-m", "conductor"]
    assert argv[3:] == ["ownership", "recover", "--dir", "X"]
    assert kwargs["cwd"] == tmp_path and kwargs["stdin"] == subprocess.DEVNULL
    assert kwargs["env"]["CONDUCT_HOME"] == str(tmp_path)
    assert kwargs["env"]["PYTHONIOENCODING"] == "utf-8"
    if os.name == "nt":
        assert kwargs["creationflags"] & subprocess.CREATE_NEW_PROCESS_GROUP
        assert not kwargs["creationflags"] & 0x01000000          # no breakaway for policy none
    else:
        assert kwargs["start_new_session"] is True
    assert ran.code == 0 and list(tmp_path.iterdir()) == []      # temp files are gone


@pytest.mark.parametrize("policy", ["none", "breakaway"])
def test_only_a_job_that_lets_a_child_leave_adds_the_breakaway_flag(owner_ops, tmp_path, policy):
    seen = []
    owner_ops.run_command(["x"], home=tmp_path, popen=fake(seen=seen), policy=lambda: policy)
    ((_, kwargs),) = seen
    if os.name == "nt":
        assert bool(kwargs["creationflags"] & 0x01000000) is (policy == "breakaway")
    else:
        assert kwargs["start_new_session"] is True


@pytest.mark.parametrize("policy", ["kill_on_close", "a_word_nobody_defined"])
def test_a_job_that_would_end_the_command_with_the_hub_refuses_before_starting_it(
        owner_ops, tmp_path, policy):
    started = []
    ran = owner_ops.run_command(["x"], home=tmp_path, popen=fake(seen=started),
                                policy=lambda: policy)
    assert started == [] and ran.code != 0 and list(tmp_path.iterdir()) == []


def test_a_command_the_os_cannot_start_is_a_failed_run_and_leaves_no_file(owner_ops, tmp_path):
    def refuse(_argv, **_kwargs):
        raise FileNotFoundError("no such program")

    ran = owner_ops.run_command(["x"], home=tmp_path, popen=refuse, policy=lambda: "none")
    assert (ran.code, ran.out, ran.error) == (1, "", "") and list(tmp_path.iterdir()) == []


def test_what_a_command_wrote_comes_back_as_utf8_text_with_its_exit_code(owner_ops, tmp_path):
    text = json.dumps({"phase": "recovered", "folder": "проект"}, ensure_ascii=False)
    ran = owner_ops.run_command(["x"], home=tmp_path, popen=fake(out=text, err="owner_busy: х\n",
                                code=1), policy=lambda: "none")
    assert (ran.code, ran.out, ran.error) == (1, text, "owner_busy: х\n")


@pytest.mark.parametrize(("text", "step", "code"), [
    ("recovery_required: restart the OS\n", "recover", "recovery_required"),
    ("recovery_refused: nothing\n", "recover", "recovery_refused"),
    ("recovery_refused: no newline at the end", "recover", "recovery_refused"),
    ("recovery_refused: a windows line end\r\n", "recover", "recovery_refused"),
    ("transition_conflict: x\n", "recover", "transition_conflict"),
    ("ownership_lost: x\n", "recover", "ownership_lost"),
    ("login_recovery_required: x\n", "recover_login", "login_recovery_required"),
    ("login_owner_busy: x\n", "recover_login", "login_owner_busy"),
    ("login_ownership_invalid: x\n", "recover_login", "login_ownership_invalid"),
    ("login_context_required: x\n", "recover_login", "login_context_required"),
    ("profile_absent: x\n", "providers", "profile_absent"),
    ("profile_invalid: x\n", "providers", "profile_invalid"),
    ("owner_busy: x\n", "providers", "owner_busy")])
def test_a_refusal_is_the_code_the_command_printed_when_the_step_lists_it(
        owner_ops, text, step, code):
    allowed = refusals.OPERATION_CODES_BY_STEP[step]
    assert owner_ops.refusal_code(text, allowed) == code


@pytest.mark.parametrize("text", [
    "", "Traceback (most recent call last):\n", "recovery_required:\n", "RECOVERY: x\n",
    "owner_busy: x\n", "conduct_home_invalid: x\n", "unknown_code: x\n", "\nrecovery_refused: x\n",
    "recovery_refused:  two spaces\n", " recovery_refused: x\n", "login_recovery_required: x\n"])
def test_anything_else_is_subprocess_failed_and_names_no_text_of_the_command(owner_ops, text):
    allowed = refusals.OPERATION_CODES_BY_STEP["recover"]
    assert owner_ops.refusal_code(text, allowed) == "subprocess_failed"


def test_only_the_first_line_of_the_error_decides(owner_ops):
    allowed = refusals.OPERATION_CODES_BY_STEP["recover"]
    assert owner_ops.refusal_code("noise\nrecovery_refused: x\n", allowed) == "subprocess_failed"
    assert owner_ops.refusal_code("recovery_refused: x\nnoise\n", allowed) == "recovery_refused"


# The top code stays `subprocess_failed`; the typed reason is kept beside it.
def test_a_typed_recovery_reason_is_kept_beside_subprocess_failed_and_nothing_else_is(owner_ops):
    providers = refusals.OPERATION_CODES_BY_STEP["providers"]
    text = "recovery_required: previous owner did not close\n"
    assert owner_ops.refusal_code(text, providers) == "subprocess_failed"
    assert owner_ops.recovery_reason(text, providers) == "recovery_required"
    # a step that lists the word as its own code needs no detail: the code already says it
    assert owner_ops.recovery_reason(text, refusals.OPERATION_CODES_BY_STEP["recover"]) is None
    for other in ("", "noise\n" + text, "owner_busy: x\n", "Traceback (most recent call last):\n",
                  "recovery_required:\n", "profile_invalid: recovery_required\n",
                  "restart_needed: x\n"):
        assert owner_ops.recovery_reason(other, providers) is None
    assert owner_ops.recovery_reason(text, providers) in refusals.OPERATION_DETAIL_REASONS


# The two recover steps list their restart-family code as their OWN code, so `recovery_reason`
# gives them nothing; `restart_reason` tells four situations apart by the sentence after the code.
# The sentences below are the ones the command prints today; the test over the real sentence
# builders further down pins them, so a rewording cannot leave this table on a stale copy.
SAME_BOOT = ("recovery_required: restart the OS before recovering an uncertain writer session "
             "(do a full Restart, not a shutdown)\n")
LEGACY = ("recovery_required: the abandoned record predates the boot counter and cannot prove a "
          "restart; run `ownership recover --prepare-restart`, restart the OS (a full Restart, "
          "not a shutdown), then run `ownership recover` again\n")
OTHER_ENVIRONMENT = ("recovery_required: no restart is proven: the recorded boot environment is "
                     "not the current one. Another Restart does not make the old environment "
                     "the current one: run `ownership recover --prepare-restart` to prepare in "
                     "the current boot environment, do a full Restart, then run "
                     "`ownership recover` again\n")
UNMEASURED = ("recovery_required: the OS boot cannot be measured, so no restart can be proven: "
              "x\n")
NOT_PROVEN = "recovery_required: no restart is proven: the boot counter did not rise\n"
REWORDED = "recovery_required: a sentence a later build words differently\n"
LOGIN_SAME_BOOT = ("login_recovery_required: restart the OS before recovering the shared login "
                   "lease (do a full Restart, not a shutdown)\n")
LOGIN_LEGACY = ("login_recovery_required: the lease predates the boot counter and cannot prove a "
                "restart; run `ownership recover-login --prepare-restart`, restart the OS (a "
                "full Restart, not a shutdown), then run `ownership recover-login` again\n")
LOGIN_OTHER = OTHER_ENVIRONMENT.replace("recovery_required:", "login_recovery_required:", 1
                                        ).replace("ownership recover", "ownership recover-login")


@pytest.mark.parametrize(("step", "text", "word"), [
    ("recover", SAME_BOOT, "restart_needed"), ("recover", LEGACY, "prepare_needed"),
    ("recover", OTHER_ENVIRONMENT, "other_environment"), ("recover", UNMEASURED, "not_proven"),
    ("recover", NOT_PROVEN, "not_proven"), ("recover", REWORDED, "not_proven"),
    ("recover_login", LOGIN_SAME_BOOT, "restart_needed"),
    ("recover_login", LOGIN_LEGACY, "prepare_needed"),
    ("recover_login", LOGIN_OTHER, "other_environment"),
    ("recover_login", "login_recovery_required: a sentence nobody knows\n", "not_proven")])
def test_a_restart_family_refusal_is_told_apart_by_its_sentence_and_defaults_to_the_neutral_word(
        owner_ops, step, text, word):
    assert owner_ops.restart_reason(text, step) == word
    assert word in refusals.OPERATION_DETAIL_REASONS


@pytest.mark.parametrize(("step", "text"), [
    ("recover", "recovery_refused: nothing\n"), ("recover", LOGIN_SAME_BOOT),
    ("recover_login", SAME_BOOT), ("providers", SAME_BOOT), ("recover", ""),
    ("recover", "Traceback (most recent call last):\n"), ("recover", "recovery_required:\n"),
    ("recover", "noise\n" + SAME_BOOT), ("no_such_step", SAME_BOOT)])
def test_anything_that_is_not_the_restart_code_of_its_step_on_its_first_line_has_no_reason(
        owner_ops, step, text):
    assert owner_ops.restart_reason(text, step) is None


def test_the_reason_never_holds_a_word_of_the_command_beyond_the_closed_four(owner_ops):
    for text in (SAME_BOOT, LEGACY, OTHER_ENVIRONMENT, UNMEASURED, NOT_PROVEN, REWORDED):
        found = owner_ops.restart_reason(text, "recover")
        assert found in {"restart_needed", "prepare_needed", "other_environment", "not_proven"}


#: What the boot witness refuses with, and whether the record is the old Windows string: the three
#: arguments of `_not_proven` in both recoveries, with the word the hub must read from the result.
REAL_CASES = [("same_boot", False, "restart_needed"), ("same_boot", True, "restart_needed"),
              ("other_scope", False, "other_environment"),
              ("other_scope", True, "other_environment"),
              ("legacy_value", True, "prepare_needed"),
              ("counter_decreased", True, "prepare_needed"),
              ("counter_decreased", False, "not_proven"),
              ("native_unavailable", False, "not_proven")]


@pytest.mark.parametrize(("step", "module"), [("recover", "ownership_transition"),
                                              ("recover_login", "ownership_login")])
@pytest.mark.parametrize(("boot_code", "legacy", "word"), REAL_CASES)
def test_the_stem_table_reads_the_sentences_the_real_recoveries_print(
        owner_ops, step, module, boot_code, legacy, word):
    real = importlib.import_module(f"conductor.{module}")
    refusal = real._not_proven(boot_witness.BootRefused(boot_code, "a detail of the reader"),
                               legacy)
    printed = str(refusal) + "\n"                    # `ownership_command` prints exactly this
    assert owner_ops.restart_reason(printed, step) == word
    assert owner_ops.refusal_code(printed, refusals.OPERATION_CODES_BY_STEP[step]) == (
        refusal.code)


@pytest.mark.parametrize(("step", "module"), [("recover", "ownership_transition"),
                                              ("recover_login", "ownership_login")])
def test_a_legacy_record_and_another_environment_never_read_as_a_bare_restart(
        owner_ops, step, module):
    real = importlib.import_module(f"conductor.{module}")
    words = {}
    for name, (boot_code, legacy) in {"legacy": ("counter_decreased", True),
                                      "other": ("other_scope", False),
                                      "same": ("same_boot", False),
                                      "unproven": ("counter_decreased", False)}.items():
        refusal = real._not_proven(boot_witness.BootRefused(boot_code, "a detail"), legacy)
        words[name] = owner_ops.restart_reason(str(refusal), step)
    assert words == {"legacy": "prepare_needed", "other": "other_environment",
                     "same": "restart_needed", "unproven": "not_proven"}


def test_success_needs_the_one_json_object_of_the_command_with_its_own_word(owner_ops):
    assert owner_ops.recovered_head(json.dumps({"phase": "recovered", "generation": 4}) + "\n")
    assert not owner_ops.recovered_head(json.dumps({"phase": "closed"}))
    assert not owner_ops.recovered_head(json.dumps({"state": "recovered"}))
    assert not owner_ops.recovered_head("not json")
    assert not owner_ops.recovered_head("")
    assert not owner_ops.recovered_head(json.dumps(["recovered"]))
    assert not owner_ops.recovered_head(json.dumps({"phase": "recovered"}) + "\n{}\n")
    assert owner_ops.recovered_login(json.dumps({"state": "recovered", "resource": "sha256:ab"}))
    assert not owner_ops.recovered_login(json.dumps({"state": "x"}))
    assert not owner_ops.recovered_login(json.dumps({"phase": "recovered"}))
    assert not owner_ops.recovered_login("")


def test_output_over_its_bound_is_never_trusted_and_output_at_the_bound_is(owner_ops, tmp_path):
    huge = json.dumps({"phase": "recovered", "pad": "x" * (owner_ops.OUTPUT_BOUND + 10)})
    ran = owner_ops.run_command(["x"], home=tmp_path, popen=fake(out=huge, err=huge),
                                policy=lambda: "none")
    assert (ran.out, ran.error) == ("", "") and not owner_ops.recovered_head(ran.out)
    exact = "x" * owner_ops.OUTPUT_BOUND
    ran = owner_ops.run_command(["x"], home=tmp_path, popen=fake(out=exact), policy=lambda: "none")
    assert ran.out == exact


def test_a_real_process_is_collected_and_leaves_no_file_behind(owner_ops, tmp_path):
    code = "import sys; sys.stderr.write('owner_busy: x\\n'); print('{}'); sys.exit(1)"
    ran = owner_ops.run_command(["-c", code], home=tmp_path, head=(sys.executable,),
                                policy=lambda: "none")
    assert ran.code == 1 and ran.error.startswith("owner_busy: ") and ran.out.strip() == "{}"
    assert list(tmp_path.iterdir()) == []


def test_a_real_ownership_command_that_refuses_prints_the_line_the_parser_reads(
        owner_ops, tmp_path):
    project, home = tmp_path / "project", tmp_path / "home"
    project.mkdir()
    home.mkdir()
    ran = owner_ops.run_command(["ownership", "recover", "--dir", str(project)], home=home,
                                policy=lambda: "none")
    assert ran.code == 1 and ran.out == ""
    allowed = refusals.OPERATION_CODES_BY_STEP["recover"]
    assert owner_ops.refusal_code(ran.error, allowed) == "recovery_refused"
    assert owner_ops.restart_reason(ran.error, "recover") is None
    assert list(home.iterdir()) == []


def test_a_real_login_recovery_of_a_folder_with_no_lease_prints_a_line_of_its_step(
        owner_ops, tmp_path):
    auth, home = tmp_path / "auth", tmp_path / "home"
    auth.mkdir()
    home.mkdir()
    ran = owner_ops.run_command(["ownership", "recover-login", "--auth-home", str(auth)],
                                home=home, policy=lambda: "none")
    assert ran.code == 1 and ran.out == ""
    allowed = refusals.OPERATION_CODES_BY_STEP["recover_login"]
    assert owner_ops.refusal_code(ran.error, allowed) in allowed, ran.error
    assert list(home.iterdir()) == []


def test_the_owner_operations_module_names_no_prepare_flag(owner_ops):
    """The hub never prepares a restart: no flag of it is spelled in the module (boundary B1)."""
    text = Path(owner_ops.__file__).read_text(encoding="utf-8")
    assert "prepare-restart" not in text and "prepare_restart" not in text


def test_the_owner_operations_module_never_kills_and_imports_no_ownership_writer(owner_ops):
    tree = ast.parse(Path(owner_ops.__file__).read_text(encoding="utf-8"))
    attributes = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    assert not attributes & {"kill", "terminate", "send_signal", "killpg"}
    imported = [node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
    imported += [alias.name for node in ast.walk(tree) if isinstance(node, ast.Import)
                 for alias in node.names]
    assert [name for name in imported if "ownership" in name] == []
