"""The closed boot witness and the one comparison that proves a restart."""
from __future__ import annotations

import pytest

from conductor import boot_witness
from conductor.boot_witness import BootRefused, counter_text, parse, prove_restart
from tests._boot_world import GUID, OTHER_GUID, assert_plain_restart_advice, counter

LINUX_A = "linux:5b1d9c0e-3b7a-4a76-9d0f-0d1f6c2e8a11"
LINUX_B = "linux:6c2e0d1f-4c8b-4b87-8e1a-1e207d3f9b22"
DARWIN_A = "darwin:5b1d9c0e-3b7a-4a76-9d0f-0d1f6c2e8a11"
LEGACY_A = "windows:13de2a5e-e1a6-11f0-aee0-91aa266ec2fd"
LEGACY_B = "windows:00000000-1111-4222-8333-444444444444"


def refusal(recorded, current):
    with pytest.raises(BootRefused) as caught:
        prove_restart(recorded, current)
    return caught.value


def test_counter_text_round_trips_through_parse_with_scope_and_counter():
    text = counter_text(GUID, 42)
    assert text == f"windows-bootid.v1:{GUID}:42"
    found = parse(text)
    assert (found.kind, found.scheme, found.scope, found.counter) == (
        "counter", "windows-bootid.v1", GUID, 42)
    assert found.text == text


def test_the_other_two_kinds_parse_as_unique_and_legacy_values():
    assert parse(LINUX_A).kind == "unique" and parse(DARWIN_A).kind == "unique"
    assert parse(LEGACY_A).kind == "legacy" and parse(LEGACY_A).counter is None


@pytest.mark.parametrize("text", [
    "", "windows-bootid.v1", f"windows-bootid.v1:{GUID}", f"windows-bootid.v1:{GUID}:",
    f"windows-bootid.v1:{GUID}:0", f"windows-bootid.v1:{GUID}:007", f"windows-bootid.v1:{GUID}:-3",
    f"windows-bootid.v1:{GUID}:4x", f"windows-bootid.v1:{GUID}:42\n",
    f" windows-bootid.v1:{GUID}:42",
    f"windows-bootid.v1:{GUID.upper()}:42", f"windows-bootid.v2:{GUID}:42",
    f"windows-bootid.v1:{GUID[:-1]}:42", "linux:not-a-uuid", "solaris:" + GUID, None, 42, b"x"])
def test_a_text_outside_the_closed_format_is_an_unknown_format(text):
    with pytest.raises(BootRefused) as caught:
        parse(text)
    assert caught.value.code == "unknown_format"


@pytest.mark.parametrize("value", [4294967295, 4294967296, 99999999999])
def test_a_counter_with_no_room_to_grow_is_an_overflow_not_a_witness(value):
    with pytest.raises(BootRefused) as caught:
        parse(f"windows-bootid.v1:{GUID}:{value}")
    assert caught.value.code == "counter_overflow"
    with pytest.raises(BootRefused) as built:
        counter_text(GUID, value)
    assert built.value.code == "counter_overflow"


def test_the_largest_counter_a_witness_may_hold_is_one_below_the_saturated_value():
    assert parse(counter(4294967294)).counter == 4294967294


def test_a_strictly_greater_counter_of_the_same_scope_proves_a_restart():
    prove_restart(counter(42), counter(43))
    prove_restart(counter(1), counter(4294967294))


def test_an_equal_counter_is_the_same_boot_and_advises_a_full_restart_and_nothing_more():
    error = refusal(counter(42), counter(42))
    assert error.code == "same_boot"
    assert_plain_restart_advice(error.detail)


def test_a_smaller_counter_is_a_decrease_and_not_a_restart():
    assert refusal(counter(43), counter(42)).code == "counter_decreased"


def test_only_the_old_windows_string_is_legacy():
    assert boot_witness.is_legacy(LEGACY_A) and boot_witness.is_legacy(LEGACY_B)
    for text in (counter(42), LINUX_A, DARWIN_A, "windows:zzz", "", None):
        assert boot_witness.is_legacy(text) is False


def test_a_recorded_counter_with_no_room_above_it_cannot_prove_anything():
    recorded = f"windows-bootid.v1:{GUID}:4294967295"
    assert refusal(recorded, counter(5)).code == "counter_overflow"


def test_another_environment_guid_is_not_comparable_even_with_a_larger_counter():
    error = refusal(counter(42), counter(9000, OTHER_GUID))
    assert error.code == "other_scope" and GUID in error.detail and OTHER_GUID in error.detail


def test_two_per_boot_ids_of_one_scheme_prove_a_restart_only_when_they_differ():
    prove_restart(LINUX_A, LINUX_B)
    assert refusal(LINUX_A, LINUX_A).code == "same_boot"


def test_another_scheme_is_refused_in_every_direction():
    for recorded, current in ((LINUX_A, DARWIN_A), (counter(42), LINUX_A), (LINUX_A, counter(42))):
        assert refusal(recorded, current).code == "other_scheme"


def test_a_legacy_value_never_authorizes_on_either_side_whatever_the_other_one_is():
    for recorded, current in ((LEGACY_A, LEGACY_B), (LEGACY_A, counter(43)),
                              (counter(42), LEGACY_B), (LEGACY_A, LEGACY_A), (LEGACY_A, LINUX_A)):
        error = refusal(recorded, current)
        assert error.code == "legacy_value", (recorded, current)
        assert "prepare" in error.detail.lower()


def test_an_unreadable_side_is_an_unknown_format_and_proves_nothing():
    assert refusal("windows:zzz", counter(43)).code == "unknown_format"
    assert refusal(counter(42), "").code == "unknown_format"


def test_a_refusal_always_carries_a_sentence_and_a_code_from_the_closed_list():
    for recorded, current in ((counter(42), counter(42)), (counter(43), counter(42)),
                              (LEGACY_A, counter(43)), (counter(1), counter(2, OTHER_GUID)),
                              (LINUX_A, DARWIN_A), ("x", "y")):
        error = refusal(recorded, current)
        assert error.code in boot_witness.CODES and len(error.detail.split()) >= 4
        assert str(error) == f"{error.code}: {error.detail}"


def test_a_refusal_with_a_code_outside_the_closed_list_cannot_be_built():
    with pytest.raises(ValueError):
        BootRefused("restart_maybe", "no")
