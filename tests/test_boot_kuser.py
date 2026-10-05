"""The KUSER_SHARED_DATA.BootId reader: the layout, the typed refusals, and the real read."""
from __future__ import annotations

import os
import struct
import subprocess
import sys

import pytest

from conductor import boot_kuser, boot_witness
from conductor.boot_witness import BootRefused
from tests._boot_world import GUID

WINDOWS = os.name == "nt"
VERSION = (10, 0, 26200)

# The members of KUSER_SHARED_DATA up to BootId in the order Microsoft documents them
# (ntddk.h, "KUSER_SHARED_DATA"), each as (name, size, alignment). KSYSTEM_TIME is 12 bytes.
DOCUMENTED = (
    ("TickCountLowDeprecated", 4, 4), ("TickCountMultiplier", 4, 4), ("InterruptTime", 12, 4),
    ("SystemTime", 12, 4), ("TimeZoneBias", 12, 4), ("ImageNumberLow", 2, 2),
    ("ImageNumberHigh", 2, 2), ("NtSystemRoot", 520, 2), ("MaxStackTraceDepth", 4, 4),
    ("CryptoExponent", 4, 4), ("TimeZoneId", 4, 4), ("LargePageMinimum", 4, 4),
    ("AitSamplingValue", 4, 4), ("AppCompatFlag", 4, 4), ("RNGSeedVersion", 8, 8),
    ("GlobalValidationRunlevel", 4, 4), ("TimeZoneBiasStamp", 4, 4), ("NtBuildNumber", 4, 4),
    ("NtProductType", 4, 4), ("ProductTypeIsValid", 1, 1), ("Reserved0", 1, 1),
    ("NativeProcessorArchitecture", 2, 2), ("NtMajorVersion", 4, 4), ("NtMinorVersion", 4, 4),
    ("ProcessorFeatures", 64, 1), ("Reserved1", 4, 4), ("Reserved3", 4, 4), ("TimeSlip", 4, 4),
    ("AlternativeArchitecture", 4, 4), ("BootId", 4, 4), ("SystemExpirationDate", 8, 8),
    ("SuiteMask", 4, 4))


# Every `VER_SUITE_*` flag winnt.h defines (Windows SDK 10.0.26100.0, um/winnt.h lines 1517-1533).
# The value 0x00010000 is not defined there.
SUITE_FLAGS = (
    ("VER_SUITE_SMALLBUSINESS", 0x00000001), ("VER_SUITE_ENTERPRISE", 0x00000002),
    ("VER_SUITE_BACKOFFICE", 0x00000004), ("VER_SUITE_COMMUNICATIONS", 0x00000008),
    ("VER_SUITE_TERMINAL", 0x00000010), ("VER_SUITE_SMALLBUSINESS_RESTRICTED", 0x00000020),
    ("VER_SUITE_EMBEDDEDNT", 0x00000040), ("VER_SUITE_DATACENTER", 0x00000080),
    ("VER_SUITE_SINGLEUSERTS", 0x00000100), ("VER_SUITE_PERSONAL", 0x00000200),
    ("VER_SUITE_BLADE", 0x00000400), ("VER_SUITE_EMBEDDED_RESTRICTED", 0x00000800),
    ("VER_SUITE_SECURITY_APPLIANCE", 0x00001000), ("VER_SUITE_STORAGE_SERVER", 0x00002000),
    ("VER_SUITE_COMPUTE_SERVER", 0x00004000), ("VER_SUITE_WH_SERVER", 0x00008000),
    ("VER_SUITE_MULTIUSERTS", 0x00020000))


def documented_offsets():
    found, cursor = {}, 0
    for name, size, align in DOCUMENTED:
        cursor = -(-cursor // align) * align
        found[name] = cursor
        cursor += size
    return found


def snapshot(*, build=VERSION[2], major=VERSION[0], minor=VERSION[1], alt=0, boot=42,
             suite=272, arch=9, size=boot_kuser.SNAPSHOT_SIZE):
    raw = bytearray(boot_kuser.SNAPSHOT_SIZE)
    struct.pack_into("<I", raw, 0x260, build)
    struct.pack_into("<I", raw, 0x26C, major)
    struct.pack_into("<I", raw, 0x270, minor)
    struct.pack_into("<H", raw, 0x26A, arch)
    struct.pack_into("<I", raw, 0x2C0, alt)
    struct.pack_into("<I", raw, 0x2C4, boot)
    struct.pack_into("<I", raw, 0x2D0, suite)
    return bytes(raw[:size])


def refusal(raw, version=VERSION):
    with pytest.raises(BootRefused) as caught:
        boot_kuser.parse_snapshot(raw, version)
    return caught.value


def test_the_offsets_the_reader_uses_are_the_sum_of_the_documented_member_sizes():
    found = documented_offsets()
    assert found["BootId"] == boot_kuser.BOOT_ID_OFFSET == 0x2C4
    assert found["NtBuildNumber"] == boot_kuser.BUILD_OFFSET
    assert found["NtMajorVersion"] == boot_kuser.MAJOR_OFFSET
    assert found["NtMinorVersion"] == boot_kuser.MINOR_OFFSET
    assert found["AlternativeArchitecture"] == boot_kuser.ALTERNATIVE_OFFSET
    assert found["NativeProcessorArchitecture"] == boot_kuser.ARCHITECTURE_OFFSET
    assert found["SuiteMask"] == boot_kuser.SUITE_OFFSET
    assert found["SuiteMask"] + 4 <= boot_kuser.SNAPSHOT_SIZE


def test_a_complete_snapshot_of_the_expected_layout_gives_the_boot_counter():
    assert boot_kuser.parse_snapshot(snapshot(boot=42), VERSION) == 42
    assert boot_kuser.parse_snapshot(snapshot(boot=4294967294), VERSION) == 4294967294


def test_a_short_snapshot_is_a_partial_read_and_gives_no_value():
    for size in (0, 16, 0x2C4, boot_kuser.SNAPSHOT_SIZE - 1):
        assert refusal(snapshot(size=size)).code == "partial_read", size


@pytest.mark.parametrize("field", ["build", "major", "minor"])
def test_a_version_the_page_does_not_share_with_the_system_is_an_unknown_layout(field):
    error = refusal(snapshot(**{field: {"build": 19045, "major": 6, "minor": 3}[field]}))
    assert error.code == "layout_unknown"
    assert "version" in error.detail


def test_an_alternative_architecture_outside_the_documented_enum_is_an_unknown_layout():
    assert refusal(snapshot(alt=3)).code == "layout_unknown"
    assert refusal(snapshot(alt=0xFFFFFFFF)).code == "layout_unknown"


def test_a_processor_architecture_outside_the_known_four_is_an_unknown_layout():
    for arch in (0, 5, 9, 12):
        boot_kuser.parse_snapshot(snapshot(arch=arch), VERSION)
    assert refusal(snapshot(arch=7)).code == "layout_unknown"


def test_a_suite_mask_with_a_bit_no_documented_suite_flag_covers_is_an_unknown_layout():
    assert refusal(snapshot(suite=0x7FFE0000)).code == "layout_unknown"
    assert refusal(snapshot(suite=0x00010000)).code == "layout_unknown"
    assert refusal(snapshot(suite=0x80000000)).code == "layout_unknown"
    assert refusal(snapshot(suite=0x00020000 | 0x00040000)).code == "layout_unknown"


@pytest.mark.parametrize("name, bit", SUITE_FLAGS)
def test_each_suite_flag_winnt_h_documents_is_accepted_alone(name, bit):
    assert boot_kuser.parse_snapshot(snapshot(suite=bit), VERSION) == 42, name


def test_all_the_suite_flags_winnt_h_documents_are_accepted_together():
    everything = 0
    for _, bit in SUITE_FLAGS:
        everything |= bit
    assert boot_kuser.parse_snapshot(snapshot(suite=everything), VERSION) == 42


def test_a_multi_session_edition_with_a_terminal_suite_mask_is_not_an_unknown_layout():
    # VER_SUITE_MULTIUSERTS together with VER_SUITE_TERMINAL and VER_SUITE_ENTERPRISE
    assert boot_kuser.parse_snapshot(snapshot(suite=0x00020000 | 0x10 | 0x2), VERSION) == 42


def test_the_version_and_architecture_refusals_hold_whatever_the_suite_mask_says():
    multi = 0x00020000
    assert refusal(snapshot(suite=multi, major=6)).code == "layout_unknown"
    assert refusal(snapshot(suite=multi, build=19045)).code == "layout_unknown"
    assert refusal(snapshot(suite=multi, arch=7)).code == "layout_unknown"
    assert refusal(snapshot(suite=multi, alt=3)).code == "layout_unknown"


def test_a_boot_counter_of_zero_is_an_empty_value_and_the_saturated_one_an_overflow():
    assert refusal(snapshot(boot=0)).code == "value_empty"
    assert refusal(snapshot(boot=0xFFFFFFFF)).code == "counter_overflow"


@pytest.mark.skipif(WINDOWS, reason="the reader exists only on Windows")
def test_off_windows_the_reader_refuses_as_an_unsupported_platform():
    with pytest.raises(BootRefused) as caught:
        boot_kuser.current_witness()
    assert caught.value.code == "unsupported_platform"


def test_the_witness_joins_the_environment_guid_and_the_counter_read_from_the_page(monkeypatch):
    monkeypatch.setattr(boot_kuser, "read_page", lambda: snapshot(boot=77))
    monkeypatch.setattr(boot_kuser, "os_version", lambda: VERSION)
    monkeypatch.setattr(boot_kuser, "environment_guid", lambda: GUID)
    monkeypatch.setattr(boot_kuser, "_WINDOWS", True)
    assert boot_kuser.current_witness() == f"windows-bootid.v1:{GUID}:77"


def test_a_page_that_cannot_be_read_gives_no_witness_even_when_the_guid_is_known(monkeypatch):
    def broken():
        raise BootRefused("partial_read", "only 16 of 736 bytes were read")
    monkeypatch.setattr(boot_kuser, "read_page", broken)
    monkeypatch.setattr(boot_kuser, "os_version", lambda: VERSION)
    monkeypatch.setattr(boot_kuser, "environment_guid", lambda: GUID)
    monkeypatch.setattr(boot_kuser, "_WINDOWS", True)
    with pytest.raises(BootRefused) as caught:
        boot_kuser.current_witness()
    assert caught.value.code == "partial_read"


def test_a_malformed_environment_guid_gives_no_witness(monkeypatch):
    monkeypatch.setattr(boot_kuser, "read_page", lambda: snapshot())
    monkeypatch.setattr(boot_kuser, "os_version", lambda: VERSION)
    monkeypatch.setattr(boot_kuser, "environment_guid", lambda: "not-a-guid")
    monkeypatch.setattr(boot_kuser, "_WINDOWS", True)
    with pytest.raises(BootRefused) as caught:
        boot_kuser.current_witness()
    assert caught.value.code == "unknown_format"


needs_windows = pytest.mark.skipif(not WINDOWS, reason="reads the real Windows page")


@needs_windows
def test_the_real_page_gives_a_witness_that_parses_and_matches_its_own_boot():
    text = boot_kuser.current_witness()
    found = boot_witness.parse(text)
    assert found.kind == "counter" and found.counter >= 1
    with pytest.raises(BootRefused) as caught:
        boot_witness.prove_restart(text, boot_kuser.current_witness())
    assert caught.value.code == "same_boot"


@needs_windows
def test_the_real_counter_is_the_value_at_the_documented_offset_of_the_mapped_page():
    raw = boot_kuser.read_page()
    assert len(raw) == boot_kuser.SNAPSHOT_SIZE
    assert struct.unpack_from("<I", raw, documented_offsets()["BootId"])[0] == (
        boot_witness.parse(boot_kuser.current_witness()).counter)


@needs_windows
def test_independent_processes_of_one_boot_read_the_same_witness():
    code = "from conductor import boot_kuser; print(boot_kuser.current_witness())"
    first = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                           check=True, env=dict(os.environ)).stdout.strip()
    second = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                            check=True, env=dict(os.environ)).stdout.strip()
    assert first == second == boot_kuser.current_witness()


@needs_windows
def test_a_read_that_runs_off_the_end_of_the_page_is_reported_as_partial_not_a_crash():
    with pytest.raises(BootRefused) as caught:
        boot_kuser.read_page(address=boot_kuser.KUSER_ADDRESS + 0x1000 - 16, size=64)
    assert caught.value.code == "partial_read"


@needs_windows
def test_a_read_of_an_unmapped_address_is_refused_as_unavailable_not_a_crash():
    with pytest.raises(BootRefused) as caught:
        boot_kuser.read_page(address=0x10, size=16)
    assert caught.value.code == "native_unavailable"


def test_the_reader_asks_for_no_privilege_and_no_other_process():
    source = open(boot_kuser.__file__, encoding="utf-8").read()
    for name in ("OpenProcess", "AdjustTokenPrivileges", "LookupPrivilegeValue", "SeDebug",
                 "OpenProcessToken"):
        assert name not in source, name
