"""Tests for `conduct init` — the guided wizard, templates, and the scaffold.

Split out of test_cli.py when the init path moved into `conductor.init`. Almost
every test here calls the CLI entry point directly and inspects the return code
plus capsys-captured stdout/stderr; the two that do not pin one helper
(`_console_ask`, `_custom_row`) because the helper is what the claim is about.
The wizard is never driven through real stdin — `_scripted` injects the
answers, so a re-prompt loop fails these tests instead of hanging them.

The machine-probing ban lives in test_init_probing_ban.py, which is where its
one child interpreter is justified. No test in this file spawns a process.
"""
import re
import tomllib

import pytest
import conductor.init
import conductor.__main__
from conductor import harnesses, prompts, templates
from conductor.init import _FIRST_ACTION, _NO_REVIEWER, _console_ask, _interactive
from conductor.__main__ import _build_parser, main


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


def _unwrapped(text):
    """Dialogue with its folding undone, for phrase assertions.

    Every surface here is wrapped at render time, so a needle that happens to
    straddle a line break would fail for a reason that has nothing to do with
    what the test is about. Normalising whitespace is what keeps these pins
    about the words rather than about where the words break.
    """
    return " ".join(text.split())


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
    assert name in capsys.readouterr().err          # which one it used is dialogue
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
    assert conductor.init.run(_init_args(guided), ask=_scripted(["", "", ""])) == 0
    quiet_map, guided_map = _map_text(quiet), _map_text(guided)
    assert tomllib.loads(quiet_map)["cycle"] == tomllib.loads(guided_map)["cycle"]
    assert guided_map == templates.get("default-orbit", project=guided.name)


def test_wizard_all_defaults_produces_a_valid_default_orbit(tmp_path, capsys):
    assert conductor.init.run(_init_args(tmp_path), ask=_scripted(["", "", ""])) == 0
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
    assert conductor.init.run(_init_args(tmp_path),
                              ask=_scripted(["my-app", "2", "kimi-cli"])) == 0
    data = tomllib.loads(_map_text(tmp_path))
    assert data["project"] == "my-app"
    assert _harnesses(tmp_path)["implementer"] == "codex"
    assert _harnesses(tmp_path)["reviewer"] == "kimi-cli"
    dialogue = capsys.readouterr().err
    assert "my-app" in dialogue and "kimi-cli" in dialogue   # shown before writing


def test_wizard_no_reviewer_selects_the_single_harness_template(tmp_path, capsys):
    # With claude-code primary the reviewer menu is 1) codex 2) cursor
    # 3) custom 4) (none) — the sentinel is always last, after the registry.
    assert conductor.init.run(_init_args(tmp_path), ask=_scripted(["solo", "1", "4"])) == 0
    data = tomllib.loads(_map_text(tmp_path))
    assert [r["id"] for r in data["cycle"]["roles"]] == ["implementer"]
    assert data["project"] == "solo"
    capsys.readouterr()
    assert main(["validate", "--dir", str(tmp_path)]) == 0


def test_wizard_never_asks_for_an_api_key_or_a_template(tmp_path, capsys):
    assert conductor.init.run(_init_args(tmp_path), ask=_scripted(["", "", ""])) == 0
    captured = capsys.readouterr()
    asked = (captured.out + captured.err).lower()
    for banned in ("api key", "api-key", "token", "password", "which template"):
        assert banned not in asked


def test_wizard_rejects_an_illegal_project_name_and_re_prompts(tmp_path, capsys):
    assert conductor.init.run(_init_args(tmp_path),
                              ask=_scripted(['my "app"', "my-app", "", ""])) == 0
    dialogue = _unwrapped(capsys.readouterr().err)
    assert 'my "app"' in dialogue and templates.NAME_RULE in dialogue
    assert tomllib.loads(_map_text(tmp_path))["project"] == "my-app"


def test_wizard_rejects_an_illegal_harness_id_and_re_prompts(tmp_path, capsys):
    assert conductor.init.run(_init_args(tmp_path),
                              ask=_scripted(["", 'kimi"cli', "kimi-cli", ""])) == 0
    dialogue = _unwrapped(capsys.readouterr().err)
    assert templates.NAME_RULE in dialogue and "'\"'" in dialogue  # names the char
    assert _harnesses(tmp_path)["implementer"] == "kimi-cli"


def test_wizard_accepts_a_product_name_with_a_space(tmp_path, capsys):
    # Real harnesses ship under names like "Claude Code"; the allowlist must
    # not turn a correct answer into an error.
    assert conductor.init.run(_init_args(tmp_path),
                              ask=_scripted(["My Project (v2)", "Kimi Code", ""])) == 0
    assert tomllib.loads(_map_text(tmp_path))["project"] == "My Project (v2)"
    assert _harnesses(tmp_path)["implementer"] == "Kimi Code"


def test_wizard_reads_an_in_range_number_as_a_menu_choice(tmp_path, capsys):
    # Primary menu: 1) claude-code 2) codex 3) cursor 4) custom. Picking codex
    # drops it from the reviewer menu, so "1" there is claude-code — a
    # harness, not the no-reviewer entry, which the registry pushed to the end.
    assert conductor.init.run(_init_args(tmp_path), ask=_scripted(["p", "2", "1"])) == 0
    assert _harnesses(tmp_path)["implementer"] == "codex"
    assert _harnesses(tmp_path)["reviewer"] == "claude-code"


def test_wizard_accepts_a_harness_whose_name_is_a_number(tmp_path, capsys):
    # A digit indexes the menu only while it indexes the menu. "7" against a
    # four-item list is not a mistake to scold — it is the id the user typed,
    # and a harness may legally be called that. Keeping the recommended list
    # short is what keeps this reachable at all.
    assert conductor.init.run(_init_args(tmp_path), ask=_scripted(["p", "7", "9"])) == 0
    assert _harnesses(tmp_path)["implementer"] == "7"
    assert _harnesses(tmp_path)["reviewer"] == "9"
    assert tomllib.loads(_map_text(tmp_path))["project"] == "p"


@pytest.mark.parametrize("answer", ["02", "002", "٢", "²"])
def test_the_wizard_takes_a_number_it_never_printed_as_a_typed_harness_id(
        tmp_path, capsys, answer):
    # The primary menu prints `1` `2` `3` `4`, and those four strings are the
    # whole of what picks a row. `02`, `002` and the ARABIC-INDIC `٢` all read
    # as item 2 to `int()` but were never offered, so answering one of them and
    # getting `codex` writes a product nobody chose. `²` is worse than
    # ambiguous: `'²'.isdigit()` is True while `int('²')` raises, so a range
    # test spelled over `int()` ends `conduct init` in an unhandled ValueError
    # on an id `templates.NAME_RE` accepts.
    assert templates.NAME_RE.fullmatch(answer), answer
    assert conductor.init.run(_init_args(tmp_path),
                              ask=_scripted(["p", answer, "1"])) == 0
    assert _harnesses(tmp_path)["implementer"] == answer
    assert _harnesses(tmp_path)["reviewer"] == "claude-code"   # row 1, as printed


def test_wizard_says_so_when_both_roles_run_the_same_harness(tmp_path, capsys):
    assert conductor.init.run(_init_args(tmp_path),
                              ask=_scripted(["p", "claude-code", "claude-code"])) == 0
    assert "not independent" in _unwrapped(capsys.readouterr().err)
    assert "different harness product" not in _map_text(tmp_path)


def test_invalid_wizard_input_leaves_no_half_created_project(tmp_path, capsys):
    # Every answer is validated before anything is created. A run abandoned
    # after a rejected answer must leave the directory exactly as it found it.
    before = sorted(p.name for p in tmp_path.iterdir())
    assert conductor.init.run(_init_args(tmp_path), ask=_scripted(['my "app"'])) == 1
    assert not (tmp_path / "conductor").exists()
    assert sorted(p.name for p in tmp_path.iterdir()) == before


def test_wizard_eof_after_an_answer_exits_1_and_leaves_no_conductor_dir(tmp_path, capsys):
    # A person started answering and walked away: that is a cancellation.
    assert conductor.init.run(_init_args(tmp_path), ask=_scripted(["my-app"])) == 1
    assert not (tmp_path / "conductor").exists()
    assert "cancelled" in capsys.readouterr().err


def test_eof_before_any_answer_falls_back_to_the_default_template(tmp_path, capsys):
    # `conduct init < NUL` on Windows: stdin is the null DEVICE, so isatty()
    # reports a console and the wizard starts, but there is nothing to read.
    # That is a script saying "no input", not a person cancelling — it must
    # produce the same scaffold the non-TTY path does, not an exit 1.
    assert conductor.init.run(_init_args(tmp_path), ask=_scripted([])) == 0
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
    assert conductor.init.run(_init_args(tmp_path), ask=_console_ask) == 0
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

    assert conductor.init.run(_init_args(tmp_path), ask=interrupt) == 1
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
    assert conductor.init.run(_init_args(tmp_path), ask=_scripted([])) == 1
    assert "already exists" in capsys.readouterr().err


def test_init_prints_next_commands_that_actually_run(tmp_path, capsys):
    assert main(["init", "--dir", str(tmp_path)]) == 0
    out = capsys.readouterr().err          # advice is dialogue, not the result
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
    assert conductor.init.run(_init_args(tmp_path),
                              ask=_scripted(["my-app", "Kimi Code", "2"])) == 0
    out = capsys.readouterr().out
    written = _map_text(tmp_path)
    assert "already exists and it already validates" in _unwrapped(out)
    assert "Produce `conductor/map.toml`" not in out
    # Nothing from the OTHER map may appear: those values contradict the
    # answers, and an agent handed both will pick one.
    for contradiction in ('project = "web-app"', "human-gate", '"plan"'):
        assert contradiction not in out
    assert 'project = "my-app"' in written and "Kimi Code" in written


def test_the_first_action_is_said_once_to_both_audiences(tmp_path, capsys):
    # Two differently-worded first actions read as two separate tasks.
    assert main(["init", "--dir", str(tmp_path)]) == 0
    said = _unwrapped(capsys.readouterr().err)
    assert said.count(_FIRST_ACTION) == 1              # the person's copy
    assert "placeholder" in prompts.bootstrap_prompt()  # the agent's copy


def test_the_harness_questions_say_what_the_answer_does(tmp_path, capsys):
    # Two of three questions are about `harness`, which no merge rule reads.
    # At a prompt that reads like configuring an integration.
    assert conductor.init.run(_init_args(tmp_path), ask=_scripted(["p", "", ""])) == 0
    asked = _unwrapped(capsys.readouterr().err)
    assert "never launches, installs or detects a harness" in asked
    assert "labels who does what" in asked


def test_the_no_reviewer_option_names_its_consequence(tmp_path, capsys):
    # The last row is the one answer that removes a role rather than naming a
    # product, and it hands the user the vacuous-agreed state.
    assert conductor.init.run(_init_args(tmp_path), ask=_scripted(["p", "", "4"])) == 0
    asked = _unwrapped(capsys.readouterr().err)
    assert "no reviewing role at all" in asked
    assert "agreed with nobody having looked" in asked
    assert [r["id"] for r in tomllib.loads(_map_text(tmp_path))["cycle"]["roles"]] \
        == ["implementer"]


# --- DO-4: the harness registry drives the menu, and only the id is written ---


def test_the_menu_shows_the_product_name_and_writes_the_id(tmp_path, capsys):
    # Two values exist now, and exactly one of them may reach disk. The row
    # carries both so the user can see which is which before answering.
    assert conductor.init.run(_init_args(tmp_path), ask=_scripted(["p", "1", "1"])) == 0
    assert "claude-code — Claude Code" in _unwrapped(capsys.readouterr().err)
    written = _map_text(tmp_path)
    assert _harnesses(tmp_path)["implementer"] == "claude-code"
    assert "Claude Code" not in written        # the display name never lands


def test_a_typed_harness_lands_exactly_as_typed(tmp_path, capsys):
    # The registry is never matched against free text, in either direction: a
    # display name typed by hand stays a display name, and an unregistered id
    # is never helpfully rewritten into a registered one.
    assert conductor.init.run(_init_args(tmp_path),
                              ask=_scripted(["p", "Claude Code", "my own agent"])) == 0
    assert _harnesses(tmp_path)["implementer"] == "Claude Code"
    assert _harnesses(tmp_path)["reviewer"] == "my own agent"


def test_the_menu_offers_the_registry_and_claims_no_detection(tmp_path, capsys):
    assert conductor.init.run(_init_args(tmp_path), ask=_scripted(["p", "", ""])) == 0
    asked = _unwrapped(capsys.readouterr().err)
    for harness_id in harnesses.RECOMMENDED:                    # numbered rows
        assert f"{harness_id} — {harnesses.get(harness_id).display_name}" in asked
    for harness in harnesses.known():          # the rest, named on the custom row
        assert harness.id in asked
    for claim in ("detected", "installed on", "we found"):
        assert claim not in asked.lower()      # there is no detection, so say none


def test_the_wizard_menu_names_a_single_product(tmp_path, capsys):
    # Two brand names in one screen is a question the user has to answer
    # before they can answer ours. §9.1 of the P0 plan leaves it to the owner
    # whether the CLI carries December's terminology before the package is
    # renamed, so the wizard stays on the name the package already ships.
    assert conductor.init.run(_init_args(tmp_path), ask=_scripted(["p", "", ""])) == 0
    asked = _unwrapped(capsys.readouterr().err)
    assert "Conduct" in asked
    assert "December" not in asked


def test_the_custom_row_says_only_things_that_hold(tmp_path, capsys):
    # The gloss is the one place the wizard makes claims about ids it does not
    # number, and it ships to a user with no way to check them.
    value, gloss = conductor.init._custom_row()
    unnumbered = [h.id for h in harnesses.known()
                  if h.id not in harnesses.RECOMMENDED and h.id != harnesses.CUSTOM]
    assert value == harnesses.CUSTOM and unnumbered
    # The row names the id it writes. Choosing it and typing an id are two
    # different answers, and a gloss that only teaches typing leaves the user
    # to discover the first one from their own map.toml.
    assert value in gloss
    for harness_id in unnumbered:
        assert harness_id in gloss, harness_id
    for harness_id in harnesses.RECOMMENDED:      # numbered above, not here
        assert harness_id not in gloss, harness_id
    # Both directions, or the name is a lie. Inclusion alone leaves the leak
    # open: a `vendors()` that forgot to drop the custom row would put this
    # row's own id back among the ids you may type INSTEAD of it, and every
    # assertion above would still be green. Pinned over the one clause that
    # lists ids — the row's id legitimately appears earlier in the sentence.
    listed = gloss.split("also knows ", 1)[1].split(" — ", 1)[0]
    assert [item.strip() for item in listed.split(",")] == unnumbered
    # Primary menu: 1-3 recommended, 4 custom. With custom primary the whole
    # recommended list returns, so the reviewer's 4 is custom as well.
    assert conductor.init.run(_init_args(tmp_path), ask=_scripted(["p", "4", "4"])) == 0
    assert _harnesses(tmp_path)["implementer"] == harnesses.CUSTOM
    assert _harnesses(tmp_path)["reviewer"] == harnesses.CUSTOM


def test_the_custom_row_does_not_promise_a_number_is_written_as_typed():
    # A digit that indexes the menu answers with the row it numbers, not with
    # itself — pinned by test_wizard_reads_an_in_range_number_as_a_menu_choice
    # above, where the legal id `2` lands in map.toml as `codex`. This gloss
    # ships to a user who has no way to check that, so its promise of a literal
    # write must carry that exception rather than read as unconditional.
    _, gloss = conductor.init._custom_row()
    promise = gloss.split("also knows ", 1)[1].split(" — ", 1)[1]
    assert "exactly as typed" in promise
    assert "not a number" in promise


def test_none_means_a_harness_at_both_prompts_now(tmp_path, capsys):
    # The old sentinel WAS the word `none`, so it named a product at the first
    # prompt and removed a role at the second. Both prompts now agree, and the
    # sentinel is spelled so `templates.NAME_RE` refuses to accept it typed.
    with pytest.raises(templates.InvalidName):
        templates.check_name("harness id", _NO_REVIEWER)
    assert conductor.init.run(_init_args(tmp_path),
                              ask=_scripted(["p", "none", "none"])) == 0
    assert _harnesses(tmp_path) == {"scout": "none", "diagnostician": "none",
                                    "architect": "none", "implementer": "none",
                                    "reviewer": "none"}


# --- the mandated set, moved here from test_cli.py ---
# Tests older than `conductor.init` that stayed behind in the CLI file when
# the init path moved out of it. They are about init, so they live here. A
# fourth, `test_init_refuses_existing`, is gone: it was the `extra=[]` case of
# `test_init_refuses_an_existing_conductor_on_every_path` line for line, minus
# that test's assertion on the message.


def test_init_creates_the_scaffold_and_the_prompt_names_the_map_path(tmp_path, capsys):
    # Renamed on the move: the stdout assertion passes because the BOOTSTRAP
    # PROMPT names the file it is about, not because a scaffold report reaches
    # stdout — the report is dialogue and goes to stderr. The old name read as
    # a claim that init prints its scaffold, which the stream contract forbids.
    assert main(["init", "--dir", str(tmp_path)]) == 0
    assert (tmp_path / "conductor" / "map.toml").is_file()
    assert (tmp_path / "conductor" / "lanes").is_dir()
    assert "map.toml" in capsys.readouterr().out

def test_init_writes_empty_events_and_valid_toml_map(tmp_path, capsys):
    assert main(["init", "--dir", str(tmp_path)]) == 0
    assert (tmp_path / "conductor" / "events.jsonl").read_text(encoding="utf-8") == ""
    data = tomllib.loads(_map_text(tmp_path))
    assert data["schema_version"] == 1 and data["nodes"]

def test_init_then_validate_is_clean(tmp_path, capsys):
    # The scaffold must satisfy its own validation rules end-to-end and print
    # zero warnings (subsumes the deprecated-row check, ADR 0001).
    assert main(["init", "--dir", str(tmp_path)]) == 0
    capsys.readouterr()                       # isolate validate's output from init's
    assert main(["validate", "--dir", str(tmp_path)]) == 0
    assert capsys.readouterr().out == ""


# --- rendered width: the sentences that matter most were the widest ---

def _widest(text, skip=None):
    """The longest rendered line, ignoring any line holding `skip`."""
    lines = [l for l in text.split("\n") if not (skip and skip in l)]
    return max((len(l) for l in lines), default=0)


def test_the_default_run_dialogue_stays_inside_the_width(tmp_path, capsys,
                                                         monkeypatch):
    # Run from inside the project so no absolute path enters a command line:
    # this is the shape a first-time user sees, and _FIRST_ACTION rendered as
    # a single 154-column line in exactly this run.
    monkeypatch.chdir(tmp_path)
    assert main(["init"]) == 0
    assert _widest(capsys.readouterr().err) <= prompts.WIDTH


def test_the_wizard_dialogue_stays_inside_the_width(tmp_path, capsys, monkeypatch):
    # Menus, the no-reviewer gloss (the longest row), and a rejection message,
    # which carries the whole of NAME_RULE and runs past 100 unwrapped.
    monkeypatch.chdir(tmp_path)
    answers = _scripted(['my "app"', "my-app", "", "claude-code"])
    assert conductor.init.run(_build_parser().parse_args(["init"]), ask=answers) == 0
    assert _widest(capsys.readouterr().err) <= prompts.WIDTH


def test_init_degrades_gracefully_when_the_root_cannot_be_written(tmp_path, capsys):
    # A real filesystem condition, not a patched one: a file where the project
    # root should be. `conduct init` is the first command a new user runs, and
    # it was the only one that answered an unwritable root with a traceback.
    blocked = tmp_path / "not-a-directory"
    blocked.write_text("", encoding="utf-8")
    assert main(["init", "--dir", str(blocked)]) == 1
    captured = capsys.readouterr()
    assert captured.out == "" and "cannot write" in captured.err


def test_the_one_path_that_leaves_a_directory_says_how_to_get_unstuck(
        tmp_path, capsys, monkeypatch):
    # Unreachable today — every template is pinned to validate — but it is the
    # single exit that leaves conductor/ behind, and a re-run refuses an
    # existing one. Without the recovery line the user is simply wedged.
    monkeypatch.setattr("conductor.validate.check",
                        lambda root: (["map: contrived failure"], []))
    assert main(["init", "--dir", str(tmp_path)]) == 1
    said = _unwrapped(capsys.readouterr().err)
    assert "map: contrived failure" in said
    assert str(tmp_path / "conductor") in said and "remove it" in said
    assert (tmp_path / "conductor").exists()      # the message is telling the truth
    assert main(["init", "--dir", str(tmp_path)]) == 1   # and a re-run does refuse


def test_the_advised_panel_port_is_the_one_up_actually_binds(tmp_path, capsys):
    # Two argparse defaults and a sentence in init used to carry 7777
    # separately; changing the port could leave init advising the wrong one.
    port = conductor.__main__.DEFAULT_PORT
    assert _build_parser().parse_args(["up"]).port == port
    assert _build_parser().parse_args(["demo"]).port == port
    assert main(["init", "--dir", str(tmp_path)]) == 0
    assert f"http://127.0.0.1:{port}/" in capsys.readouterr().err


# --- the stream contract: stdout is the result, stderr is everything else ---


def test_init_stdout_is_exactly_the_bootstrap_prompt(tmp_path, capsys):
    # `conduct init > setup.txt` must yield a promptable file, not a prompt
    # with a scaffold report and a next-steps list wrapped around it.
    assert main(["init", "--dir", str(tmp_path)]) == 0
    captured = capsys.readouterr()
    assert captured.out == prompts.bootstrap_prompt(str(tmp_path / "conductor"
                                                        / "map.toml"))
    for dialogue in ("scaffolded", "template:", "conduct validate: clean",
                     "Your first action"):
        assert dialogue in captured.err and dialogue not in captured.out


def test_init_stdout_does_not_depend_on_a_tty(tmp_path, capsys):
    # The invariant under the contract: a terminal changes the conversation,
    # never the result. Only the root each was written to may differ.
    quiet, guided = tmp_path / "quiet", tmp_path / "guided"
    quiet.mkdir(), guided.mkdir()
    assert main(["init", "--dir", str(quiet)]) == 0
    quiet_out = capsys.readouterr().out
    assert conductor.init.run(_init_args(guided), ask=_scripted(["", "", ""])) == 0
    guided_out = capsys.readouterr().out
    assert quiet_out.replace(str(quiet), "ROOT") == guided_out.replace(str(guided),
                                                                      "ROOT")
    assert quiet_out != ""


@pytest.mark.parametrize("extra", [[], ["--template", "orbital-decay"]])
def test_init_operational_errors_leave_stdout_empty(tmp_path, capsys, extra):
    if not extra:
        (tmp_path / "conductor").mkdir()               # the refusal path
    assert main(["init", "--dir", str(tmp_path), *extra]) == 1
    captured = capsys.readouterr()
    assert captured.out == "" and captured.err != ""


def test_init_reports_the_validation_it_just_ran(tmp_path, capsys):
    assert main(["init", "--dir", str(tmp_path)]) == 0
    # On stderr specifically: the bootstrap prompt also says `conduct validate`,
    # so reading stdout here would pass without init having checked anything.
    assert "conduct validate: clean" in capsys.readouterr().err


def test_init_template_empty_prints_no_role_prompt_it_cannot_offer(tmp_path, capsys):
    assert main(["init", "--dir", str(tmp_path), "--template", "empty"]) == 0
    out = capsys.readouterr().err
    assert "conduct prompt --role" not in out          # `empty` declares no roles
    assert "conduct up" in out
