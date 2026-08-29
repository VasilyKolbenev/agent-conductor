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


@pytest.fixture
def project(tmp_path):
    """A real project, scaffolded by the real `conduct init`."""
    assert main(["init", "--dir", str(tmp_path)]) == 0
    return tmp_path


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

    assert configure(project, "1", str(executable), "", "MY_TOKEN_NAME", "y") == 0

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

    assert configure(project, "1", str(executable), "", "MY_TOKEN_NAME", "y") == 0

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

    assert configure(project, "1", EXECUTABLE, "", "", "y") == 0

    row = written(project)["providers"][0]
    assert row["protocol"] == PROVIDER_CATALOG[row["provider_id"]].protocol


# -- the claim: no credential value can get in -------------------------------


def test_a_pasted_credential_is_refused_and_never_written(project):
    """`NAME=value` is what somebody in a hurry pastes. It must not be taken.

    The second answer at the same question is a legal name, so this also shows
    the refusal is a re-ask rather than a failure: a person is corrected, not
    thrown out of the flow.
    """
    assert configure(project, "1", EXECUTABLE, "",
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
    configure(project, "1", EXECUTABLE, "", "TOKEN=abc", "MY_TOKEN_NAME", "y")

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
    assert configure(project, "1", EXECUTABLE, "", name, "MY_TOKEN_NAME",
                     "y") == 0

    said = capsys.readouterr().err
    assert f"{name!r} may not be allowed" in said, said
    assert written(project)["providers"][0]["env_allow"] == ["MY_TOKEN_NAME"]


def test_an_allowed_name_is_still_allowed(project):
    """The over-correction control: the refusals must not refuse everything.

    `env_allow` is how a credential reaches a harness at all. A flow that
    refused every name would be secure and useless.
    """
    assert configure(project, "1", EXECUTABLE, "",
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
    assert configure(project, "1", EXECUTABLE, "", "", "n") == 1

    assert not operator_config.provider_config_path(
        project / "conductor").exists()


def test_configuring_a_second_provider_keeps_the_first(project):
    """Adding is adding. A wizard that replaced the file would silently unconfigure."""
    assert configure(project, "1", EXECUTABLE, "", "", "y") == 0
    assert configure(project, "2", "/opt/other/bin/agent", "", "", "y") == 0

    ids = [row.provider_id for row in operator_config.load_provider_configs(
        operator_config.provider_config_path(project / "conductor"))]
    assert len(ids) == 2 and len(set(ids)) == 2


def test_configuring_the_same_provider_twice_corrects_it(project):
    """Two rows under one id is a document the reader refuses.

    So the second pass replaces by identity rather than appending, which is
    also what a person means the second time: they are correcting the path.
    """
    assert configure(project, "1", EXECUTABLE, "", "", "y") == 0
    assert configure(project, "1", "/opt/corrected/bin/agent", "", "", "y") == 0

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

    assert configure(project, "1", EXECUTABLE, "", "", "y") == 1

    assert path.read_bytes() == before
    assert "will not overwrite what it cannot read" in capsys.readouterr().err


def test_a_relative_path_is_refused_and_re_asked(project):
    """The contract wants an absolute pin; the wizard says so in those words."""
    assert configure(project, "1", "bin/agent", EXECUTABLE, "", "", "y") == 0

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
