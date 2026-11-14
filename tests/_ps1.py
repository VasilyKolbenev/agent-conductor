"""A PowerShell script written for a child, and what the child printed, read for a person.

Test support, not product code, and importable on every platform: the Windows-only tests import it
at the top of their module. The one rule of the scripts is in `write_ps1`; the two readers of a
child's output keep the facts strict and make the failure readable.
"""
from __future__ import annotations

from pathlib import Path

#: UTF-8 with a byte order mark: the encoding of every script a test hands to ``powershell -File``.
SCRIPT_ENCODING = "utf-8-sig"


def write_ps1(path: Path, text: str) -> Path:
    """Write ``text`` as the script ``powershell.exe -File`` runs, and return ``path``.

    The file is UTF-8 WITH a byte order mark, because Windows PowerShell 5.1 reads a script that
    has none in the system ANSI code page (cp1251 on a Russian Windows, cp1252 on an English
    one), so a non-ASCII path inside it is read as other characters. The 0x82 byte of «т» is a
    quotation mark in both code pages: the string literal breaks, the parse fails and the script
    runs no line. The bytes are written as they are, with no newline translation.
    """
    path.write_bytes(text.encode(SCRIPT_ENCODING))
    return path


def child_text(output: bytes) -> str:
    """What a child printed, read in the console's own code page, for a MESSAGE and nothing else.

    A hidden console writes the OEM code page (cp866 on a Russian Windows) and Windows PowerShell
    answers a parse error in the user's language, so UTF-8 cannot read it. Bytes that do not fit
    become replacement characters: never judge a fact on this text, use `strict_text`.
    """
    try:
        return output.decode("oem", errors="replace")
    except LookupError:  # the "oem" codec exists on Windows only
        return output.decode("utf-8", errors="replace")


def strict_text(output: bytes) -> str:
    """What a child printed, as UTF-8 and nothing looser, so every fact still has to match exactly.

    Output that is not UTF-8 fails the test here, and the failure shows what the child said
    (`child_text`) instead of the position of the first byte that did not decode.
    """
    try:
        return output.decode("utf-8")
    except UnicodeDecodeError as error:
        raise AssertionError(
            f"the child's output is not UTF-8 ({error}); read in the console's code page it is:\n"
            f"{child_text(output)}") from error


def describe(outcome) -> str:
    """How a run ended and what it printed, for the message of an assert on its exit code."""
    return (f"the child ended {outcome.status} with exit code {outcome.exit_code} "
            f"(output truncated: {outcome.output_truncated}) and printed:\n"
            f"{child_text(outcome.output)}")
