"""Tests for conductor.__main__ — the `conduct` CLI, subprocess-free.

Every test calls `main(argv)` directly and inspects the return code plus
capsys-captured stdout/stderr.
"""
import ast
import json
import re
import tomllib
from pathlib import Path

import pytest
import conductor.__main__
from conductor import prompts, templates
from conductor.__main__ import (_FIRST_ACTION, _build_parser, _cmd_init,
                                _console_ask, _interactive, main)
from tests.test_store import write_project, good_lane


def test_validate_ok_project_exits_0(tmp_path, capsys):
    root = write_project(tmp_path, lanes={"claude": good_lane()})
    assert main(["validate", "--dir", str(root)]) == 0

def test_validate_schema_error_exits_1(tmp_path, capsys):
    root = write_project(tmp_path, lanes={"bad": "{not json"})
    assert main(["validate", "--dir", str(root)]) == 1
    assert "bad" in capsys.readouterr().out

def test_validate_referential_drift_warns_but_exits_0(tmp_path, capsys):
    lane_body = json.dumps({"schema_version": 1, "author": "claude",
                            "updated": "2026-07-30T11:00:00+00:00",
                            "map_status": {"ghost": "pass"}})
    root = write_project(tmp_path, lanes={"claude": lane_body})
    assert main(["validate", "--dir", str(root)]) == 0
    assert "ghost" in capsys.readouterr().out

def test_init_scaffolds_and_prints_bootstrap(tmp_path, capsys):
    assert main(["init", "--dir", str(tmp_path)]) == 0
    assert (tmp_path / "conductor" / "map.toml").is_file()
    assert (tmp_path / "conductor" / "lanes").is_dir()
    assert "map.toml" in capsys.readouterr().out

def test_init_refuses_existing(tmp_path, capsys):
    (tmp_path / "conductor").mkdir()
    assert main(["init", "--dir", str(tmp_path)]) == 1

def test_prompt_renders_role_and_fails_on_unknown(tmp_path, capsys):
    root = write_project(tmp_path, lanes={"claude": good_lane()})
    # map from write_project has no roles → unknown role must exit 1
    assert main(["prompt", "ghost", "--dir", str(root)]) == 1


# --- additional coverage beyond the mandated set ---

MAP_WITH_ROLES = (
    'schema_version = 1\nproject = "p"\n'
    '[[nodes]]\nid = "a"\nlabel = "a"\nkind = "artifact"\n'
    '[[cycle.roles]]\nid = "reviewer"\nreviews = []\n'
)


def test_validate_broken_map_prints_error_and_exits_1(tmp_path, capsys):
    root = write_project(tmp_path, map_toml="= not toml")
    assert main(["validate", "--dir", str(root)]) == 1
    assert "map.toml" in capsys.readouterr().out

def test_validate_missing_conductor_dir_exits_1_with_stderr(tmp_path, capsys):
    assert main(["validate", "--dir", str(tmp_path)]) == 1
    assert "conductor" in capsys.readouterr().err

def test_init_writes_empty_events_and_valid_toml_map(tmp_path, capsys):
    assert main(["init", "--dir", str(tmp_path)]) == 0
    assert (tmp_path / "conductor" / "events.jsonl").read_text(encoding="utf-8") == ""
    data = tomllib.loads((tmp_path / "conductor" / "map.toml").read_text(encoding="utf-8"))
    assert data["schema_version"] == 1 and data["nodes"]

def test_init_then_validate_is_clean(tmp_path, capsys):
    # The scaffold must satisfy its own validation rules end-to-end and print
    # zero warnings (subsumes the deprecated-row check, ADR 0001).
    assert main(["init", "--dir", str(tmp_path)]) == 0
    capsys.readouterr()                       # isolate validate's output from init's
    assert main(["validate", "--dir", str(tmp_path)]) == 0
    assert capsys.readouterr().out == ""

def test_validate_schema_version_warning_surfaces_in_stdout(tmp_path, capsys):
    # Pin: validate must pass loaded.warnings into merge (extra_warnings=...) —
    # dropping the pass-through would lose loader-level schema-version warnings.
    body = good_lane().replace('"schema_version": 1', '"schema_version": 2')
    root = write_project(tmp_path, lanes={"claude": body})
    assert main(["validate", "--dir", str(root)]) == 0
    assert "schema_version" in capsys.readouterr().out

def test_validate_map_error_printed_before_lane_error(tmp_path, capsys):
    # Pin: the map error is inserted at position 0, ahead of broken-lane errors.
    root = write_project(tmp_path, map_toml="= not toml", lanes={"bad": "{not json"})
    assert main(["validate", "--dir", str(root)]) == 1
    out = capsys.readouterr().out
    assert "map.toml" in out and "lane bad" in out
    assert out.index("map.toml") < out.index("lane bad")

def test_prompt_known_role_prints_prompt(tmp_path, capsys):
    root = write_project(tmp_path, map_toml=MAP_WITH_ROLES,
                         lanes={"claude": good_lane()})
    assert main(["prompt", "reviewer", "--dir", str(root)]) == 0
    out = capsys.readouterr().out
    assert "reviewer" in out and "lanes/" in out

def test_prompt_unknown_role_message_goes_to_stderr(tmp_path, capsys):
    root = write_project(tmp_path, map_toml=MAP_WITH_ROLES)
    assert main(["prompt", "ghost", "--dir", str(root)]) == 1
    err = capsys.readouterr().err
    assert "ghost" in err and "reviewer" in err

def test_prompt_broken_map_exits_1_before_rendering(tmp_path, capsys):
    root = write_project(tmp_path, map_toml="= not toml")
    assert main(["prompt", "reviewer", "--dir", str(root)]) == 1
    captured = capsys.readouterr()
    assert "map.toml" in captured.err and captured.out == ""

def test_prompt_missing_conductor_dir_exits_1_with_stderr(tmp_path, capsys):
    assert main(["prompt", "reviewer", "--dir", str(tmp_path)]) == 1
    assert "conductor" in capsys.readouterr().err


# --- C6.1: conduct prompt --role/--author (positional role deprecated) ---


def test_prompt_positional_role_warns_deprecated_but_works(tmp_path, capsys):
    root = write_project(tmp_path, map_toml=MAP_WITH_ROLES,
                         lanes={"claude": good_lane()})
    assert main(["prompt", "reviewer", "--dir", str(root)]) == 0
    captured = capsys.readouterr()
    assert "deprecated" in captured.err and "--role" in captured.err
    assert "reviewer" in captured.out

def test_prompt_role_flag_exits_0_without_warning(tmp_path, capsys):
    root = write_project(tmp_path, map_toml=MAP_WITH_ROLES)
    assert main(["prompt", "--role", "reviewer", "--dir", str(root)]) == 0
    captured = capsys.readouterr()
    assert captured.err == "" and "reviewer" in captured.out

def test_prompt_author_flag_renders_author_lane(tmp_path, capsys):
    root = write_project(tmp_path, map_toml=MAP_WITH_ROLES)
    assert main(["prompt", "--role", "reviewer", "--author", "codex",
                 "--dir", str(root)]) == 0
    out = capsys.readouterr().out
    assert "conductor/lanes/codex.json" in out and '"author": "codex"' in out

def test_prompt_invalid_author_exits_1(tmp_path, capsys):
    root = write_project(tmp_path, map_toml=MAP_WITH_ROLES)
    assert main(["prompt", "--role", "reviewer", "--author", "bad name",
                 "--dir", str(root)]) == 1
    assert "author" in capsys.readouterr().err

def test_prompt_positional_plus_role_flag_is_usage_error(tmp_path, capsys):
    with pytest.raises(SystemExit) as e:
        main(["prompt", "reviewer", "--role", "reviewer", "--dir", str(tmp_path)])
    assert e.value.code == 2
    assert "usage" in capsys.readouterr().err

def test_prompt_no_role_at_all_is_usage_error(tmp_path, capsys):
    with pytest.raises(SystemExit) as e:
        main(["prompt", "--dir", str(tmp_path)])
    assert e.value.code == 2
    assert "usage" in capsys.readouterr().err


# --- DO-3: guided init, templates, and the deterministic --template path ---


def _init_args(tmp_path, *extra):
    """A real parsed `init` namespace — no hand-built stand-in."""
    return _build_parser().parse_args(["init", "--dir", str(tmp_path), *extra])


def _scripted(answers):
    """An `ask` replaying `answers`, then behaving exactly like a closed stdin.

    A wizard that fails to consume its script therefore ends as a clean
    EOFError rather than spinning forever — a re-prompt loop bug shows up as a
    failing assertion, never as a hung suite.
    """
    queue = list(answers)

    def ask(prompt):
        if not queue:
            raise EOFError(prompt)
        return queue.pop(0)
    return ask


def _map_text(tmp_path):
    return (tmp_path / "conductor" / "map.toml").read_text(encoding="utf-8")


def _harnesses(tmp_path):
    data = tomllib.loads(_map_text(tmp_path))
    return {r["id"]: r.get("harness") for r in data["cycle"]["roles"]}


TEMPLATE_NAMES = ["default-orbit", "single-harness", "empty", "minimal"]


@pytest.mark.parametrize("name", TEMPLATE_NAMES)
def test_init_template_writes_that_template_and_validates_clean(tmp_path, capsys, name):
    assert main(["init", "--dir", str(tmp_path), "--template", name]) == 0
    assert _map_text(tmp_path) == templates.get(name)
    assert name in capsys.readouterr().out          # says which one it used
    assert main(["validate", "--dir", str(tmp_path)]) == 0
    assert capsys.readouterr().out == ""


def test_init_unknown_template_exits_1_and_writes_nothing(tmp_path, capsys):
    # Deliberately not argparse `choices`: that is a usage error (exit 2) and
    # duplicates the template list. The message comes from templates.get().
    assert main(["init", "--dir", str(tmp_path), "--template", "orbital-decay"]) == 1
    assert not (tmp_path / "conductor").exists()
    err = capsys.readouterr().err
    assert "orbital-decay" in err
    for name in ("default-orbit", "single-harness", "empty"):
        assert name in err


def test_init_non_tty_uses_the_default_template_and_never_reads_stdin(
        tmp_path, capsys, monkeypatch):
    # The whole of CI lives on this: no TTY means no question, ever.
    def boom(*args, **kwargs):
        raise AssertionError("conduct init read stdin on a non-TTY")

    monkeypatch.setattr("builtins.input", boom)
    assert _interactive() is False                   # the suite IS the non-TTY case
    assert main(["init", "--dir", str(tmp_path)]) == 0
    assert _map_text(tmp_path) == templates.get(templates.DEFAULT)


@pytest.mark.parametrize("extra", [[], *[["--template", n] for n in TEMPLATE_NAMES]])
def test_init_writes_exactly_one_trailing_newline(tmp_path, capsys, extra):
    # templates.get() already ends in one newline; a writer adding its own
    # would leave a blank line at the end of every user's committed map. The
    # `minimal` case is the sharp one: prompts.MAP_EXAMPLE ends without one.
    assert main(["init", "--dir", str(tmp_path), *extra]) == 0
    text = _map_text(tmp_path)
    assert text.endswith("\n") and not text.endswith("\n\n")


def test_init_default_scaffold_is_the_default_orbit_not_the_spec_example(tmp_path, capsys):
    # A deliberate change of content, not a preserved default: the Default
    # Orbit is the product's entry point, and the old spec-example scaffold
    # survives only as `--template minimal`.
    assert main(["init", "--dir", str(tmp_path)]) == 0
    assert _map_text(tmp_path) == templates.get("default-orbit")
    assert _map_text(tmp_path) != templates.get("minimal")


def test_the_result_of_init_does_not_depend_on_a_tty(tmp_path, capsys):
    # Only the WAY you choose may differ. Wizard-with-every-default and the
    # non-TTY path must land on the same template.
    quiet, guided = tmp_path / "quiet", tmp_path / "guided"
    quiet.mkdir(), guided.mkdir()
    assert main(["init", "--dir", str(quiet)]) == 0
    assert _cmd_init(_init_args(guided), ask=_scripted(["", "", ""])) == 0
    quiet_map, guided_map = _map_text(quiet), _map_text(guided)
    assert tomllib.loads(quiet_map)["cycle"] == tomllib.loads(guided_map)["cycle"]
    assert guided_map == templates.get("default-orbit", project=guided.name)


def test_wizard_all_defaults_produces_a_valid_default_orbit(tmp_path, capsys):
    assert _cmd_init(_init_args(tmp_path), ask=_scripted(["", "", ""])) == 0
    data = tomllib.loads(_map_text(tmp_path))
    assert data["project"] == tmp_path.name          # the directory you are in
    assert data["cycle"]["phases"][0] == "goal"
    assert _harnesses(tmp_path) == {"scout": "claude-code", "diagnostician": "codex",
                                    "architect": "claude-code",
                                    "implementer": "claude-code", "reviewer": "codex"}
    capsys.readouterr()
    assert main(["validate", "--dir", str(tmp_path)]) == 0
    assert capsys.readouterr().out == ""


def test_wizard_carries_the_chosen_project_and_harnesses(tmp_path, capsys):
    # project, primary = menu item 2 (codex), reviewer = a typed custom id.
    assert _cmd_init(_init_args(tmp_path),
                     ask=_scripted(["my-app", "2", "kimi-cli"])) == 0
    data = tomllib.loads(_map_text(tmp_path))
    assert data["project"] == "my-app"
    assert _harnesses(tmp_path)["implementer"] == "codex"
    assert _harnesses(tmp_path)["reviewer"] == "kimi-cli"
    dialogue = capsys.readouterr().err
    assert "my-app" in dialogue and "kimi-cli" in dialogue   # shown before writing


def test_wizard_no_reviewer_selects_the_single_harness_template(tmp_path, capsys):
    # With claude-code primary the reviewer menu is 1) codex  2) none.
    assert _cmd_init(_init_args(tmp_path), ask=_scripted(["solo", "1", "2"])) == 0
    data = tomllib.loads(_map_text(tmp_path))
    assert [r["id"] for r in data["cycle"]["roles"]] == ["implementer"]
    assert data["project"] == "solo"
    capsys.readouterr()
    assert main(["validate", "--dir", str(tmp_path)]) == 0


def test_wizard_never_asks_for_an_api_key_or_a_template(tmp_path, capsys):
    assert _cmd_init(_init_args(tmp_path), ask=_scripted(["", "", ""])) == 0
    captured = capsys.readouterr()
    asked = (captured.out + captured.err).lower()
    for banned in ("api key", "api-key", "token", "password", "which template"):
        assert banned not in asked


def test_wizard_rejects_an_illegal_project_name_and_re_prompts(tmp_path, capsys):
    assert _cmd_init(_init_args(tmp_path),
                     ask=_scripted(['my "app"', "my-app", "", ""])) == 0
    dialogue = capsys.readouterr().err
    assert 'my "app"' in dialogue and templates.NAME_RULE in dialogue
    assert tomllib.loads(_map_text(tmp_path))["project"] == "my-app"


def test_wizard_rejects_an_illegal_harness_id_and_re_prompts(tmp_path, capsys):
    assert _cmd_init(_init_args(tmp_path),
                     ask=_scripted(["", 'kimi"cli', "kimi-cli", ""])) == 0
    dialogue = capsys.readouterr().err
    assert templates.NAME_RULE in dialogue and "'\"'" in dialogue  # names the char
    assert _harnesses(tmp_path)["implementer"] == "kimi-cli"


def test_wizard_accepts_a_product_name_with_a_space(tmp_path, capsys):
    # Real harnesses ship under names like "Claude Code"; the allowlist must
    # not turn a correct answer into an error.
    assert _cmd_init(_init_args(tmp_path),
                     ask=_scripted(["My Project (v2)", "Kimi Code", ""])) == 0
    assert tomllib.loads(_map_text(tmp_path))["project"] == "My Project (v2)"
    assert _harnesses(tmp_path)["implementer"] == "Kimi Code"


def test_wizard_reads_an_in_range_number_as_a_menu_choice(tmp_path, capsys):
    # Primary menu: 1) claude-code 2) codex. Reviewer menu then: 1) claude-code
    # 2) none — so "1" here is a harness, not the no-reviewer entry.
    assert _cmd_init(_init_args(tmp_path), ask=_scripted(["p", "2", "1"])) == 0
    assert _harnesses(tmp_path)["implementer"] == "codex"
    assert _harnesses(tmp_path)["reviewer"] == "claude-code"


def test_wizard_accepts_a_harness_whose_name_is_a_number(tmp_path, capsys):
    # A digit indexes the menu only while it indexes the menu. "7" against a
    # two-item list is not a mistake to scold — it is the id the user typed,
    # and a harness may legally be called that.
    assert _cmd_init(_init_args(tmp_path), ask=_scripted(["p", "7", "9"])) == 0
    assert _harnesses(tmp_path)["implementer"] == "7"
    assert _harnesses(tmp_path)["reviewer"] == "9"
    assert tomllib.loads(_map_text(tmp_path))["project"] == "p"


def test_wizard_says_so_when_both_roles_run_the_same_harness(tmp_path, capsys):
    assert _cmd_init(_init_args(tmp_path),
                     ask=_scripted(["p", "claude-code", "claude-code"])) == 0
    assert "not independent" in capsys.readouterr().err
    assert "different harness product" not in _map_text(tmp_path)


def test_invalid_wizard_input_leaves_no_half_created_project(tmp_path, capsys):
    # Every answer is validated before anything is created. A run abandoned
    # after a rejected answer must leave the directory exactly as it found it.
    before = sorted(p.name for p in tmp_path.iterdir())
    assert _cmd_init(_init_args(tmp_path), ask=_scripted(['my "app"'])) == 1
    assert not (tmp_path / "conductor").exists()
    assert sorted(p.name for p in tmp_path.iterdir()) == before


PROBING_MODULES = {"shutil", "subprocess", "os", "platform", "socket",
                   "importlib", "sysconfig", "site", "winreg"}
PROBING_CALLS = {"which", "getenv", "popen", "system", "run", "find_spec",
                 "check_output", "listdir", "environ"}


def test_init_never_probes_the_machine_for_installed_harnesses():
    # Detecting installed harnesses is deferred, and probing a user's box is a
    # new capability class that needs its own ADR (privacy, sandboxing). The
    # ban is pinned structurally rather than by grepping prose: nothing on the
    # init path may import a module that can see the machine, or call anything
    # that looks one up. Parsed, so a comment mentioning subprocess is fine
    # and an actual import is not.
    for module in (conductor.__main__, conductor.templates):
        tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            imported = []
            if isinstance(node, ast.Import):
                imported = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                imported = [node.module or ""]
            for name in imported:
                assert name.split(".")[0] not in PROBING_MODULES, \
                    f"{module.__name__} may not import {name}"
            if isinstance(node, ast.Attribute):
                assert node.attr not in PROBING_CALLS, \
                    f"{module.__name__} may not touch .{node.attr}"


def test_wizard_eof_after_an_answer_exits_1_and_leaves_no_conductor_dir(tmp_path, capsys):
    # A person started answering and walked away: that is a cancellation.
    assert _cmd_init(_init_args(tmp_path), ask=_scripted(["my-app"])) == 1
    assert not (tmp_path / "conductor").exists()
    assert "cancelled" in capsys.readouterr().err


def test_eof_before_any_answer_falls_back_to_the_default_template(tmp_path, capsys):
    # `conduct init < NUL` on Windows: stdin is the null DEVICE, so isatty()
    # reports a console and the wizard starts, but there is nothing to read.
    # That is a script saying "no input", not a person cancelling — it must
    # produce the same scaffold the non-TTY path does, not an exit 1.
    assert _cmd_init(_init_args(tmp_path), ask=_scripted([])) == 0
    assert _map_text(tmp_path) == templates.get(templates.DEFAULT)
    assert "no input available" in capsys.readouterr().err


def test_a_nul_stdin_run_leaves_no_question_on_stdout(tmp_path, capsys, monkeypatch):
    # The real shape, through the real terminal prompter: `input()` raises at
    # once, exactly as it does when stdin is the null device. The outcome was
    # already right; what a stdout-capturing caller sees must be too — the
    # non-TTY contract is that no question is asked, so none may be echoed.
    def eof():
        raise EOFError

    monkeypatch.setattr("builtins.input", eof)
    assert _cmd_init(_init_args(tmp_path), ask=_console_ask) == 0
    captured = capsys.readouterr()
    assert _map_text(tmp_path) == templates.get(templates.DEFAULT)
    for question in ("three questions", "Project name", "choice [",
                     "Which harness", "no input available"):
        assert question not in captured.out
    assert "Project name" in captured.err        # a person at a terminal sees it


def test_the_console_prompter_puts_its_prompt_on_stderr(tmp_path, capsys, monkeypatch):
    # input(prompt) writes the prompt to stdout — and writes it BEFORE it
    # discovers there is nothing to read. _console_ask is the whole reason the
    # fallback above can stay silent, so pin it directly.
    monkeypatch.setattr("builtins.input", lambda: "typed")
    assert _console_ask("Project name [p]: ") == "typed"
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "Project name [p]: "


def test_wizard_ctrl_c_exits_1_and_leaves_no_conductor_dir(tmp_path, capsys):
    def interrupt(prompt):
        raise KeyboardInterrupt

    assert _cmd_init(_init_args(tmp_path), ask=interrupt) == 1
    assert not (tmp_path / "conductor").exists()
    assert "cancelled" in capsys.readouterr().err


@pytest.mark.parametrize("extra", [[], ["--template", "empty"]])
def test_init_refuses_an_existing_conductor_on_every_path(tmp_path, capsys, extra):
    (tmp_path / "conductor").mkdir()
    assert main(["init", "--dir", str(tmp_path), *extra]) == 1
    assert "already exists" in capsys.readouterr().err


def test_wizard_refuses_an_existing_conductor_before_asking_anything(tmp_path, capsys):
    # An empty script means any question at all would surface as "cancelled".
    (tmp_path / "conductor").mkdir()
    assert _cmd_init(_init_args(tmp_path), ask=_scripted([])) == 1
    assert "already exists" in capsys.readouterr().err


def test_init_prints_next_commands_that_actually_run(tmp_path, capsys):
    assert main(["init", "--dir", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert f"--dir {tmp_path}" in out                  # the printed root is real
    assert "conduct up" in out and "127.0.0.1:7777" in out
    assert "placeholder nodes" in out                  # the first action
    role = re.search(r"conduct prompt --role (\S+)", out).group(1)
    assert main(["validate", "--dir", str(tmp_path)]) == 0
    assert main(["prompt", "--role", role, "--dir", str(tmp_path)]) == 0


def test_the_bootstrap_prompt_does_not_contradict_the_map_just_written(tmp_path, capsys):
    # The prompt used to tell the agent to PRODUCE a map and embedded a
    # different one, so the step the CLI recommends discarded every answer the
    # wizard collected. It must now be about the file on disk.
    assert _cmd_init(_init_args(tmp_path),
                     ask=_scripted(["my-app", "Kimi Code", "2"])) == 0
    out = capsys.readouterr().out
    written = _map_text(tmp_path)
    assert "already exists and already validates" in out
    assert "Produce `conductor/map.toml`" not in out
    # Nothing from the OTHER map may appear: those values contradict the
    # answers, and an agent handed both will pick one.
    for contradiction in ('project = "web-app"', "human-gate", '"plan"'):
        assert contradiction not in out
    assert 'project = "my-app"' in written and "Kimi Code" in written


def test_the_bootstrap_prompt_stands_alone_when_redirected(tmp_path, capsys):
    # `conduct init > bootstrap.txt` yields this and nothing else, so it may
    # not lean on anything the CLI printed around it.
    text = prompts.bootstrap_prompt("conductor/map.toml")
    for needed in ("conductor/map.toml", "schema_version", "[[nodes]]",
                   "[[cycle.roles]]", "conduct validate", "depends_on"):
        assert needed in text
    for dangling in ("above", "below", "the rules"):
        assert dangling not in text


def test_the_first_action_is_said_once_to_both_audiences(tmp_path, capsys):
    # Two differently-worded first actions read as two separate tasks.
    assert main(["init", "--dir", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert out.count(_FIRST_ACTION) == 1               # the person's copy
    assert "placeholder" in prompts.bootstrap_prompt()  # the agent's copy


def test_the_harness_questions_say_what_the_answer_does(tmp_path, capsys):
    # Two of three questions are about `harness`, which no merge rule reads.
    # At a prompt that reads like configuring an integration.
    assert _cmd_init(_init_args(tmp_path), ask=_scripted(["p", "", ""])) == 0
    asked = capsys.readouterr().err
    assert "never launches, installs or detects a harness" in asked
    assert "labels who does what" in asked


def test_the_no_reviewer_option_names_its_consequence(tmp_path, capsys):
    # `none` is the one answer that removes a role rather than naming a
    # product, and it hands the user the vacuous-agreed state.
    assert _cmd_init(_init_args(tmp_path), ask=_scripted(["p", "", "2"])) == 0
    asked = capsys.readouterr().err
    assert "no reviewing role at all" in asked
    assert "agreed with nobody having looked" in asked
    assert [r["id"] for r in tomllib.loads(_map_text(tmp_path))["cycle"]["roles"]] \
        == ["implementer"]


def test_init_reports_the_validation_it_just_ran(tmp_path, capsys):
    assert main(["init", "--dir", str(tmp_path)]) == 0
    assert "conduct validate" in capsys.readouterr().out


def test_init_template_empty_prints_no_role_prompt_it_cannot_offer(tmp_path, capsys):
    assert main(["init", "--dir", str(tmp_path), "--template", "empty"]) == 0
    out = capsys.readouterr().out
    assert "conduct prompt --role" not in out          # `empty` declares no roles
    assert "conduct up" in out


def test_demo_rejects_dir_flag(capsys):
    # Pin: demo materializes its own throwaway root — --dir is deliberately
    # not accepted (argparse usage error, exit 2). Demo behavior itself is
    # covered in tests/test_demo.py.
    with pytest.raises(SystemExit) as e:
        main(["demo", "--dir", "."])
    assert e.value.code == 2
    assert "usage" in capsys.readouterr().err
