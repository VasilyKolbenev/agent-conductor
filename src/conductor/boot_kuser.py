"""The Windows boot counter: `KUSER_SHARED_DATA.BootId`, read without any privilege.

Microsoft documents `BootId` as the "boot sequence, incremented for each boot attempt by the OS
loader". The page is mapped read-only at 0x7FFE0000 in every process. Its member offsets are the
sum of the documented member sizes (ntddk.h, `KUSER_SHARED_DATA`): `BootId` follows
`AlternativeArchitecture` at 0x2C4, and the version members before it sit at 0x260, 0x26C, 0x270.

The bytes are read with `ReadProcessMemory` on the current process: an unmapped or short read
comes back as an error and a byte count, never as a crashed interpreter. The value is used only
after the page proves to be the documented layout (same version as the system, enum and mask in
range); otherwise the answer is a typed refusal, not a guess.

The counter alone is not a boot: it is joined to the boot environment GUID (the scope in which
counters are comparable) by `boot_witness.counter_text`.
"""
from __future__ import annotations

import os
import struct

from . import boot_witness
from .boot_witness import BootRefused

_WINDOWS = os.name == "nt"

KUSER_ADDRESS = 0x7FFE0000
BUILD_OFFSET = 0x260
ARCHITECTURE_OFFSET = 0x26A
MAJOR_OFFSET = 0x26C
MINOR_OFFSET = 0x270
ALTERNATIVE_OFFSET = 0x2C0
BOOT_ID_OFFSET = 0x2C4
SUITE_OFFSET = 0x2D0
#: The bytes read: through `SuiteMask`, the last member the layout check looks at.
SNAPSHOT_SIZE = 0x2E0

_ARCHITECTURES = frozenset({0, 5, 9, 12})
_ALTERNATIVE_LIMIT = 3
_SUITE_LIMIT = 0x10000
_SATURATED = 0xFFFFFFFF


def _u32(raw: bytes, offset: int) -> int:
    return struct.unpack_from("<I", raw, offset)[0]


def parse_snapshot(raw: bytes, version: tuple[int, int, int]) -> int:
    """Check that `raw` is the documented page and return its `BootId`.

    Args:
        raw: The first `SNAPSHOT_SIZE` bytes of the shared page.
        version: The system's (major, minor, build) as the system itself reports it.

    Raises:
        BootRefused: `partial_read` for a short buffer, `layout_unknown` when the page does not
            share the system's version or a member is outside its documented range,
            `value_empty` for 0 and `counter_overflow` for the saturated value.
    """
    if len(raw) < SNAPSHOT_SIZE:
        raise BootRefused("partial_read", f"only {len(raw)} of {SNAPSHOT_SIZE} bytes were read")
    seen = (_u32(raw, MAJOR_OFFSET), _u32(raw, MINOR_OFFSET), _u32(raw, BUILD_OFFSET))
    if seen != tuple(version):
        raise BootRefused("layout_unknown", (
            f"the shared page carries version {seen} but the system reports {tuple(version)}; "
            "the layout is not the documented one (or the process runs under a version shim)"))
    _check_members(raw)
    boot = _u32(raw, BOOT_ID_OFFSET)
    if boot == 0:
        raise BootRefused("value_empty", "the shared page holds a boot counter of 0")
    if boot == _SATURATED:
        raise BootRefused("counter_overflow", "the boot counter is saturated")
    return boot


def _check_members(raw: bytes) -> None:
    architecture = struct.unpack_from("<H", raw, ARCHITECTURE_OFFSET)[0]
    if architecture not in _ARCHITECTURES:
        raise BootRefused("layout_unknown",
                          f"the processor architecture {architecture} is not a documented one")
    if _u32(raw, ALTERNATIVE_OFFSET) >= _ALTERNATIVE_LIMIT:
        raise BootRefused("layout_unknown", "the alternative architecture is outside its enum")
    if _u32(raw, SUITE_OFFSET) >= _SUITE_LIMIT:
        raise BootRefused("layout_unknown", "the suite mask is not a small bit set")


def _need_windows() -> None:
    if not _WINDOWS:
        raise BootRefused("unsupported_platform", "the boot counter reader exists only on Windows")


def read_page(address: int = KUSER_ADDRESS, size: int = SNAPSHOT_SIZE) -> bytes:
    """Read `size` bytes at `address` of the current process, all or refuse.

    Raises:
        BootRefused: `partial_read` when only part could be read, `native_unavailable` when
            nothing could, `unsupported_platform` off Windows.
    """
    _need_windows()
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    kernel.ReadProcessMemory.restype = wintypes.BOOL
    kernel.ReadProcessMemory.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.c_void_p,
                                         ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
    buffer, got = ctypes.create_string_buffer(size), ctypes.c_size_t(0)
    done = kernel.ReadProcessMemory(kernel.GetCurrentProcess(), address, buffer, size,
                                    ctypes.byref(got))
    if done and got.value == size:
        return buffer.raw
    if 0 < got.value < size:
        raise BootRefused("partial_read", f"only {got.value} of {size} bytes were read")
    raise BootRefused("native_unavailable",
                      f"the read failed with Windows error {ctypes.get_last_error()}")


def os_version() -> tuple[int, int, int]:
    """The system's (major, minor, build) from `RtlGetVersion`.

    Raises:
        BootRefused: `native_unavailable` if the call fails, `unsupported_platform` off Windows.
    """
    _need_windows()
    import ctypes
    from ctypes import wintypes

    class Info(ctypes.Structure):
        _fields_ = [("size", wintypes.DWORD), ("major", wintypes.DWORD),
                    ("minor", wintypes.DWORD), ("build", wintypes.DWORD),
                    ("platform", wintypes.DWORD), ("csd", wintypes.WCHAR * 128)]

    call = ctypes.WinDLL("ntdll").RtlGetVersion
    call.argtypes, call.restype = [ctypes.c_void_p], wintypes.LONG
    info = Info(ctypes.sizeof(Info))
    if call(ctypes.byref(info)) != 0:
        raise BootRefused("native_unavailable", "the system version could not be read")
    return info.major, info.minor, info.build


def environment_guid() -> str:
    """The boot environment GUID: the scope inside which boot counters are comparable.

    Raises:
        BootRefused: `native_unavailable` if the system does not answer or answers empty.
    """
    _need_windows()
    from .ownership_native import boot_identity
    try:
        return boot_identity().split(":", 1)[1]
    except OSError as error:
        detail = f"the boot environment is unavailable: {error}"
        raise BootRefused("native_unavailable", detail) from error


def current_witness() -> str:
    """The counter witness of the current boot, or a typed refusal.

    Raises:
        BootRefused: any reader code; nothing is guessed or approximated.
    """
    _need_windows()
    counter = parse_snapshot(read_page(), os_version())
    return boot_witness.counter_text(environment_guid(), counter)
