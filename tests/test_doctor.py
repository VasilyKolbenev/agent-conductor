"""Tests for `conduct doctor` — readiness, and its boundary with `validate`.

Every test calls `main(argv)` and reads the exit code and the capsys-captured
streams, so what is asserted is the command's own output rather than a helper
that happens to agree with it. `doctor.inspect` is built directly only where a
test needs to relate the rendered report back to the checks it came from.

The corpus below is one project shape per readiness answer: no scaffold, a map
that is still a template, nothing reporting, everything stale, a role nobody
holds, a harness the registry has never heard of, an unreadable map and an
unreadable lane. Every way a check can come back UNKNOWN is built here,
because "green on something it never inspected" is the defect this command
exists in order not to have.
"""
import json
from datetime import datetime, timedelta, timezone

import pytest
from conductor import doctor, harnesses, prompts, store, templates, validate
from conductor.__main__ import main
from tests.test_store import write_project

# A map about a real project: node ids and labels no built-in template writes,
# one declared role, and a harness the bundled registry knows.
REAL_MAP = ('schema_version = 1\nproject = "p"\n'
            '[[nodes]]\nid = "api"\nlabel = "the api service"\nkind = "artifact"\n'
            '[[cycle.roles]]\nid = "implementer"\nharness = "claude-code"\n'
            'reviews = []\n')

# The same map naming a harness id nobody registered — the shape a typo makes.
TYPO_MAP = REAL_MAP.replace('"claude-code"', '"claud-code"')

# The same map with a second declared role nobody is running.
TWO_ROLE_MAP = REAL_MAP + '[[cycle.roles]]\nid = "reviewer"\nreviews = []\n'


def lane(author="claude", role="implementer", minutes_ago=0):
    """One schema-valid lane, aged by `minutes_ago` against the merger's clock."""
    when = datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)
    body = {"schema_version": 1, "author": author, "updated": when.isoformat()}
    if role is not None:
        body["role"] = role
    return json.dumps(body)


def role_map(role_id):
    """A minimal valid map whose one role carries `role_id`, whatever it holds."""
    return ('schema_version = 1\n[[nodes]]\nid = "api"\nlabel = "the api service"\n'
            f'[[cycle.roles]]\nid = {json.dumps(role_id)}\nreviews = []\n')


def ready_project(tmp_path):
    """A project every check comes back OK on."""
    return write_project(tmp_path, map_toml=REAL_MAP, lanes={"claude": lane()})


def corpus(tmp_path):
    """One project per readiness answer, each in its own directory."""
    unscaffolded = tmp_path / "unscaffolded"
    unscaffolded.mkdir()
    return {
        "unscaffolded": unscaffolded,
        "template": write_project(tmp_path / "template",
                                  map_toml=templates.get(templates.DEFAULT)),
        "no lanes": write_project(tmp_path / "nolanes", map_toml=REAL_MAP),
        "stale": write_project(tmp_path / "stale", map_toml=REAL_MAP,
                               lanes={"claude": lane(minutes_ago=10_000)}),
        "unheld role": write_project(tmp_path / "unheld", map_toml=TWO_ROLE_MAP,
                                     lanes={"claude": lane()}),
        "unknown harness": write_project(tmp_path / "typo", map_toml=TYPO_MAP,
                                         lanes={"claude": lane()}),
        "broken map": write_project(tmp_path / "brokenmap", map_toml="= not toml"),
        "broken lane": write_project(tmp_path / "brokenlane", map_toml=REAL_MAP,
                                     lanes={"bad": "{not json"}),
        # Two shapes validate has nothing to say about, which is why they are
        # here: a map with no role to hand out, and one whose only role cannot
        # be named on a command line. Both are legal Protocol v1.
        "no roles": write_project(tmp_path / "noroles",
                                  map_toml='schema_version = 1\n[[nodes]]\n'
                                           'id = "api"\nlabel = "the api service"\n'),
        "untypable role": write_project(tmp_path / "untypable",
                                        map_toml=role_map("scout x"),
                                        lanes={"claude": lane()}),
    }


def report(capsys, root, expect):
    """Run `conduct doctor` on `root`, assert its exit code, return stdout."""
    assert main(["doctor", "--dir", str(root)]) == expect
    captured = capsys.readouterr()
    assert captured.err == ""
    return captured.out


def outcomes(out):
    """`{check name: outcome}` read back off the rendered report."""
    found = {}
    for line in out.splitlines():
        if line.startswith("[") and "] " in line:
            outcome, _, name = line.partition("] ")
            found[name] = outcome[1:]
    return found


def commands(out):
    """Every command line of a report, as the argv `main` would be given."""
    return [line[len(doctor.COMMAND_PREFIX):].split(" ")[1:]
            for line in out.splitlines()
            if line.startswith(doctor.COMMAND_PREFIX)]


class _FakeServer:
    """A bound server that returns from `serve_forever` at once, as Ctrl-C does."""

    server_address = ("127.0.0.1", 7777)

    def serve_forever(self):
        raise KeyboardInterrupt

    def server_close(self):
        pass


# --- validate is untouched, and doctor is not a second copy of it ------------


def test_a_project_validate_passes_in_silence_can_still_be_unready(tmp_path, capsys):
    # The boundary in one project. `conduct init` writes a map that validates
    # perfectly and describes nobody's project; validate is right to say
    # nothing about it, and doctor is right to refuse it. Were doctor asking
    # validate's questions, this project would come back the same way twice.
    assert main(["init", "--dir", str(tmp_path)]) == 0
    capsys.readouterr()
    assert main(["validate", "--dir", str(tmp_path)]) == 0
    assert capsys.readouterr() == ("", "")
    assert outcomes(report(capsys, tmp_path, 1))["map"] == doctor.FINDING


def test_doctor_repeats_no_line_validate_already_prints(tmp_path, capsys):
    # Six projects whose files do not load or do not fit the schema. Every one
    # makes validate print something, and doctor must print none of it: a
    # schema error has one owner, and doctor's job is to say which readiness
    # question it cost and which command reports it.
    broken = {
        "map": dict(map_toml="= not toml"),
        "nodeless": dict(map_toml="schema_version = 1\n"),
        "lane": dict(map_toml=REAL_MAP, lanes={"bad": "{not json"}),
        "author": dict(map_toml=REAL_MAP, lanes={"impostor": lane(author="claude")}),
        "both": dict(map_toml="= not toml", lanes={"bad": "{not json"}),
        "version": dict(map_toml=REAL_MAP,
                        lanes={"claude": lane().replace('"schema_version": 1',
                                                        '"schema_version": 2')}),
    }
    for name, kwargs in broken.items():
        root = write_project(tmp_path / name, **kwargs)
        main(["validate", "--dir", str(root)])
        from_validate = {ln.strip() for ln in capsys.readouterr().out.splitlines()
                         if ln.strip()}
        main(["doctor", "--dir", str(root)])
        from_doctor = {ln.strip() for ln in capsys.readouterr().out.splitlines()
                       if ln.strip()}
        assert from_validate and not (from_validate & from_doctor), name


@pytest.mark.parametrize("field, variants", [
    # Directory names stay free of spaces: a quoted `--dir` in one report and
    # a bare one in another would differ for a reason that is not the subject.
    ("map", {"syntax": "= not toml",
             "nonodes": "schema_version = 1\n",
             "duplicate-ids": ('schema_version = 1\n[[nodes]]\nid = "a"\n'
                               '[[nodes]]\nid = "a"\n'),
             "noversion": '[[nodes]]\nid = "a"\nlabel = "a"\n'}),
    ("lane", {"notjson": "{not json",
              "notanobject": "[1, 2]",
              "wrongauthor": lane(author="somebody-else"),
              "noupdated": json.dumps({"schema_version": 1, "author": "claude"})}),
])
def test_doctor_answers_the_same_however_the_file_underneath_is_broken(
        tmp_path, capsys, field, variants):
    # The strong form of the boundary, and the one a wrapped line cannot hide.
    # Each variant makes validate print something different; doctor knows only
    # that the file did not load, so all four of its reports must be the same
    # bytes. Echo one word of validate's message into a detail and they stop
    # being.
    messages, reports = set(), set()
    for name, text in variants.items():
        root = write_project(tmp_path / name,
                             map_toml=text if field == "map" else REAL_MAP,
                             lanes=None if field == "map" else {"claude": text})
        main(["validate", "--dir", str(root)])
        messages.add(capsys.readouterr().out)
        main(["doctor", "--dir", str(root)])
        reports.add(capsys.readouterr().out.replace(str(root), "<root>"))
    assert len(messages) == len(variants)      # validate tells them apart
    assert len(reports) == 1                   # doctor never learned how


def test_doctor_leaves_validates_own_bytes_and_exit_codes_alone(tmp_path, capsys):
    # Whatever doctor says about a project, `conduct validate` still prints
    # exactly what `validate.check` computed and nothing else, on the same two
    # streams, with the same code — findings on stdout even when it exits 1,
    # and not one byte for a clean project.
    cases = {"clean": dict(map_toml=REAL_MAP, lanes={"claude": lane()}),
             "template": dict(map_toml=templates.get(templates.DEFAULT)),
             "drifted": dict(map_toml=REAL_MAP, lanes={"claude": lane().replace(
                 '"schema_version": 1', '"schema_version": 2')}),
             "broken": dict(map_toml="= not toml")}
    for name, kwargs in cases.items():
        root = write_project(tmp_path / name, **kwargs)
        errors, warnings = validate.check(root)
        assert main(["validate", "--dir", str(root)]) == (1 if errors else 0), name
        captured = capsys.readouterr()
        assert captured.out == "".join(f"{line}\n" for line in (errors or warnings))
        assert captured.err == "", name


# --- never green on something that was never inspected ----------------------


@pytest.mark.parametrize("name, kwargs, unknown", [
    ("unreadable map", dict(map_toml="= not toml"), {"map", "roles", "harnesses"}),
    ("invalid map", dict(map_toml="schema_version = 1\n"),
     {"map", "roles", "harnesses"}),
    ("every lane broken", dict(map_toml=REAL_MAP, lanes={"bad": "{not json"}),
     {"lanes", "roles"}),
])
def test_a_check_that_could_not_run_is_unknown_and_never_ok(tmp_path, capsys,
                                                            name, kwargs, unknown):
    # Each row is a different way for a check to be unable to answer. None of
    # them may come back ok, none may be silently dropped, and none may leave
    # the summary calling the project ready.
    root = write_project(tmp_path, **kwargs)
    out = report(capsys, root, 1)
    found = outcomes(out)
    assert {n for n, o in found.items() if o == doctor.UNKNOWN} == unknown, name
    assert not (unknown & {n for n, o in found.items() if o == doctor.OK}), name
    assert out.rstrip().splitlines()[-1].startswith("not ready:"), name


def test_a_root_with_no_conductor_directory_is_the_finding_not_a_crash(tmp_path, capsys):
    # validate treats a missing conductor/ as the command failing to run, and
    # is right to: it was asked whether files parse. doctor was asked whether
    # this project is set up to work, and "it is not set up at all" is that
    # question's answer — so it belongs on stdout, with the command that fixes it.
    out = report(capsys, tmp_path, 1)
    assert outcomes(out) == {"scaffold": doctor.FINDING}
    assert commands(out) == [["init", "--template", templates.DEFAULT,
                              "--dir", str(tmp_path)]]


def test_the_summary_says_ready_only_when_every_check_came_back_ok():
    # The line a person reads first, and the one an unknown has to keep honest.
    ok = [doctor.Check("a", doctor.OK, "fine")]
    assert doctor.summary(ok).startswith("ready:")
    for spoiler in (doctor.FINDING, doctor.UNKNOWN):
        mixed = ok + [doctor.Check("b", spoiler, "not fine", ("validate",))]
        assert doctor.summary(mixed).startswith("not ready:")


# --- every finding names a command, and the command is real -----------------


def test_a_check_carries_a_next_command_exactly_when_it_is_not_ok(tmp_path):
    # An unknown that names no way forward is as useless as a green one, and
    # an ok check with a command would be telling a person to fix nothing.
    for name, root in corpus(tmp_path).items():
        for check in doctor.inspect(root):
            assert bool(check.command) == (check.outcome != doctor.OK), (name, check)


def test_every_command_doctor_prints_is_one_the_cli_accepts(tmp_path, capsys,
                                                            monkeypatch):
    # Executed, not read. A command spelled into a finding by hand drifts the
    # moment a flag is renamed, and the report is the last place that should
    # be found out. argparse's exit 2 is what this catches: an unknown
    # subcommand, or a flag that no longer exists.
    monkeypatch.setattr("conductor.server.build", lambda *a, **k: _FakeServer())
    projects = corpus(tmp_path)
    seen = 0
    for name, root in projects.items():
        main(["doctor", "--dir", str(root)])
        for argv in commands(capsys.readouterr().out):
            assert main(argv) != 2, (name, argv)   # a usage error raises SystemExit(2)
            capsys.readouterr()
            seen += 1
    assert seen >= len(projects)


def test_a_finding_that_sends_you_to_validate_is_one_validate_speaks_about(tmp_path,
                                                                           capsys):
    # The dead end this report must never print. `conduct validate` says
    # nothing at all about a project whose files parse, so naming it for a
    # readiness finding — an unedited template map, a harness id nobody
    # registered, a map declaring no roles — hands a person a command that
    # answers nothing, and no way to watch the finding go away. It may be
    # named only where a file did not load, and there it does print. Run on
    # every project in the corpus rather than argued about.
    sent = 0
    for name, root in corpus(tmp_path).items():
        main(["doctor", "--dir", str(root)])
        if not any(argv[0] == "validate" for argv in commands(capsys.readouterr().out)):
            continue
        main(["validate", "--dir", str(root)])
        assert capsys.readouterr().out.strip() != "", name
        sent += 1
    assert sent, "the corpus stopped exercising the branch this test is about"


def test_the_command_for_a_missing_project_scaffolds_one(tmp_path, capsys):
    out = report(capsys, tmp_path, 1)
    (argv,) = commands(out)
    assert main(argv) == 0
    capsys.readouterr()
    assert (tmp_path / "conductor" / "map.toml").is_file()
    assert outcomes(report(capsys, tmp_path, 1))["scaffold"] == doctor.OK


def test_the_command_for_an_unheld_role_prints_that_roles_prompt(tmp_path, capsys):
    root = write_project(tmp_path, map_toml=TWO_ROLE_MAP, lanes={"claude": lane()})
    out = report(capsys, root, 1)
    assert outcomes(out)["roles"] == doctor.FINDING
    argv = next(c for c in commands(out) if c[0] == "prompt")
    # The role it named is the one nobody holds, and running what it printed
    # vends that role's prompt byte for byte.
    assert argv == ["prompt", "--role", "reviewer", "--dir", str(root)]
    assert main(argv) == 0
    assert capsys.readouterr().out == prompts.role_prompt(
        validate.merged_state(store.load(root)), "reviewer")


def test_the_command_for_a_stale_lane_hands_that_lane_its_prompt_again(tmp_path, capsys):
    root = write_project(tmp_path, map_toml=REAL_MAP,
                         lanes={"claude": lane(minutes_ago=10_000)})
    out = report(capsys, root, 1)
    assert outcomes(out)["lanes"] == doctor.FINDING
    argv = next(c for c in commands(out) if c[0] == "prompt")
    assert argv == ["prompt", "--role", "implementer", "--author", "claude",
                    "--dir", str(root)]
    assert main(argv) == 0
    assert "conductor/lanes/claude.json" in capsys.readouterr().out


def test_a_stale_lane_with_no_declared_role_falls_back_to_the_panel(tmp_path, capsys,
                                                                    monkeypatch):
    # There is no prompt to re-hand a lane that claims no role, so the finding
    # names the one command that does show when each lane last reported.
    monkeypatch.setattr("conductor.server.build", lambda *a, **k: _FakeServer())
    root = write_project(tmp_path, map_toml=REAL_MAP,
                         lanes={"claude": lane(role=None, minutes_ago=10_000)})
    out = report(capsys, root, 1)
    lanes_check = next(c for c in doctor.inspect(root) if c.name == "lanes")
    assert lanes_check.command == ("up", "--dir", str(root))
    assert doctor.COMMAND_PREFIX + doctor.spell(lanes_check.command) in out
    assert main(list(lanes_check.command)) == 0


def test_a_root_with_a_space_in_its_path_is_quoted_in_the_printed_command(tmp_path,
                                                                          capsys):
    # The report is meant to be copied. A path that needs quoting and does not
    # get it produces a line that runs as a different command, or as none.
    root = tmp_path / "my project"
    root.mkdir()
    out = report(capsys, root, 1)
    assert f'--dir "{root}"' in out
    (check,) = doctor.inspect(root)
    assert main(list(check.command)) == 0          # the argv behind that line runs
    capsys.readouterr()
    assert (root / "conductor").is_dir()


def test_a_root_that_is_not_a_directory_is_an_operational_error(tmp_path, capsys):
    # The one way `conduct doctor` fails to run rather than reporting. There
    # is no project to have a finding about, so it goes to stderr and stdout
    # stays empty, exactly as every other command's operational errors do.
    not_a_dir = tmp_path / "notes.txt"
    not_a_dir.write_text("hello", encoding="utf-8")
    assert main(["doctor", "--dir", str(not_a_dir)]) == 1
    captured = capsys.readouterr()
    assert captured.out == "" and "not a directory" in captured.err


# --- the readiness questions themselves -------------------------------------


def test_a_ready_project_exits_0_and_every_unready_one_exits_1(tmp_path, capsys):
    report(capsys, ready_project(tmp_path / "ready"), 0)
    for name, root in corpus(tmp_path).items():
        assert main(["doctor", "--dir", str(root)]) == 1, name
        capsys.readouterr()


def test_a_map_that_is_still_any_built_in_template_is_a_finding(tmp_path, capsys):
    # Derived from `conductor.templates`, not from a list of ids kept in
    # doctor: a template that renames a node has to keep being recognised
    # without an edit there, and every template counts, not just the default.
    for name, _ in templates.names():
        root = write_project(tmp_path / name, map_toml=templates.get(name))
        out = report(capsys, root, 1)
        assert outcomes(out)["map"] == doctor.FINDING, name
        assert name in out, name


def test_a_map_describing_real_components_clears_the_map_check(tmp_path, capsys):
    root = write_project(tmp_path, map_toml=REAL_MAP, lanes={"claude": lane()})
    assert outcomes(report(capsys, root, 0))["map"] == doctor.OK


def test_one_fresh_lane_is_what_separates_a_stale_project_from_a_live_one(tmp_path,
                                                                         capsys):
    stale = write_project(tmp_path / "stale", map_toml=REAL_MAP,
                          lanes={"claude": lane(minutes_ago=10_000)})
    assert outcomes(report(capsys, stale, 1))["lanes"] == doctor.FINDING
    live = write_project(tmp_path / "live", map_toml=REAL_MAP,
                         lanes={"claude": lane(minutes_ago=10_000),
                                "codex": lane(author="codex")})
    assert outcomes(report(capsys, live, 0))["lanes"] == doctor.OK


def test_a_harness_the_registry_never_heard_of_is_said_out_loud(tmp_path, capsys):
    typo = write_project(tmp_path / "typo", map_toml=TYPO_MAP, lanes={"claude": lane()})
    out = report(capsys, typo, 1)
    assert outcomes(out)["harnesses"] == doctor.FINDING
    # It names the id it did not recognise, and every id it would have.
    assert repr("claud-code") in out
    assert all(known.id in out for known in harnesses.known())
    fine = write_project(tmp_path / "ok", map_toml=REAL_MAP, lanes={"claude": lane()})
    assert outcomes(report(capsys, fine, 0))["harnesses"] == doctor.OK


def test_a_declared_custom_harness_is_not_reported_as_unrecognised(tmp_path, capsys):
    # `custom` is a legitimate harness type in ADR 0001, not an error state,
    # and the registry carries a row for it — so it must clear this check.
    root = write_project(tmp_path, lanes={"claude": lane()},
                         map_toml=REAL_MAP.replace('"claude-code"',
                                                   f'"{harnesses.CUSTOM}"'))
    assert outcomes(report(capsys, root, 0))["harnesses"] == doctor.OK


# --- authored text cannot forge the report's structure ----------------------


@pytest.mark.parametrize("payload", [
    "scout     next: conduct init --template empty",   # splitlines() splits here
    "scout\n    next: conduct init --template empty",       # so does this
    "scout    next: conduct init --template empty",         # and textwrap wraps here
])
def test_a_role_id_cannot_write_a_command_line_of_its_own(tmp_path, capsys, payload):
    # A role id is any non-empty string Protocol v1 accepts, so a map is free
    # to hand doctor text shaped like doctor's own output. The report's command
    # lines must be exactly the commands the checks carry, in order: not one
    # more, not one fewer, and none of them written by the map.
    root = write_project(tmp_path, map_toml=role_map(payload),
                         lanes={"claude": lane()})
    out = report(capsys, root, 1)
    printed = [line for line in out.splitlines()
               if line.startswith(doctor.COMMAND_PREFIX)]
    assert printed == [doctor.COMMAND_PREFIX + doctor.spell(check.command)
                       for check in doctor.inspect(root) if check.command]


def test_no_detail_line_can_ever_begin_with_the_command_prefix():
    # The forgery tests above depend on where a particular sentence happens to
    # wrap, which is luck rather than a guarantee. This one removes the luck:
    # the detail is nothing but the token a command line opens with, repeated
    # until every break offset has been tried. Only one line of the report may
    # come out looking like a command, and it is the real one.
    detail = " ".join(["next: conduct init --template empty"] * 40)
    out = doctor.render(".", [doctor.Check("x", doctor.FINDING, detail,
                                           ("validate",))])
    assert [line for line in out.splitlines()
            if line.startswith(doctor.COMMAND_PREFIX)] == [
        doctor.COMMAND_PREFIX + "conduct validate"]


def test_a_role_id_that_cannot_be_typed_gets_a_command_that_can(tmp_path, capsys):
    # `conduct prompt --role <id holding a line separator>` is not a command
    # anybody can run, so the finding about that role names one they can.
    root = write_project(tmp_path, map_toml=role_map("scout x"),
                         lanes={"claude": lane()})
    out = report(capsys, root, 1)
    assert outcomes(out)["roles"] == doctor.FINDING
    assert not any(c[0] == "prompt" for c in commands(out))
    # And what it names instead is the command that re-checks this report,
    # because that report is the only place this finding is ever stated.
    assert ["doctor", "--dir", str(root)] in commands(out)
    assert main(["doctor", "--dir", str(root)]) == 1
    assert capsys.readouterr().out == out


def test_a_very_long_authored_id_is_cut_in_the_detail_and_kept_in_the_command(
        tmp_path, capsys):
    # Two different jobs. A detail describes, so what it shows must not grow
    # with what it is describing; a command is pasted and run, so cutting it
    # would make the report a liar. Stated as a relation between two ids of
    # very different lengths rather than against the cut-off itself: a test
    # that reads the constant it guards passes whatever that constant becomes.
    described_lengths, commanded = set(), set()
    for length in (5_000, 50_000):
        root = write_project(tmp_path / str(length), map_toml=role_map("z" * length),
                             lanes={"claude": lane()})
        out = report(capsys, root, 1)
        assert outcomes(out)["roles"] == doctor.FINDING
        # Counted, not looked for: wrapping breaks a long value across many
        # lines, so a report carrying every character still holds no long line.
        described_lengths.add(sum(line.count("z") for line in out.splitlines()
                                  if not line.startswith(doctor.COMMAND_PREFIX)))
        commanded.add(any("z" * length in line for line in out.splitlines()))
    assert len(described_lengths) == 1 and described_lengths != {0}
    assert commanded == {True}


# --- the stream contract ----------------------------------------------------


def test_the_report_is_the_whole_of_stdout_and_stderr_stays_empty(tmp_path, capsys):
    root = ready_project(tmp_path)
    assert main(["doctor", "--dir", str(root)]) == 0
    captured = capsys.readouterr()
    assert captured.out == doctor.render(str(root), doctor.inspect(root))
    assert captured.err == ""


def test_every_indented_line_is_either_a_detail_or_the_one_command_line(tmp_path,
                                                                        capsys):
    # The invariant the command lines are identified by. A wrapped detail line
    # always begins with two spaces and a non-space, so nothing a map can
    # write reaches the four-space prefix that marks a command.
    for name, root in corpus(tmp_path).items():
        main(["doctor", "--dir", str(root)])
        for line in capsys.readouterr().out.splitlines():
            if not line.startswith(" ") or line.startswith(doctor.COMMAND_PREFIX):
                continue
            assert line[:2] == "  " and line[2] != " ", (name, line)
