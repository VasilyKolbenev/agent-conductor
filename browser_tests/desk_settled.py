"""What a test may ask of a desk document that may not be the desk yet.

A frame that was just mounted, or a page whose location was just replaced, runs the wait's
predicate in a document that has not drawn the desk: its `#deskShell` is not there. A predicate
that dereferences the element then throws, and a wait whose predicate throws ENDS -- the call
raises -- instead of going on waiting. So every predicate here reads through `?.`: an absent
element is a word that is none of the words asked for, and the wait goes on until the document
is the desk and says one of them.

This is a helper and not a test module.
"""
from __future__ import annotations

#: The shell's word, or `undefined` while the document is not the desk's yet.
SHELL_WORD = 'document.getElementById("deskShell")?.getAttribute("data-state")'
#: The desk has settled when the shell says one of these (the same word every desk test waits for).
SETTLED = f'() => ["ready", "refused", "failed"].includes({SHELL_WORD})'
#: The top bar says the desk is open for another project (spec 4.5.1); a missing bar says nothing.
FOREIGN_SAID = ('() => document.getElementById("deskStatus")?.innerText'
                '.includes("another project") === true')


def shell_is(word: str) -> str:
    """The wait for the shell to say exactly `word`."""
    return f'() => {SHELL_WORD} === "{word}"'
