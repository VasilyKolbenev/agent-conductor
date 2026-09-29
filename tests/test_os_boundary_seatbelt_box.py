"""The Seatbelt box and its fixtures, checked on every POSIX host.

The darwin tests run only on macOS. What the box hands them (a layout of their own, an
absent name that really is absent, a profile that names it) does not depend on Seatbelt,
so it is checked here: a red run of this module is a fault in the test support, never a
finding about the mechanism.
"""
from __future__ import annotations

import os

import pytest

from tests.os_boundary_seatbelt_box import (  # noqa: F401
    absent_box, implement_box, unprotected_box)

pytestmark = pytest.mark.skipif(
    os.name == "nt", reason="needs POSIX paths: a Seatbelt profile names POSIX paths")

_ABSENT_NAMES = ("hooks", "hooks-paths")


def test_two_boxes_asked_for_by_one_test_do_not_share_a_vendor_home(
        absent_box, unprotected_box):
    assert absent_box.layout.base != unprotected_box.layout.base
    assert absent_box.layout.vendor_home != unprotected_box.layout.vendor_home


def test_the_box_that_protects_absent_names_starts_without_them_beside_a_box_that_has_them(
        absent_box, unprotected_box):
    for name in _ABSENT_NAMES:
        assert not (absent_box.layout.vendor_home / name).exists(), name
        assert (unprotected_box.layout.vendor_home / name).exists(), name


def test_the_profile_of_the_absent_box_denies_both_names_after_the_allow_that_covers_them(
        absent_box):
    lines = absent_box.profile.splitlines()
    allow = next(i for i, line in enumerate(lines) if line.startswith("(allow file-write*"))
    named = [os.path.realpath(absent_box.layout.vendor_home / name) for name in _ABSENT_NAMES]
    denies = [i for i, line in enumerate(lines)
              if line.startswith("(deny file-write* (subpath")
              and all(f'(subpath "{path}")' in line for path in named)]
    assert denies, "no rule denies both absent names"
    assert denies[0] > allow, "a later rule wins, so the deny must come after the allow"
