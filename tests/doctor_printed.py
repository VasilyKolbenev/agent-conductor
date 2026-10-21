"""Reading a printed `conduct doctor` command line back into the argv it spells.

`test_doctor.py` hands `main` what `commands` reads off a report, and
`test_doctor_printed.py` holds that reading against the writer, `doctor.spell`.
Both import it from here and not from each other: `test_doctor_printed.py`
already takes its fixtures from `test_doctor.py`, so a helper kept in either of
the two would be an import cycle.
"""
import re

from conductor import doctor

#: One token of a printed command, read the way `doctor._spelled` writes it: a
#: token that needed quoting is wrapped in double quotes and holds no double
#: quote itself (the contract: nothing holding one ever reaches a printed
#: command), anything else is bare up to the next space. Owned here rather than
#: imported, for the reason `BARE_ENOUGH` in `test_doctor.py` is. Not
#: `shlex.split`: in its POSIX mode that reads the backslash as an escape and
#: eats it out of a Windows root.
_PRINTED_TOKEN = re.compile(r'"([^"]*)"|([^ "]+)')


def printed_argv(line):
    """The argv a printed command line spells, `conduct` itself left off.

    A quoted token is one argument with the quotes taken off, spaces and
    backslashes kept; a bare token ends at the next space.

    The reading is then held to the writer's contract: spelling the argv it
    found with `doctor.spell` must give `line` back, character for character.
    A line that is not what `spell` writes for what it parses to (a bare token
    `spell` would have quoted, a quoted one it would have left bare, a doubled
    space, a first token other than `conduct`) is not read at all.

    Raises:
        AssertionError: `line` is not the one `doctor.spell` writes for the
            argv read off it, naming both.
    """
    tokens = [m.group(1) if m.group(1) is not None else m.group(2)
              for m in _PRINTED_TOKEN.finditer(line)]
    argv = tokens[1:]
    spelled = doctor.spell(tuple(argv))
    if spelled != line:
        raise AssertionError(
            f"printed line {line!r} is not what doctor.spell writes for the argv "
            f"read off it, {argv!r}: spell gives {spelled!r}")
    return argv
