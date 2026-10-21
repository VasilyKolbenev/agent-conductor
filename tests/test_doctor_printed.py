"""How `test_doctor.py` reads a printed command back, held against the writer.

Every test in `test_doctor.py` that runs a command the report prints hands
`main` what `commands` read off the line, so the way that reading treats a
quoted token is part of what they assert. This file asserts it directly, and
holds `printed_argv` to the contract it answers to, `doctor.spell`: the line
read must be the line `spell` writes for the argv it was read into, or the
reading refuses it with an `AssertionError` that names both.

Split from `test_doctor.py` rather than added to it, which would have taken it
over the 800-line cap. The helper itself is in `doctor_printed.py`, which this
file and `test_doctor.py` both import, so neither imports the other's helper
back. The report fixtures come from `test_doctor.py`, as `test_doctor_claims.py`
takes its own.
"""
import pytest
from conductor import doctor, templates
from conductor.__main__ import main
from tests.doctor_printed import printed_argv
from tests.test_doctor import commands, report


def test_a_quoted_root_is_read_back_out_of_the_printed_line_as_the_path_it_is(tmp_path,
                                                                              capsys):
    # Every test of `test_doctor.py` that runs a printed command hands `main`
    # what `commands` read off the line, so how that reading treats a quoted
    # token is part of what they assert. A non-ASCII name with a space is quoted
    # by the rule on every OS, whatever directory the runner's temp root lives
    # in. Left to that root alone the quoting happened only under a Cyrillic
    # user profile, so the suite was green on an ASCII CI and red on one laptop.
    root = tmp_path / "Пользователь dir"
    root.mkdir()
    out = report(capsys, root, 1)
    (line,) = [ln for ln in out.splitlines() if ln.startswith(doctor.COMMAND_PREFIX)]
    assert f'--dir "{root}"' in line                # the line does quote the path
    (argv,) = commands(out)
    assert argv == ["init", "--template", templates.DEFAULT, "--dir", str(root)]
    assert not any('"' in token for token in argv)  # the quotes are syntax, not name
    assert main(argv) == 0                          # and the argv read back runs
    capsys.readouterr()
    assert (root / "conductor" / "map.toml").is_file()


@pytest.mark.parametrize("argv", [
    ("doctor", "--dir", "plain"),
    ("doctor", "--dir", "/srv/Пользователь dir"),
    ("doctor", "--dir", "C:\\Users\\Пользователь\\project\\a b"),
    ("prompt", "--role", "scout", "--dir", "C:\\Program Files (x86)\\p&q"),
    ("doctor", "--dir", ""),
])
def test_a_printed_line_reads_back_as_the_argv_it_was_spelled_from(argv):
    # The reading `commands` does, held against the writer it answers to and
    # apart from any directory a runner happens to give: quotes come off a
    # quoted token, and its spaces and backslashes stay, which is what rules
    # out `shlex.split(posix=True)`, whose escape rule eats a Windows path.
    line = doctor.spell(argv)
    assert printed_argv(line) == list(argv)
    assert doctor.spell(tuple(printed_argv(line))) == line   # and back, the same line


@pytest.mark.parametrize("line", [
    'conduct doctor --dir a&b',                # bare, where `spell` would quote
    'conduct doctor --dir "plain"',            # quoted, where `spell` writes it bare
    'conduct  doctor',                         # a doubled space `spell` never writes
    'conduct doctor --dir "a"b',               # a quote that closes inside a token
    'conduct doctor --dir ""x',                # an empty quoted token with a tail
    'doctor --dir x',                          # not a command line: no `conduct`
    '',
])
def test_a_line_that_doctor_spell_would_not_write_is_refused_not_read(line):
    # Without this the reading is only as good as the lines it is handed: a
    # token it split the way `spell` would not have written reads back as some
    # argv, and every test that runs it is running that one.
    with pytest.raises(AssertionError, match="is not what doctor.spell writes"):
        printed_argv(line)
