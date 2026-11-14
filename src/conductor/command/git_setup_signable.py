"""The one spelling of a branch that a signature wait may name (review ruling).

When Git is set to sign, the product writes nothing to the repository's refs: it shows the owner
two commands to paste into a terminal, and both name the target branch. Git's own rule for a
branch name (`check-ref-format`) lets through what a shell reads as code, as a redirect or as
more than one word, so the signed road names only a branch made of characters that mean nothing
to PowerShell, cmd or a POSIX shell. Git still judges everything else about the name.

This module holds the rule and nothing else, so the record layer, the refusal vocabulary and the
confirmation all read the same pattern from a place that imports nothing of the product.
"""
from __future__ import annotations

import re

_SIGNABLE_REF = re.compile(r"refs/heads/[A-Za-z0-9._/-]+")


def signable_ref(ref: object) -> bool:
    """True when `ref` is a branch the two commands of a signature wait may name."""
    return type(ref) is str and _SIGNABLE_REF.fullmatch(ref) is not None
