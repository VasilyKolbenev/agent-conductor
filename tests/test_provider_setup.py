"""`conduct providers`: the flow that replaced an instruction to open an editor.

Configuring a provider meant hand-writing `conductor/providers.json`. Three
surfaces said so and `docs/owner-acceptance.md` called it "the one place the
script sends you back to a file" — an honest description of a gap, not a design.

The claim this module holds is not "a wizard exists". It is four claims, and
they fail in different ways:

1. the complete owner path after `init` requires no text editor — driven end to
   end, ending at a provider the SERVER reports as `available`;
2. no credential value can reach that file, and not because anything screens
   for one: the dialogue asks for environment variable NAMES, and there is
   nowhere in a name that a value fits;
3. a name that would load code into the harness is refused WHILE SOMEBODY IS
   TYPING IT. ADR 0007 records what the alternative costs: the same name in the
   file surfaces later as "the harness could not start the pinned build",
   naming neither the variable nor the file;
4. nothing is spelled on a command line. `--providers` is deliberately a path
   and nothing else, so a flag-shaped setup would put a machine path — and
   eventually a secret — into shell history and CI logs.

The wizard is driven with a scripted prompter rather than a real terminal, and
that is the whole of the substitution: every refusal, every derivation and every
byte written is the production road's.
"""
from __future__ import annotations

import argparse
import json

import pytest

from conductor import provider_setup
from conductor.__main__ import main
from conductor.command import operator_config
from conductor.command.adapters.provider import ProviderConfig

EXECUTABLE = "/opt/harness/bin/agent"
ENTRYPOINT = "/opt/harness/lib/agent.py"

#: What each catalogued provider's pin LOOKS like, stated here rather than read
#: from `providers.entrypoint_rule`.
#:
#: This is the independent expectation, and it has to be independent: the rule
#: is exactly what these tests judge, so a table derived from it would move with
#: a mutation and call the result a pass. Written down, it is a claim about five
#: vendors that a person can check against their documentation.
#:
#: `required` — the pinned executable is an INTERPRETER, and the script it runs
#: is a second absolute path. `forbidden` — the pinned executable is the whole
#: harness, so there is no second file and offering to pin one produces a config
#: this build will not honour.
#: The answer that picks the environment-credential road at the login question,
#: which is the road every row in this module was configured with before that
#: question existed. Named rather than typed as a bare "2" beside a path, so a
#: reader of a script can see which question it answers.
ENV_LOGIN = "2"
#: Which providers this dialogue asks a LOGIN question of, stated here for the
#: same reason `PIN_SHAPES` is: a table derived from `providers.login_hint`
#: would move with a mutation of that rule and call the result a pass. Only the
#: two harnesses whose transport really drives a vendor login are asked; the
#: other three are TOLD they read a credential from the environment.
LOGIN_ASKED = {
    "claude-code": True,
    "codex": True,
    "deepseek-harness": False,
    "grok-build": False,
    "kimi-code": False,
}
PIN_SHAPES = {
    "claude-code": "forbidden",
    "codex": "forbidden",
    "deepseek-harness": "required",
    "grok-build": "forbidden",
    "kimi-code": "forbidden",
}


@pytest.fixture
def project(tmp_path):
    """A real project, scaffolded by the real `conduct init`."""
    assert main(["init", "--dir", str(tmp_path)]) == 0
    return tmp_path


def menu_choice(provider_id: str) -> str:
    """The number a person types to pick this provider from the printed menu."""
    from conductor.command.providers import PROVIDER_CATALOG

    return str(sorted(PROVIDER_CATALOG).index(provider_id) + 1)


def pin_answers(provider_id: str, executable, entrypoint) -> list[str]:
    """The path answers this provider's dialogue asks for, per `PIN_SHAPES`.

    A `forbidden` row is given NO entrypoint answer, so a dialogue that asked
    for one would consume the env-name answer here and the test would fail on
    the shifted script rather than on a hidden default. The login question
    follows the same rule: it is asked only of a provider whose transport really
    drives a vendor login, and the answer below picks the environment road --
    the one every one of these rows was configured with before the question
    existed.
    """
    answers = [menu_choice(provider_id), str(executable)]
    if PIN_SHAPES[provider_id] == "required":
        answers.append(str(entrypoint))
    if LOGIN_ASKED[provider_id]:
        answers.append("2")
    return answers


def scripted(*answers):
    """One prompter that reads a fixed script, as a terminal would read a person."""
    remaining = iter(answers)

    def ask(_prompt: str) -> str:
        return next(remaining)

    return ask


def configure(root, *answers):
    return provider_setup.run(argparse.Namespace(dir=str(root)),
                              ask=scripted(*answers))


def written(root):
    path = operator_config.provider_config_path(root / "conductor")
    return json.loads(path.read_text(encoding="utf-8"))


# -- the claim: no editor, end to end ----------------------------------------


def test_the_owner_path_after_init_reaches_an_available_provider(
        project, tmp_path):
    """init -> providers -> the SERVER answers `available`. No file was edited.

    The last leg is the one that matters, and it is asked over the wire rather
    than of the file: a wizard that wrote something nothing could resolve would
    satisfy every other test in this module and leave the owner exactly where
    they started. `conduct up` reads the file once at startup and hands the
    result to the server, so that is the road driven here.
    """
    import json as _json
    import threading
    import urllib.request

    from conductor import server

    executable = tmp_path / "harness-executable"
    executable.write_text("", encoding="utf-8", newline="\n")

    assert configure(project, "1", str(executable), ENV_LOGIN, "MY_TOKEN_NAME", "y") == 0

    pinned = operator_config.load_provider_configs(
        operator_config.provider_config_path(project / "conductor"))
    assert [row.provider_id for row in pinned] == ["claude-code"]
    srv = server.build(project, port=0, providers=pinned)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    base = "http://127.0.0.1:%d" % srv.server_address[1]
    try:
        call = urllib.request.Request(
            base + "/command/workflows",
            headers={"Host": base.removeprefix("http://")}, method="GET")
        with urllib.request.urlopen(call, timeout=10) as answer:
            payload = _json.loads(answer.read())
    finally:
        srv.shutdown()
        thread.join(timeout=5)
        srv.server_close()

    availability = {row["provider_id"]: row["availability"]
                    for row in payload["providers"]}
    assert availability["claude-code"] == "available", availability
    # And nothing else was configured by configuring one.
    assert {state for provider, state in availability.items()
            if provider != "claude-code"} == {"unconfigured"}


def test_the_wizard_writes_what_the_reader_admits(project, tmp_path):
    """Round trip through the production reader, not through this module's idea."""
    executable = tmp_path / "harness-executable"
    executable.write_text("", encoding="utf-8", newline="\n")

    assert configure(project, "1", str(executable), ENV_LOGIN, "MY_TOKEN_NAME", "y") == 0

    configs = operator_config.load_provider_configs(
        operator_config.provider_config_path(project / "conductor"))
    assert len(configs) == 1
    assert configs[0].executable == str(executable)
    assert configs[0].env_allow == ("MY_TOKEN_NAME",)


def test_the_protocol_is_derived_and_never_asked_for(project):
    """A fact about the provider, held by the catalogue.

    Asked for, it becomes a way to get it wrong; and a wizard that spelled one
    would be naming a provider's protocol in generic code.
    """
    from conductor.command.providers import PROVIDER_CATALOG

    assert configure(project, "1", EXECUTABLE, ENV_LOGIN, "", "y") == 0

    row = written(project)["providers"][0]
    assert row["protocol"] == PROVIDER_CATALOG[row["provider_id"]].protocol


# -- the claim: no credential value can get in -------------------------------


def test_a_pasted_credential_is_refused_and_never_written(project):
    """`NAME=value` is what somebody in a hurry pastes. It must not be taken.

    The second answer at the same question is a legal name, so this also shows
    the refusal is a re-ask rather than a failure: a person is corrected, not
    thrown out of the flow.
    """
    assert configure(project, "1", EXECUTABLE, ENV_LOGIN,
"ANTHROPIC_API_KEY=sk-live-secret", "MY_TOKEN_NAME",
                     "y") == 0

    document = written(project)
    assert "sk-live-secret" not in json.dumps(document)
    assert document["providers"][0]["env_allow"] == ["MY_TOKEN_NAME"]


def test_the_refusal_says_the_value_is_read_from_the_environment(
        project, capsys):
    """Told only "invalid", a person retypes the same thing with the same value.

    This is the witness for the `=` arm specifically, and it has to be the
    MESSAGE rather than the outcome: `NAME=value` is refused by the name grammar
    too, so deleting the arm still keeps every credential out of the file. What
    it deletes is the only sentence that tells somebody WHY, and a flow that
    answers "that is not a name" to a pasted key is one they will fight.
    """
    configure(project, "1", EXECUTABLE, ENV_LOGIN, "TOKEN=abc", "MY_TOKEN_NAME", "y")

    said = capsys.readouterr().err
    assert "looks like NAME=value" in said, said
    assert "read from your environment" in said, said
    assert "abc" not in said, "the refusal echoed the value back"


@pytest.mark.parametrize("name", ["PYTHONPATH", "LD_PRELOAD", "NODE_OPTIONS"])
def test_a_name_that_would_inject_code_is_refused_while_it_is_typed(
        project, capsys, name):
    """ADR 0007's stated gap, closed at the surface where a person can act.

    These are refused at the spawn door already. That refusal arrives as a
    harness that will not start, naming neither the variable nor the file, long
    after the person who typed it has moved on.
    """
    assert configure(project, "1", EXECUTABLE, ENV_LOGIN, name, "MY_TOKEN_NAME",
                     "y") == 0

    said = capsys.readouterr().err
    assert f"{name!r} may not be allowed" in said, said
    assert written(project)["providers"][0]["env_allow"] == ["MY_TOKEN_NAME"]


def test_an_allowed_name_is_still_allowed(project):
    """The over-correction control: the refusals must not refuse everything.

    `env_allow` is how a credential reaches a harness at all. A flow that
    refused every name would be secure and useless.
    """
    assert configure(project, "1", EXECUTABLE, ENV_LOGIN,
"ANTHROPIC_API_KEY OPENAI_API_KEY", "y") == 0

    assert written(project)["providers"][0]["env_allow"] == [
        "ANTHROPIC_API_KEY", "OPENAI_API_KEY"]


# -- the claim: nothing is spelled on a command line -------------------------


def test_the_providers_command_takes_no_setting_as_a_flag():
    """A path or a name on argv is a path or a name in shell history and CI logs.

    Read off the parser rather than asserted about the source, so a flag added
    later is caught by what argparse would accept, not by a grep.
    """
    from conductor.__main__ import _build_parser

    chooser = next(action for action in _build_parser()._actions
                   if hasattr(action, "choices") and action.choices
                   and "providers" in action.choices)
    options = {option
               for action in chooser.choices["providers"]._actions
               for option in action.option_strings}

    assert options <= {"-h", "--help", "--dir"}, sorted(options)


def test_a_non_terminal_is_refused_rather_than_defaulted(project, capsys):
    """Every answer is a fact about one machine, and none has a default.

    `conduct init` may fall back to a template when nobody is there to ask; this
    cannot. There is no default absolute path, and inventing one would write a
    provider configuration nobody chose.
    """
    assert main(["providers", "--dir", str(project)]) == 1

    said = capsys.readouterr().err
    assert "needs a terminal" in said, said
    assert not operator_config.provider_config_path(
        project / "conductor").exists()


# -- what it does with what is already there ---------------------------------


def test_declining_the_confirmation_writes_nothing(project):
    """The last question is a real question."""
    assert configure(project, "1", EXECUTABLE, ENV_LOGIN, "", "n") == 1

    assert not operator_config.provider_config_path(
        project / "conductor").exists()


def test_configuring_a_second_provider_keeps_the_first(project):
    """Adding is adding. A wizard that replaced the file would silently unconfigure."""
    assert configure(project, "1", EXECUTABLE, ENV_LOGIN, "", "y") == 0
    assert configure(
        project, "2", "/opt/other/bin/agent", ENV_LOGIN, "", "y") == 0

    ids = [row.provider_id for row in operator_config.load_provider_configs(
        operator_config.provider_config_path(project / "conductor"))]
    assert len(ids) == 2 and len(set(ids)) == 2


def test_configuring_the_same_provider_twice_corrects_it(project):
    """Two rows under one id is a document the reader refuses.

    So the second pass replaces by identity rather than appending, which is
    also what a person means the second time: they are correcting the path.
    """
    assert configure(project, "1", EXECUTABLE, ENV_LOGIN, "", "y") == 0
    assert configure(
        project, "1", "/opt/corrected/bin/agent", ENV_LOGIN, "", "y") == 0

    configs = operator_config.load_provider_configs(
        operator_config.provider_config_path(project / "conductor"))
    assert len(configs) == 1
    assert configs[0].executable == "/opt/corrected/bin/agent"


def test_a_file_this_build_cannot_read_is_not_overwritten(project, capsys):
    """Refuse rather than clobber: those rows are somebody's configuration.

    A wizard that started from an empty list whenever it could not parse the
    file would quietly delete every provider in it, and the person would find
    out when a run refused.
    """
    path = operator_config.provider_config_path(project / "conductor")
    path.write_text('{"schema_version": 99, "providers": []}',
                    encoding="utf-8", newline="\n")
    before = path.read_bytes()

    assert configure(project, "1", EXECUTABLE, ENV_LOGIN, "", "y") == 1

    assert path.read_bytes() == before
    assert "will not overwrite what it cannot read" in capsys.readouterr().err


def test_a_relative_path_is_refused_and_re_asked(project):
    """The contract wants an absolute pin; the wizard says so in those words."""
    assert configure(
        project, "1", "bin/agent", EXECUTABLE, ENV_LOGIN, "", "y") == 0

    assert written(project)["providers"][0]["executable"] == EXECUTABLE


# -- the writer, held to the reader ------------------------------------------


def test_the_writer_and_the_reader_agree_in_both_directions(tmp_path):
    """One module owns the file's shape, so a round trip is the whole guard."""
    path = tmp_path / "providers.json"
    configs = (
        ProviderConfig(provider_id="alpha", executable="/opt/a",
                       protocol="claude-code-headless-v1",
                       env_allow=["ONE", "TWO"]),
        ProviderConfig(provider_id="beta", executable="/opt/b",
                       protocol="codex-headless-v1", entrypoint="/opt/b/main"),
    )

    operator_config.save_provider_configs(path, configs)

    assert operator_config.load_provider_configs(path) == configs


def test_the_writer_omits_what_the_operator_pinned_none_of(tmp_path):
    """Absent and empty are one fact, and a file must spell it one way.

    `_reviewed_row` fills both optional halves in on read, so writing them back
    would put two spellings of "pinned none" into every file this produces.
    """
    path = tmp_path / "providers.json"

    operator_config.save_provider_configs(path, [ProviderConfig(
        provider_id="alpha", executable="/opt/a",
        protocol="claude-code-headless-v1")])

    row = json.loads(path.read_text(encoding="utf-8"))["providers"][0]
    assert set(row) == {"provider_id", "executable", "protocol"}


def test_the_writer_refuses_a_document_its_own_reader_would_reject(tmp_path):
    """Two rows under one id, refused before anything is written.

    A writer that produced a file its reader refuses would tell somebody their
    configuration was saved and leave them unable to start the project.
    """
    path = tmp_path / "providers.json"
    twice = [ProviderConfig(provider_id="alpha", executable="/opt/a",
                            protocol="claude-code-headless-v1"),
             ProviderConfig(provider_id="alpha", executable="/opt/b",
                            protocol="codex-headless-v1")]

    with pytest.raises(operator_config.OperatorConfigError, match="more than once"):
        operator_config.save_provider_configs(path, twice)

    assert not path.exists()


# -- the claim: every pin shape in the catalogue, not just the first row ------
#
# The end-to-end test above drives the catalogue's FIRST row, and that is the
# one shape where pressing Enter at the entrypoint question happens to be
# right. Everything below exists because that was the whole of the coverage,
# and two real defects lived in the space it did not reach: an interpreter-
# backed provider written with no entrypoint (`rc=0`, then `executable_absent`
# from the server), and a single-executable provider written WITH one (`rc=0`,
# then `version_mismatch`). Both were reported as "wrote providers.json".


def recording():
    """A prompter that keeps the QUESTIONS as well as answering them.

    The question text is handed to `ask` and never printed to stderr, so a test
    that reads captured output cannot see which questions were put. A dialogue
    that stops asking something is exactly what has to be measured here.
    """
    asked: list[str] = []
    answers: list[str] = []

    def ask(prompt: str) -> str:
        asked.append(prompt)
        return answers.pop(0)

    return asked, answers, ask


def pinned_files(tmp_path, provider_id):
    """Two real files to pin, so availability turns on shape and not on disk."""
    executable = tmp_path / f"{provider_id}-executable"
    entrypoint = tmp_path / f"{provider_id}-entrypoint"
    for path in (executable, entrypoint):
        path.write_text("", encoding="utf-8", newline="\n")
    return executable, entrypoint


def server_availability(root):
    """What `conduct up` would report, asked of the road `conduct up` uses."""
    from conductor.command.providers import resolve_providers

    pinned = operator_config.load_provider_configs(
        operator_config.provider_config_path(root / "conductor"))
    counter = iter(range(1, 10_000))
    resolution = resolve_providers(
        pinned, root=root, clock=lambda: "2026-01-01T00:00:00Z",
        ids=lambda kind: f"{kind}-{next(counter)}")
    return {row.provider_id: row.availability for row in resolution.contracts}


def test_every_catalogued_provider_has_a_stated_pin_shape():
    """`PIN_SHAPES` is the independent expectation, so it must stay complete.

    Both directions. A provider added to the catalogue with no row here fails
    until somebody states its pin shape, which is the point at which the
    question "does this run through an interpreter?" is cheap to answer; and a
    row here for a provider that no longer exists is a stale expectation the
    tests below would quietly stop exercising.
    """
    from conductor.command.providers import PROVIDER_CATALOG

    assert set(PIN_SHAPES) == set(PROVIDER_CATALOG)
    assert set(PIN_SHAPES.values()) == {"required", "forbidden"}


@pytest.mark.parametrize("provider_id", sorted(PIN_SHAPES))
def test_every_pin_shape_reaches_an_available_provider(
        project, tmp_path, provider_id):
    """The editor-free path, driven for EVERY row, ending at the server's word.

    `available` is the whole assertion, and it is asked of `resolve_providers`
    -- the function `conduct up` hands its file to -- rather than of any
    convenience the wizard itself calls. Before the pin shape was derived, four
    of these five failed: `deepseek-harness` at `executable_absent` and the
    other rows at `version_mismatch` had an entrypoint been offered to them.
    """
    executable, entrypoint = pinned_files(tmp_path, provider_id)

    assert configure(project,
                     *pin_answers(provider_id, executable, entrypoint),
                     "MY_TOKEN_NAME", "y") == 0

    assert server_availability(project)[provider_id] == "available"


def test_an_interpreter_backed_provider_refuses_an_empty_entrypoint(
        project, tmp_path, capsys):
    """Enter is what the old dialogue invited, and it produced a dead config.

    The refusal is a re-ask, and it names the ENTRYPOINT: a message saying "a
    provider needs an executable" under this question sends somebody back to
    check a path that was never the problem.
    """
    executable, entrypoint = pinned_files(tmp_path, "deepseek-harness")

    assert configure(project, menu_choice("deepseek-harness"), str(executable),
                     "", str(entrypoint), "MY_TOKEN_NAME", "y") == 0

    said = capsys.readouterr().err
    assert "needs an entrypoint" in said, said
    assert "executable; there is no default" not in said, said
    assert written(project)["providers"][0]["entrypoint"] == str(entrypoint)
    assert server_availability(project)["deepseek-harness"] == "available"


@pytest.mark.parametrize("provider_id", sorted(
    name for name, shape in PIN_SHAPES.items() if shape == "forbidden"))
def test_a_single_executable_provider_is_never_asked_for_an_entrypoint(
        project, tmp_path, provider_id):
    """Not "asked and ignored" -- the question is not put at all.

    Measured on the QUESTIONS, because a dialogue that still asked and then
    discarded the answer would leave the same three durable facts as one that
    never asked, and the person would still have typed a path this build cannot
    honour. A question with one acceptable answer is a way to get it wrong.
    """
    executable, _ = pinned_files(tmp_path, provider_id)
    asked, answers, ask = recording()
    answers.extend([menu_choice(provider_id), str(executable), ENV_LOGIN,
                    "MY_TOKEN_NAME", "y"])

    assert provider_setup.run(
        argparse.Namespace(dir=str(project)), ask=ask) == 0

    assert not [question for question in asked
                if "entrypoint" in question.lower()], asked
    assert "entrypoint" not in written(project)["providers"][0]
    assert server_availability(project)[provider_id] == "available"


def test_the_wizard_states_the_availability_the_server_will_report(
        project, tmp_path, capsys):
    """"wrote providers.json" was a claim nothing had checked.

    Both directions, because a line that always said `available` would pass the
    first half: a pin whose file is not there yet is written, said to be
    `executable_absent`, and the absent path is named.
    """
    executable, _ = pinned_files(tmp_path, "claude-code")

    assert configure(project, "1", str(executable), ENV_LOGIN, "MY_TOKEN_NAME", "y") == 0
    said = capsys.readouterr().err
    assert "availability available" in said, said

    missing = tmp_path / "not-installed-yet"
    assert configure(
        project, "1", str(missing), ENV_LOGIN, "MY_TOKEN_NAME", "y") == 0
    said = capsys.readouterr().err
    assert "availability executable_absent" in said, said
    # The NOTE, not the summary. `executable  <path>` prints the same path one
    # line above, so asserting the path alone passed with the note deleted --
    # a mutation found that, and it is the reason this reads the sentence.
    note = next((line for line in said.splitlines()
                 if "is not on this machine yet" in line), "")
    assert str(missing) in note, said
    assert server_availability(project)["claude-code"] == "executable_absent"


def test_the_pin_shape_rule_answers_optional_for_a_protocol_in_neither_set():
    """The over-correction control on the rule itself.

    A protocol this build does not catalogue constrains the pin NEITHER way, and
    `optional` is the honest word for that. A rule that answered `required` for
    everything it did not recognise would demand a second path from a provider
    that has none, which is the defect this closed, in the other direction.
    """
    from conductor.command import providers

    assert providers.entrypoint_rule(
        "a-protocol-this-build-never-reviewed") == providers.ENTRYPOINT_OPTIONAL
    assert providers.ENTRYPOINT_RULES == {"required", "forbidden", "optional"}


# -- the claim: a refusal never repeats the token back -----------------------
#
# `NAME=value` was refused with only its name half quoted, which was right. A
# bare key-shaped token -- what a paste actually looks like when somebody
# misreads the question -- fell through to the name-grammar arm and was echoed
# WHOLE inside its own refusal, onto the screen, into the scrollback and into
# anything capturing stderr.

#: A token shaped like a live vendor key and belonging to nobody. It is spelled
#: with a marker rather than a plausible body so that finding it in any file or
#: any log is unambiguous.
SYNTHETIC_KEY = "sk-live-SYNTHETIC-DO-NOT-USE"


@pytest.mark.parametrize("typed", [
    SYNTHETIC_KEY,                        # a bare paste into the wrong question
    f"{SYNTHETIC_KEY}=x",                 # a paste whose own LEFT half is secret
    f"ANTHROPIC_API_KEY={SYNTHETIC_KEY}",  # the shape that was already handled
])
def test_a_pasted_credential_is_never_repeated_back(project, capsys, typed):
    """No arm of the env-name question may put the token on the screen.

    Three shapes rather than one, because the arm that catches each is
    different: the name grammar, the `=` split whose head is not a name either,
    and the `=` split whose head IS one. The third is the case that was already
    right, and it is here so a redaction that swallowed everything would be
    caught by the test below rather than by nobody.
    """
    assert configure(project, "1", EXECUTABLE, ENV_LOGIN, typed,
                     "MY_TOKEN_NAME", "y") == 0

    said = capsys.readouterr().err
    assert SYNTHETIC_KEY not in said, said
    assert "MY_TOKEN_NAME" in json.dumps(written(project))
    assert SYNTHETIC_KEY not in json.dumps(written(project))


def test_a_refusal_still_quotes_a_head_that_is_itself_a_name(project, capsys):
    """The over-correction control: redaction must not eat the useful case.

    `MY_TOKEN=abc` is a person who understood the question and typed one
    character too many. Naming `'MY_TOKEN'` back is how they see that; refusing
    with a position and no name would make the good case as opaque as the bad
    one, and the value half still may not appear.
    """
    configure(project, "1", EXECUTABLE, ENV_LOGIN, "MY_TOKEN=abc", "MY_TOKEN", "y")

    said = capsys.readouterr().err
    assert "'MY_TOKEN' looks like NAME=value" in said, said
    assert "abc" not in said, said


def test_a_refusal_names_which_entry_it_means_when_several_were_typed(
        project, capsys):
    """A position locates a typo as well as a quotation does, and carries nothing.

    Somebody who typed three names needs to know which one is wrong. That is the
    only thing the echoed token was doing that a person needed.
    """
    assert configure(project, "1", EXECUTABLE, ENV_LOGIN,
f"ONE TWO {SYNTHETIC_KEY}", "ONE TWO", "y") == 0

    said = capsys.readouterr().err
    assert "entry 3 of 3" in said, said
    assert SYNTHETIC_KEY not in said, said
    assert written(project)["providers"][0]["env_allow"] == ["ONE", "TWO"]


def test_the_preamble_says_the_terminal_echoes_what_you_type(project, capsys):
    """The honest half of the claim, since this command cannot silence a terminal.

    A dialogue that said only "nothing you type here is a secret" invites the
    reading that pasting one is safe. It is not: the terminal has already drawn
    it. What this command controls is whether IT repeats it, and that is what it
    promises.
    """
    configure(project, "1", EXECUTABLE, ENV_LOGIN, "", "n")

    said = capsys.readouterr().err
    assert "TERMINAL echoes what you type" in said, said
    assert "never repeat one back" in said, said


# -- the input that ends -----------------------------------------------------


def ending(*answers):
    """A prompter that answers, then reaches the end of its input.

    What a real terminal does when a pipe closes, a person presses Ctrl+Z, or
    the command is run somewhere with nothing to read.
    """
    remaining = iter(answers)

    def ask(_prompt: str) -> str:
        try:
            return next(remaining)
        except StopIteration:
            raise EOFError from None

    return ask


@pytest.mark.parametrize("given", [
    (),                                  # ends at the very first question
    ("1",),                              # ends midway through the pin
    ("1", EXECUTABLE, "MY_TOKEN_NAME"),  # ends at the confirmation
])
def test_an_input_that_ends_says_so_in_the_products_own_words(
        project, capsys, given):
    """Python's name for this is "EOF when reading a line", and it reached a
    person's screen.

    Nobody who sees that has done anything wrong -- a pipe closed, or this was
    run where there is nothing to type into. `docs/owner-acceptance.md` asks
    that every failure be understandable without opening a terminal log, and an
    exception's own repr is the opposite of that. All three ending points are
    driven, because the last one is a different `ask` call in a different arm.
    """
    assert provider_setup.run(
        argparse.Namespace(dir=str(project)), ask=ending(*given)) == 1

    said = capsys.readouterr().err
    assert "the input ended before" in said, said
    assert "nothing was written" in said, said
    assert "EOF when reading a line" not in said, said
    path = operator_config.provider_config_path(project / "conductor")
    assert not path.exists(), "a refused dialogue wrote a file"


# -- which login, asked exactly where there is a choice -----------------------


@pytest.mark.parametrize("provider_id", sorted(LOGIN_ASKED))
def test_the_login_question_is_put_only_where_a_login_is_driven(
        project, tmp_path, capsys, provider_id):
    """A question with one acceptable answer is a way to get it wrong.

    So a provider whose transport drives no vendor login is TOLD which login it
    uses, and the two that do are asked. Measured on the dialogue rather than on
    the row, because both roads write the same `api_key` and only one of them
    put a choice to a person.
    """
    executable, entrypoint = pinned_files(tmp_path, provider_id)
    assert configure(project, *pin_answers(provider_id, executable, entrypoint),
                     "MY_TOKEN_NAME", "y") == 0

    said = capsys.readouterr().err
    if LOGIN_ASKED[provider_id]:
        assert f"How does {provider_id} sign in?" in said, said
    else:
        assert "sign in?" not in said, said
        assert "drives no vendor login" in said, said
    assert written(project)["providers"][0].get("auth", "api_key") == "api_key"


def test_the_vendor_login_writes_a_directory_and_prints_the_command_to_run(
        project, tmp_path, capsys):
    """The dialogue asks WHERE the login is kept and never for the login itself.

    A relative answer is re-asked, as every other path is. What the person is
    given back is the exact command to run in their own shell: this build never
    performs a login, and a product that did would be holding an account.
    """
    executable, _ = pinned_files(tmp_path, "claude-code")
    home = tmp_path / "auth" / "claude-code"

    assert configure(project, menu_choice("claude-code"), str(executable),
                     "1", "auth/claude-code", str(home), "", "y") == 0

    row = written(project)["providers"][0]
    assert row["auth"] == "subscription"
    assert row["auth_home"] == str(home)
    said = capsys.readouterr().err
    assert f"CLAUDE_CONFIG_DIR={home}" in said, said
    assert "auth login --claudeai" in said, said
    assert "this build never runs a login" in said, said
    assert "login       subscription" in said, said
    assert f"login dir   {home}" in said, said


def test_a_subscription_row_refuses_an_api_billing_name_while_it_is_typed(
        project, tmp_path, capsys):
    """Refused at the question, not at the finished row: a dialogue that took
    every answer and then refused would cost a person the whole conversation."""
    executable, _ = pinned_files(tmp_path, "claude-code")
    home = tmp_path / "auth" / "claude-code"

    assert configure(project, menu_choice("claude-code"), str(executable),
                     "1", str(home), "ANTHROPIC_API_KEY", "HTTPS_PROXY",
                     "y") == 0

    said = capsys.readouterr().err
    assert "pays for model access through an API account" in said, said
    assert written(project)["providers"][0]["env_allow"] == ["HTTPS_PROXY"]
