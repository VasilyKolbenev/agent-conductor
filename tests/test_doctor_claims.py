"""What the doctor report claims about a project, held against that project.

`test_doctor.py` asks what each check answers and whether the command it names
is one the CLI accepts. This file asks the other half — whether the SENTENCES
are true — and that is the half already shipped wrong twice: a fallback kept
the sentence written for the branch it fell back from, so the report said
"Start one with:" over `conduct validate`, and a summary counted nothing.
Both were green, because a report is prose and a test that looks for a
substring of prose agrees with whatever the prose is later rewritten to say.

Three instruments, none of them a substring of an expected sentence:

* an advice is classified by the PROMISE its closing words make to a reader,
  and the command printed under it is then RUN and held to that promise.
  "Start one with:" over `conduct validate` fails here not because the pair is
  unexpected but because running validate hands nobody a prompt.
* every number a detail prints is compared with the same number measured from
  the project, over several sizes of the thing being counted, so neither a
  constant nor a count of the wrong set survives.
* every authored value a detail quotes is compared with the set computed here
  from the map and the registry — the ids the finding is about, and not the
  ids sitting next to them that it is not about.

Split from `test_doctor.py` rather than added to it: the corpus, the fixtures
and the report helpers are imported from there, so no project shape is
described twice and neither file goes near the 800-line cap.
"""
import re
from collections import Counter
from pathlib import Path

import pytest
from conductor import doctor, harnesses, prompts, store, validate
from conductor.__main__ import main
from tests.test_doctor import (REAL_MAP, corpus, lane, outcomes, ready_project,
                               report)
from tests.test_store import write_project

#: The five things the closing words of a detail can promise a reader.
PROMPT = "hands out a role's prompt"
WHY = "says why a file did not load"
RECHECK = "prints this same report again"
PANEL = "shows when each lane last reported"
SCAFFOLD = "scaffolds a project"

#: How each promise is recognised, in the closing sentence — the one the
#: command sits directly under, and therefore the one a reader reads as
#: describing it. Suffixes and one prefix rather than whole sentences: a rule
#: carrying the whole sentence would have to be edited whenever the prose was,
#: and that edit is exactly what must not pass unnoticed.
RULES = (
    (lambda s: s.endswith("re-check with:"), RECHECK),
    (lambda s: s.lower().endswith("this command reports why:"), WHY),
    (lambda s: s.endswith("last reported:"), PANEL),
    (lambda s: s.endswith("Scaffold one:"), SCAFFOLD),
    (lambda s: s.startswith("Start ") or s.startswith("Hand the work back out"),
     PROMPT),
)


def closing(detail):
    """The last sentence of a detail — the one the printed command sits under."""
    return detail.rsplit(". ", 1)[-1].strip()


def promised(detail):
    """Which promise a detail's closing sentence makes to a reader.

    Raises:
        AssertionError: When it makes none of them, or more than one. Both
            matter, and the first one most: a sentence no rule recognises is a
            sentence nothing below executes, so a report could grow a new
            advice and this file would keep passing over a shrinking share of
            it.
    """
    sentence = closing(detail)
    made = [promise for matches, promise in RULES if matches(sentence)]
    assert len(made) == 1, f"{sentence!r} promises {made}"
    return made[0]


def a_server(served):
    """A `server.build` that records the root it was asked for and returns at once.

    Recording is the point: "shows when each lane last reported" is kept by
    serving the panel for this project, and a command that never reached the
    server kept nothing.
    """
    class Bound:
        server_address = ("127.0.0.1", 7777)

        def serve_forever(self):
            raise KeyboardInterrupt          # what Ctrl-C does

        def server_close(self):
            pass

    def build(root, port=0):
        served.append(str(root))
        return Bound()
    return build


def keeps(promise, argv, root, printed, capsys, served):
    """Run `argv` and assert it does the thing `promise` says it does."""
    if promise is PROMPT:
        flags = dict(zip(argv[1::2], argv[2::2]))
        wanted = prompts.role_prompt(validate.merged_state(store.load(root)),
                                     flags["--role"], flags.get("--author"))
        assert main(list(argv)) == 0
        assert capsys.readouterr().out == wanted
    elif promise is WHY:
        assert main(list(argv)) == 1
        assert capsys.readouterr().out.strip() != ""
    elif promise is RECHECK:
        assert main(list(argv)) == 1
        assert capsys.readouterr().out == printed
    elif promise is PANEL:
        assert main(list(argv)) == 0
        capsys.readouterr()
        assert served[-1:] == [str(root)]
    else:
        assert main(list(argv)) == 0
        capsys.readouterr()
        assert (Path(root) / "conductor").is_dir()


def advice_corpus(tmp_path):
    """`test_doctor`'s corpus, plus the shape whose advice it does not reach."""
    root = tmp_path / "corpus"
    root.mkdir()
    projects = corpus(root)
    # A stale lane claiming no role the map declares: the one shape with no
    # prompt to hand back out, and the only place the panel is ever named.
    projects["stale unclaimed"] = write_project(
        tmp_path / "unclaimed", map_toml=REAL_MAP,
        lanes={"claude": lane(role=None, minutes_ago=10_000)})
    return projects


def test_every_command_keeps_the_promise_the_sentence_above_it_makes(
        tmp_path, capsys, monkeypatch):
    # The regression this file exists for, as a relation no rewrite of the
    # prose can satisfy on its own. Each printed command is classified by what
    # the sentence over it promises, and then run: "Start one with:" over
    # `conduct validate` fails because validate hands nobody a prompt, and
    # "re-check with:" over `conduct up` fails because up prints no report.
    served = []
    monkeypatch.setattr("conductor.server.build", a_server(served))
    kept = Counter()
    for name, root in advice_corpus(tmp_path).items():
        assert main(["doctor", "--dir", str(root)]) == 1, name
        printed = capsys.readouterr().out
        for check in doctor.inspect(root):
            if not check.command:
                continue
            promise = promised(check.detail)
            keeps(promise, check.command, root, printed, capsys, served)
            kept[promise] += 1
    # And every promise was actually made by something, so a corpus that stops
    # reaching a branch fails here rather than quietly stops testing it.
    assert set(kept) == {PROMPT, WHY, RECHECK, PANEL, SCAFFOLD}, kept


def a_map(nodes=("api",), roles=(("implementer", "claude-code"),)):
    """A map about a real project: `nodes` node ids, `roles` as (id, harness).

    Nothing it writes holds a digit, so every number a detail about one of
    these projects prints is one the check counted rather than one it echoed.
    """
    text = 'schema_version = 1\nproject = "p"\n'
    for node in nodes:
        text += (f'[[nodes]]\nid = "{node}"\nlabel = "the {node} service"\n'
                 'kind = "artifact"\n')
    for role, harness in roles:
        text += f'[[cycle.roles]]\nid = "{role}"\n'
        text += f'harness = "{harness}"\n' if harness else ""
        text += "reviews = []\n"
    return text


def numbers(text):
    """Every integer a sentence states, in the order it states them."""
    return [int(found) for found in re.findall(r"\d+", text)]


def quoted(text):
    """Every authored value a detail shows: `_shown` quotes them, nothing else."""
    return set(re.findall(r"'([^']*)'", text))


THREE_ROLES = (("implementer", "claude-code"), ("reviewer", ""), ("scout", ""))

#: One project per counted answer, and the outcome and numbers each check owes
#: it. The sizes vary on purpose and differ from each other: a detail printing
#: a constant, or counting the set next to the one it is about, agrees with at
#: most one row of this table.
NUMBER_CASES = [
    ("one node, one held role", ("api",), None, {"claude": lane()},
     {"map": (doctor.OK, [1]), "lanes": (doctor.OK, [1, 1]),
      "roles": (doctor.OK, [1]), "harnesses": (doctor.OK, [1])}),
    ("three nodes", ("api", "web", "db"), None, {"claude": lane()},
     {"map": (doctor.OK, [3])}),
    ("two of three lanes fresh", ("api",), None,
     {"claude": lane(), "codex": lane(author="codex"),
      "cursor": lane(author="cursor", minutes_ago=10_000)},
     {"lanes": (doctor.OK, [2, 3]), "roles": (doctor.OK, [1])}),
    ("four lanes, all stale", ("api",), None,
     {name: lane(author=name, minutes_ago=10_000)
      for name in ("claude", "codex", "cursor", "windsurf")},
     {"lanes": (doctor.FINDING, [4])}),
    ("two lanes, both unreadable", ("api",), None,
     {"bad": "{not json", "worse": "[]"},
     {"lanes": (doctor.UNKNOWN, [2]), "roles": (doctor.UNKNOWN, [2, 1])}),
    ("one unreadable among two live", ("api",), None,
     {"claude": lane(), "codex": lane(author="codex"), "bad": "{not json"},
     {"lanes": (doctor.OK, [2, 3]), "roles": (doctor.UNKNOWN, [1, 1])}),
    ("two of three roles unheld", ("api",), THREE_ROLES, {"claude": lane()},
     {"roles": (doctor.FINDING, [2, 3]), "harnesses": (doctor.OK, [1])}),
    ("two harness ids nobody registered", ("api",),
     (("implementer", "claud-code"), ("reviewer", "codx")), {"claude": lane()},
     {"harnesses": (doctor.FINDING, [2]), "roles": (doctor.FINDING, [1, 2])}),
    ("no role names a harness", ("api",), (("implementer", ""),),
     {"claude": lane()}, {"harnesses": (doctor.OK, [])}),
]


@pytest.mark.parametrize("name, nodes, roles, lanes, expected", NUMBER_CASES)
def test_every_number_a_detail_prints_is_one_measured_from_the_project(
        tmp_path, name, nodes, roles, lanes, expected):
    # A detail describes the project the report is about, and the only part of
    # that description a test can hold to the project itself is what it counts.
    # So every count is stated here from the fixture and compared, outcome
    # included: a detail that is right about the answer and wrong about the
    # number is still a false statement about somebody's project.
    text = a_map(nodes) if roles is None else a_map(nodes, roles)
    root = write_project(tmp_path, map_toml=text, lanes=lanes)
    checks = {check.name: check for check in doctor.inspect(root)}
    for check_name, (outcome, counted) in expected.items():
        check = checks[check_name]
        assert (check.outcome, numbers(check.detail)) == (outcome, counted), \
            (name, check_name, check.detail)


def test_the_counted_table_reaches_every_check_and_every_outcome():
    # The table above is only as strong as what it covers, and a row deleted or
    # narrowed would take a check's counting out of the suite in silence.
    covered = {(check, outcome) for *_, expected in NUMBER_CASES
               for check, (outcome, _) in expected.items()}
    assert {check for check, _ in covered} == {"map", "lanes", "roles",
                                               "harnesses"}
    assert {outcome for _, outcome in covered} == {doctor.OK, doctor.FINDING,
                                                   doctor.UNKNOWN}


def test_a_finding_quotes_the_values_it_is_about_and_not_the_ones_beside_them(
        tmp_path):
    # Two findings name a set of authored ids, and each has the complementary
    # set close enough to print by mistake: the roles somebody does hold, and
    # the harness ids the registry does know. Both sets are computed here, from
    # the map and from the registry, rather than read back off the report.
    unheld = write_project(tmp_path / "unheld", lanes={"claude": lane()},
                           map_toml=a_map(roles=THREE_ROLES))
    roles = next(c for c in doctor.inspect(unheld) if c.name == "roles")
    assert roles.outcome == doctor.FINDING
    assert quoted(roles.detail) == {"reviewer", "scout"}      # not "implementer"

    typo = write_project(tmp_path / "typo", lanes={"claude": lane()},
                         map_toml=a_map(roles=(("implementer", "claud-code"),
                                               ("reviewer", "codx"))))
    named = next(c for c in doctor.inspect(typo) if c.name == "harnesses")
    assert named.outcome == doctor.FINDING
    assert quoted(named.detail) == {"claud-code", "codx"}
    assert not quoted(named.detail) & {known.id for known in harnesses.known()}


def test_the_report_names_the_project_it_was_asked_about_and_no_other(tmp_path,
                                                                      capsys):
    # A report is redirected, mailed and pasted into issues, so the one line
    # saying which project it is about is load-bearing. Stated as a relation
    # between the root the renderer was handed and the header it produced: the
    # same checks under two roots must give two headers.
    alpha = ready_project(tmp_path / "alpha")
    beta = write_project(tmp_path / "beta", map_toml=REAL_MAP)
    printed = report(capsys, alpha, 0)
    assert printed.splitlines()[0].endswith(str(alpha))
    assert str(beta) not in printed
    checks = doctor.inspect(alpha)
    first, second = (doctor.render(root, checks).splitlines()[0]
                     for root in (alpha, beta))
    assert first != second
    assert first.endswith(str(alpha)) and second.endswith(str(beta))


def counted(line):
    """`{word: number}` read back off a summary line."""
    return {word: int(found) for found, word in re.findall(r"(\d+) (\w+)", line)}


@pytest.mark.parametrize("finding, unknown, ok", [(0, 3, 2), (2, 0, 1),
                                                  (1, 1, 1), (0, 0, 4)])
def test_the_summary_counts_the_checks_it_was_given(finding, unknown, ok):
    # The line a person reads first, and the only one that speaks about the
    # report as a whole. Three counts that differ from each other in every row,
    # so a summary printing a constant — or one count where another belongs —
    # disagrees with the checks it was handed.
    checks = ([doctor.Check("f", doctor.FINDING, "x", ("doctor",))] * finding
              + [doctor.Check("u", doctor.UNKNOWN, "x", ("doctor",))] * unknown
              + [doctor.Check("o", doctor.OK, "x")] * ok)
    line = doctor.summary(checks)
    if finding or unknown:
        assert counted(line) == {"finding": finding, "unknown": unknown,
                                 "ok": ok}
    else:
        assert counted(line) == {"check": ok}


def test_the_summary_line_counts_the_outcomes_printed_above_it(tmp_path, capsys):
    # And the same relation inside a real report, between its own two halves:
    # whatever the checks came back as, the last line counts those and not
    # something else. A project every check passes is in the loop so both
    # spellings of that line are held to it.
    projects = advice_corpus(tmp_path)
    projects["ready"] = ready_project(tmp_path / "ready")
    spellings = set()
    for name, root in projects.items():
        main(["doctor", "--dir", str(root)])
        printed = capsys.readouterr().out
        found = Counter(outcomes(printed).values())
        line = printed.rstrip().splitlines()[-1]
        if found[doctor.FINDING] or found[doctor.UNKNOWN]:
            assert counted(line) == {"finding": found[doctor.FINDING],
                                     "unknown": found[doctor.UNKNOWN],
                                     "ok": found[doctor.OK]}, name
        else:
            assert counted(line) == {"check": found[doctor.OK]}, name
        spellings.add(line.split(":")[0])
    assert spellings == {"ready", "not ready"}
