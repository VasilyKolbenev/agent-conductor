"""The KUSER_SHARED_DATA.BootId reader: the layout, the typed refusals, and the real read."""
from __future__ import annotations

import contextlib
import ctypes
import os
import struct
import subprocess
import sys
import types

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
    ("AlternativeArchitecture", 4, 4), ("BootId", 4, 4))

#: A page as long as the one the OS maps for the first members of the structure, so that a mask
#: written at its real place (0x2D0) is inside the buffer whatever the reader chooses to read.
PAGE_WITH_MASK = 0x2E0
SUITE_OFFSET = 0x2D0

MEM_COMMIT, MEM_RESERVE, MEM_FREE, MEM_RELEASE = 0x1000, 0x2000, 0x10000, 0x8000
PAGE_READWRITE = 0x04
ERROR_PARTIAL_COPY = 299
#: Where the fake kernel32 is asked to read and what it hands back (the address is never touched).
FAKE_ADDRESS = 0x10000000
FAKE_BYTES = bytes(range(64))


def documented_offsets():
    found, cursor = {}, 0
    for name, size, align in DOCUMENTED:
        cursor = -(-cursor // align) * align
        found[name] = cursor
        cursor += size
    return found


def snapshot(*, build=VERSION[2], major=VERSION[0], minor=VERSION[1], alt=0, boot=42,
             suite=272, arch=9, size=boot_kuser.SNAPSHOT_SIZE):
    raw = bytearray(PAGE_WITH_MASK)
    struct.pack_into("<I", raw, 0x260, build)
    struct.pack_into("<I", raw, 0x26C, major)
    struct.pack_into("<I", raw, 0x270, minor)
    struct.pack_into("<H", raw, 0x26A, arch)
    struct.pack_into("<I", raw, 0x2C0, alt)
    struct.pack_into("<I", raw, 0x2C4, boot)
    struct.pack_into("<I", raw, SUITE_OFFSET, suite)
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
    assert found["BootId"] + 4 == boot_kuser.SNAPSHOT_SIZE


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


def test_any_suite_mask_value_is_accepted():
    masks = [0, 272, 0x00010000, 0x00040000, 0x7FFE0000, 0xFFFFFFFF]
    masks += [1 << bit for bit in range(32)]
    for mask in masks:
        page = snapshot(suite=mask, size=PAGE_WITH_MASK)
        assert boot_kuser.parse_snapshot(page, VERSION) == 42, hex(mask)


@pytest.mark.parametrize("mask", [0, 0x00010000, 0xFFFFFFFF])
def test_every_other_refusal_holds_whatever_the_suite_mask_says(mask):
    page = {"suite": mask, "size": PAGE_WITH_MASK}
    assert refusal(snapshot(**page, major=6)).code == "layout_unknown"
    assert refusal(snapshot(**page, build=19045)).code == "layout_unknown"
    assert refusal(snapshot(**page, arch=7)).code == "layout_unknown"
    assert refusal(snapshot(**page, alt=3)).code == "layout_unknown"
    assert refusal(snapshot(**page, boot=0)).code == "value_empty"
    assert refusal(snapshot(**page, boot=0xFFFFFFFF)).code == "counter_overflow"


def test_a_page_that_ends_right_after_the_boot_counter_is_complete():
    page = snapshot(size=boot_kuser.BOOT_ID_OFFSET + 4)
    assert boot_kuser.parse_snapshot(page, VERSION) == 42
    assert refusal(snapshot(size=boot_kuser.BOOT_ID_OFFSET + 3)).code == "partial_read"


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


@contextlib.contextmanager
def page_before_a_hole():
    """Yield `(end, written)`: a readable page of this process, with nothing mapped behind it.

    `end` is the first address after the page and `written` the 16 bytes stored at its tail. The
    page is a whole one-page VirtualAlloc, and Windows allocates in granules larger than a page
    (64 KiB), so the pages behind it stay unmapped while it lives: nobody can allocate there. The
    granularity and both facts about the layout are asked of the system before the page is handed
    out, so a layout that is not this one fails here, by name, and not as a wrong answer from the
    read.
    """
    from ctypes import wintypes

    class SystemInfo(ctypes.Structure):
        _fields_ = [("architecture", wintypes.WORD), ("reserved", wintypes.WORD),
                    ("page_size", wintypes.DWORD), ("lowest", ctypes.c_void_p),
                    ("highest", ctypes.c_void_p), ("mask", ctypes.c_size_t),
                    ("processors", wintypes.DWORD), ("kind", wintypes.DWORD),
                    ("granularity", wintypes.DWORD), ("level", wintypes.WORD),
                    ("revision", wintypes.WORD)]

    # MEMORY_BASIC_INFORMATION; `PartitionId` is a member of the 64-bit layout only (winnt.h).
    members = [("base", ctypes.c_void_p), ("allocation", ctypes.c_void_p),
               ("allocation_protect", wintypes.DWORD)]
    members += [("partition", wintypes.WORD)] if ctypes.sizeof(ctypes.c_void_p) == 8 else []
    members += [("region", ctypes.c_size_t), ("state", wintypes.DWORD),
                ("protect", wintypes.DWORD), ("kind", wintypes.DWORD)]

    class Memory(ctypes.Structure):
        _fields_ = members

    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.GetSystemInfo.argtypes, k32.GetSystemInfo.restype = [ctypes.POINTER(SystemInfo)], None
    k32.VirtualAlloc.argtypes = [ctypes.c_void_p, ctypes.c_size_t, wintypes.DWORD, wintypes.DWORD]
    k32.VirtualAlloc.restype = ctypes.c_void_p
    k32.VirtualFree.argtypes = [ctypes.c_void_p, ctypes.c_size_t, wintypes.DWORD]
    k32.VirtualFree.restype = wintypes.BOOL
    k32.VirtualQuery.argtypes = [ctypes.c_void_p, ctypes.POINTER(Memory), ctypes.c_size_t]
    k32.VirtualQuery.restype = ctypes.c_size_t

    def query(address):
        found = Memory()
        if not k32.VirtualQuery(address, ctypes.byref(found), ctypes.sizeof(found)):
            raise OSError(ctypes.get_last_error(), "VirtualQuery failed")
        return found

    system = SystemInfo()
    k32.GetSystemInfo(ctypes.byref(system))
    page = system.page_size
    assert system.granularity > page, (
        f"the allocation granularity {system.granularity:#x} is not larger than the page {page:#x}")
    base = k32.VirtualAlloc(None, page, MEM_RESERVE | MEM_COMMIT, PAGE_READWRITE)
    if not base:
        raise OSError(ctypes.get_last_error(), "VirtualAlloc failed")
    try:
        written = bytes(range(0xA0, 0xB0))
        ctypes.memmove(base + page - 16, written, 16)
        own, behind = query(base), query(base + page)
        assert (own.state, own.protect) == (MEM_COMMIT, PAGE_READWRITE), (
            f"the page is not committed and readable: state {own.state:#x}, "
            f"protection {own.protect:#x}")
        assert behind.state == MEM_FREE, (
            f"the page behind the boundary is not unmapped: state {behind.state:#x}")
        yield base + page, written
    finally:
        k32.VirtualFree(base, 0, MEM_RELEASE)


@needs_windows
def test_a_read_that_runs_off_the_end_of_the_page_is_reported_as_partial_not_a_crash():
    """The kernel reads the 16 bytes up to a real boundary and says so: 16 of 64.

    The boundary is built here and proven unmapped before the read. 0x7FFE1000, the page after
    the shared page, is not used: what lies behind it is not the test's to control.
    """
    with page_before_a_hole() as (end, written):
        assert boot_kuser.read_page(address=end - 16, size=16) == written
        with pytest.raises(BootRefused) as caught:
            boot_kuser.read_page(address=end - 16, size=64)
    assert caught.value.code == "partial_read"
    assert caught.value.detail == "only 16 of 64 bytes were read"


needs_fake_kernel = pytest.mark.skipif(
    not WINDOWS, reason="the fake replaces ctypes.WinDLL, which exists only on Windows")


def fake_kernel(monkeypatch, *, done, got, error=0):
    """Put a kernel32 whose ReadProcessMemory answers as told where `read_page` will load it.

    The answer is what the API gives back: a return value, the count stored through the pointer
    and the last error; the first `got` bytes of FAKE_BYTES land in the buffer. Returns the list
    of (address, size) the reader asked for.
    """
    asked = []

    def read_process_memory(process, address, buffer, size, count):
        asked.append((address, size))
        ctypes.memmove(buffer, FAKE_BYTES, got)
        count._obj.value = got
        ctypes.set_last_error(error)
        return done

    kernel = types.SimpleNamespace(GetCurrentProcess=lambda: -1,
                                   ReadProcessMemory=read_process_memory)
    monkeypatch.setattr(ctypes, "WinDLL", lambda name, **options: kernel)
    return asked


@needs_fake_kernel
@pytest.mark.parametrize("done", [False, True])
@pytest.mark.parametrize("got", [1, 16, 63])
def test_a_count_between_nothing_and_everything_is_a_partial_read_whatever_the_api_returned(
        monkeypatch, done, got):
    asked = fake_kernel(monkeypatch, done=done, got=got, error=ERROR_PARTIAL_COPY)
    with pytest.raises(BootRefused) as caught:
        boot_kuser.read_page(address=FAKE_ADDRESS, size=64)
    assert caught.value.code == "partial_read"
    assert caught.value.detail == f"only {got} of 64 bytes were read"
    assert asked == [(FAKE_ADDRESS, 64)]


@needs_fake_kernel
@pytest.mark.parametrize("done", [False, True])
def test_a_read_that_stored_no_bytes_is_unavailable_and_names_the_windows_error(monkeypatch, done):
    asked = fake_kernel(monkeypatch, done=done, got=0, error=ERROR_PARTIAL_COPY)
    with pytest.raises(BootRefused) as caught:
        boot_kuser.read_page(address=FAKE_ADDRESS, size=64)
    assert caught.value.code == "native_unavailable"
    assert caught.value.detail == f"the read failed with Windows error {ERROR_PARTIAL_COPY}"
    assert asked == [(FAKE_ADDRESS, 64)]


@needs_fake_kernel
def test_a_read_the_api_calls_failed_is_not_accepted_even_when_the_count_looks_full(monkeypatch):
    asked = fake_kernel(monkeypatch, done=False, got=64, error=5)
    with pytest.raises(BootRefused) as caught:
        boot_kuser.read_page(address=FAKE_ADDRESS, size=64)
    assert caught.value.code == "native_unavailable"
    assert caught.value.detail == "the read failed with Windows error 5"
    assert asked == [(FAKE_ADDRESS, 64)]


@needs_fake_kernel
def test_a_complete_read_returns_exactly_the_bytes_the_kernel_stored(monkeypatch):
    asked = fake_kernel(monkeypatch, done=True, got=64)
    assert boot_kuser.read_page(address=FAKE_ADDRESS, size=64) == FAKE_BYTES
    assert asked == [(FAKE_ADDRESS, 64)]


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
