"""Native project holds; POSIX exclusion does not prevent hostile namespace edits."""
from __future__ import annotations

import os
import stat
import sys
import uuid


class NativeOwnershipError(OSError):
    """A native hold or identity could not be established."""


def _plain(found):
    return not stat.S_ISLNK(found.st_mode) and not getattr(found, "st_reparse_tag", 0)


if os.name == "nt":
    import ctypes
    from ctypes import wintypes

    _k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _invalid = wintypes.HANDLE(-1).value
    _read, _write, _delete = 0x80000000, 0x40000000, 0x00010000
    _normal, _reparse, _backup = 0x80, 0x00200000, 0x02000000
    _k32.CreateFileW.restype = wintypes.HANDLE
    _k32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
        ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    _k32.CloseHandle.argtypes = [wintypes.HANDLE]
    _k32.GetFileInformationByHandleEx.argtypes = [wintypes.HANDLE, ctypes.c_int,
        ctypes.c_void_p, wintypes.DWORD]
    _k32.LockFileEx.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD,
        wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p]
    _k32.DuplicateHandle.argtypes = [wintypes.HANDLE, wintypes.HANDLE, wintypes.HANDLE,
        ctypes.POINTER(wintypes.HANDLE), wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    _k32.GetCurrentProcess.restype = wintypes.HANDLE
    _k32.SetFileInformationByHandle.argtypes = [wintypes.HANDLE, ctypes.c_int,
        ctypes.c_void_p, wintypes.DWORD]

    class _Id(ctypes.Structure):
        _fields_ = [("volume", ctypes.c_ulonglong), ("file", ctypes.c_ubyte * 16)]

    class _Tag(ctypes.Structure):
        _fields_ = [("attributes", wintypes.DWORD), ("tag", wintypes.DWORD)]

    class _Standard(ctypes.Structure):
        _fields_ = [("allocation", ctypes.c_longlong), ("end", ctypes.c_longlong),
            ("links", wintypes.DWORD), ("pending", ctypes.c_ubyte),
            ("directory", ctypes.c_ubyte)]

    class _Overlapped(ctypes.Structure):
        _fields_ = [("internal", ctypes.c_size_t), ("high", ctypes.c_size_t),
            ("offset", wintypes.DWORD), ("offset_high", wintypes.DWORD),
            ("event", wintypes.HANDLE)]

    def _error(operation):
        return NativeOwnershipError(ctypes.get_last_error(), operation)

    def _open(path, access, share):
        handle = _k32.CreateFileW(str(path), access, share, None, 3,
            _normal | _reparse | _backup, None)
        if handle in (None, _invalid):
            raise _error("cannot hold ownership object")
        return handle

    def _facts(handle):
        ident, tag, standard = _Id(), _Tag(), _Standard()
        for kind, target in ((18, ident), (9, tag), (1, standard)):
            if not _k32.GetFileInformationByHandleEx(handle, kind,
                    ctypes.byref(target), ctypes.sizeof(target)):
                raise _error("cannot identify ownership object")
        if tag.tag or standard.pending:
            raise NativeOwnershipError("ownership object is reparse or delete-pending")
        if not standard.directory and standard.links != 1:
            raise NativeOwnershipError("ownership file has multiple names")
        return (ident.volume, int.from_bytes(bytes(ident.file), "little")), bool(standard.directory)

    def identity(path):
        handle = _open(path, 0x80, 7)
        try:
            return _facts(handle)[0]
        finally:
            _k32.CloseHandle(handle)

    def stream_identity(stream):
        import msvcrt
        return _facts(msvcrt.get_osfhandle(stream.fileno()))[0]

    class NativeHold:
        def __init__(self, path, *, directory=False, exclusive=False, tree=False, movable=False):
            self.path, self.closed = path, False
            access = _read | (_delete if movable else 0)
            share = 1 if tree else (3 if directory or exclusive else 1)
            if tree:
                probe = _open(path, _read | _write, 3)
                _k32.CloseHandle(probe)
            self.handle = _open(path, access, share)
            try:
                self.identity, is_dir = _facts(self.handle)
                if is_dir != directory:
                    raise NativeOwnershipError("ownership object has the wrong kind")
                if exclusive:
                    overlap = _Overlapped()
                    if not _k32.LockFileEx(self.handle, 3, 0, 1, 0, ctypes.byref(overlap)):
                        raise _error("project ownership is held by another process")
                self.check()
            except BaseException:
                self.close()
                raise

        def check(self):
            if self.closed or _facts(self.handle)[0] != self.identity or identity(self.path) != self.identity:
                raise NativeOwnershipError("ownership namespace identity changed")

        def duplicate(self):
            handle = wintypes.HANDLE()
            current = _k32.GetCurrentProcess()
            if not _k32.DuplicateHandle(current, self.handle, current,
                    ctypes.byref(handle), 0, True, 2):
                raise _error("cannot inherit project tree hold")
            return int(handle.value)

        def read_bytes(self, limit=8192):
            import msvcrt
            descriptor = msvcrt.open_osfhandle(self.duplicate(), os.O_RDONLY | os.O_BINARY)
            with os.fdopen(descriptor, "rb") as stream:
                stream.seek(0)
                return stream.read(limit + 1)

        def rename(self, destination):
            self.check()
            encoded = str(destination).encode("utf-16-le")

            class Rename(ctypes.Structure):
                _fields_ = [("replace", ctypes.c_ubyte), ("root", wintypes.HANDLE),
                    ("length", wintypes.DWORD), ("name", ctypes.c_ubyte * (len(encoded) + 2))]

            # FileNameLength excludes the UTF-16 terminator; reserve it in the
            # actual native buffer rather than depending on structure padding.
            data = Rename(0, None, len(encoded), (ctypes.c_ubyte * (len(encoded) + 2))(*encoded))
            if not _k32.SetFileInformationByHandle(self.handle, 3, ctypes.byref(data), ctypes.sizeof(data)):
                raise _error("cannot publish ownership rename without replacement")
            self.path = destination
            self.check()

        def close(self):
            if not self.closed:
                _k32.CloseHandle(self.handle)
                self.closed = True

    def close_inherited(handle):
        _k32.CloseHandle(handle)

    def boot_identity():
        ntdll = ctypes.WinDLL("ntdll")
        query = ntdll.NtQuerySystemInformation
        query.argtypes = [ctypes.c_int, ctypes.c_void_p, wintypes.ULONG, ctypes.c_void_p]
        query.restype = wintypes.LONG
        data = ctypes.create_string_buffer(64)
        if query(90, data, len(data), None) != 0:
            raise NativeOwnershipError("OS boot identity is unavailable")
        identifier = uuid.UUID(bytes_le=data.raw[:16])
        if identifier.int == 0:
            raise NativeOwnershipError("OS boot identity is empty")
        return "windows:" + str(identifier)

else:
    import fcntl

    def identity(path):
        found = os.lstat(path)
        if not _plain(found) or not (stat.S_ISDIR(found.st_mode) or stat.S_ISREG(found.st_mode)):
            raise NativeOwnershipError("ownership object is not a plain file or directory")
        if stat.S_ISREG(found.st_mode) and found.st_nlink != 1:
            raise NativeOwnershipError("ownership file has multiple names")
        return found.st_dev, found.st_ino

    def stream_identity(stream):
        found = os.fstat(stream.fileno())
        return found.st_dev, found.st_ino

    class NativeHold:
        def __init__(self, path, *, directory=False, exclusive=False, tree=False, movable=False):
            self.path, self.closed = path, False
            flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW
            self.handle = os.open(path, flags | (os.O_DIRECTORY if directory else 0))
            try:
                found = os.fstat(self.handle)
                if stat.S_ISDIR(found.st_mode) != directory or not _plain(found):
                    raise NativeOwnershipError("ownership object has the wrong kind")
                self.identity = (found.st_dev, found.st_ino)
                if exclusive or tree:
                    fcntl.flock(self.handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                self.check()
            except BaseException:
                self.close()
                raise

        def check(self):
            if self.closed or identity(self.path) != self.identity:
                raise NativeOwnershipError("ownership namespace identity changed")

        def duplicate(self):
            return os.dup(self.handle)

        def read_bytes(self, limit=8192):
            with os.fdopen(self.duplicate(), "rb") as stream:
                stream.seek(0)
                return stream.read(limit + 1)

        def rename(self, destination):
            # A dirfd cannot keep another same-user process from replacing the
            # source name. Maintenance uses no-clobber and verifies after effect;
            # mismatches are preserved at the destination, never removed.
            import ctypes
            self.check()
            library = ctypes.CDLL(None, use_errno=True)
            source, target = os.fsencode(self.path), os.fsencode(destination)
            if sys.platform == "linux":
                rename = getattr(library, "renameat2", None)
                if rename is None:
                    raise NativeOwnershipError("no atomic no-replace rename primitive")
                rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
                result = rename(-100, source, -100, target, 1)
            elif sys.platform == "darwin":
                rename = getattr(library, "renamex_np", None)
                if rename is None:
                    raise NativeOwnershipError("no atomic no-replace rename primitive")
                rename.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
                result = rename(source, target, 4)
            else:
                raise NativeOwnershipError("ownership transition platform is unsupported")
            if result != 0:
                raise NativeOwnershipError(ctypes.get_errno(), "ownership no-replace rename refused")
            self.path = destination
            self.check()

        def close(self):
            if not self.closed:
                os.close(self.handle)
                self.closed = True

    def close_inherited(handle):
        os.close(handle)

    def boot_identity():
        if sys.platform == "linux":
            with open("/proc/sys/kernel/random/boot_id", "r", encoding="ascii") as stream:
                value = stream.read(80).strip()
            return "linux:" + str(uuid.UUID(value))
        if sys.platform == "darwin":
            import ctypes
            library = ctypes.CDLL(None, use_errno=True)
            data, length = ctypes.create_string_buffer(80), ctypes.c_size_t(80)
            if library.sysctlbyname(b"kern.bootsessionuuid", data, ctypes.byref(length), None, 0):
                raise NativeOwnershipError("OS boot identity is unavailable")
            return "darwin:" + str(uuid.UUID(data.value.decode("ascii")))
        raise NativeOwnershipError("OS boot identity is unsupported")
