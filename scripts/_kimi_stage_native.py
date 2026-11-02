"""Windows relative handles for the closed Kimi staging layout.

Every create returns the handle of the object it actually created. No operation resolves a
vendor-provided relative path. Not registered as a provider, grant, or subscription transport.
"""
import ctypes
import os
from ctypes import wintypes
from functools import lru_cache

from conductor import ownership_native


class StageRefused(Exception):
    """Closed diagnostic for the laboratory and its caller."""


_NAMES = {"stage-record.jsonl", "attempt", "credentials", "kimi-code.json", "config.toml"}
_DIRECTORIES = {"attempt", "credentials"}


@lru_cache(maxsize=1)
def _native_create():
    class UnicodeString(ctypes.Structure):
        _fields_ = [("length", wintypes.USHORT), ("maximum", wintypes.USHORT),
                    ("buffer", wintypes.LPWSTR)]

    class ObjectAttributes(ctypes.Structure):
        _fields_ = [("length", wintypes.ULONG), ("parent", wintypes.HANDLE),
                    ("name", ctypes.POINTER(UnicodeString)), ("attributes", wintypes.ULONG),
                    ("security", ctypes.c_void_p), ("quality", ctypes.c_void_p)]

    class IOStatus(ctypes.Structure):
        _fields_ = [("status", ctypes.c_void_p), ("information", ctypes.c_size_t)]

    create = ctypes.WinDLL("ntdll", use_last_error=True).NtCreateFile
    create.restype = wintypes.LONG
    create.argtypes = [ctypes.POINTER(wintypes.HANDLE), wintypes.ULONG,
                       ctypes.POINTER(ObjectAttributes), ctypes.POINTER(IOStatus), ctypes.c_void_p,
                       wintypes.ULONG, wintypes.ULONG, wintypes.ULONG, wintypes.ULONG,
                       ctypes.c_void_p, wintypes.ULONG]
    return create, UnicodeString, ObjectAttributes, IOStatus


class HeldObject:
    """Only literal known children; one open handle owns the identity through disposition."""

    def __init__(self, parent, name, *, create):
        if os.name != "nt" or name not in _NAMES:
            raise StageRefused("unsupported object or system")
        native, unicode_type, attributes_type, status_type = _native_create()
        buf = ctypes.create_unicode_buffer(name)
        length = len(name.encode("utf-16-le"))
        word = unicode_type(length, length + 2, ctypes.cast(buf, wintypes.LPWSTR))
        attrs = attributes_type(ctypes.sizeof(attributes_type), parent.handle, ctypes.pointer(word),
                                0x40, None, None)  # OBJ_CASE_INSENSITIVE
        handle, status = wintypes.HANDLE(), status_type()
        directory = name in _DIRECTORIES
        # Open the reparse point itself, synchronous I/O, directory or non-directory.
        options = 0x00200000 | 0x20 | (1 if directory else 0x40)
        # SYNCHRONIZE | DELETE | READ_ATTRIBUTES | READ_DATA | WRITE_DATA. Share READ only:
        # no other handle can rename/replace the checked object while this handle is open.
        result = native(ctypes.byref(handle), 0x110083, ctypes.byref(attrs), ctypes.byref(status),
                        None, 0x80, 1, 2 if create else 1, options, None, 0)
        if result < 0:
            if not create and result & 0xffffffff == 0xc0000034:  # STATUS_OBJECT_NAME_NOT_FOUND
                raise FileNotFoundError(name)
            raise StageRefused("native object refused")
        self.handle = handle.value
        try:
            self.identity, observed_directory = ownership_native._facts(self.handle)
            if observed_directory != directory or status.information != (2 if create else 1):
                raise StageRefused("unexpected native object")
        except BaseException:
            self.close()
            raise

    def _stream(self, mode):
        import msvcrt
        kernel = ownership_native._k32
        duplicate = wintypes.HANDLE()
        process = kernel.GetCurrentProcess()
        if not kernel.DuplicateHandle(process, self.handle, process, ctypes.byref(duplicate),
                                      0, False, 2):  # DUPLICATE_SAME_ACCESS
            raise StageRefused("native duplicate refused")
        try:
            fd = msvcrt.open_osfhandle(duplicate.value, os.O_BINARY | os.O_RDWR)
        except OSError:
            kernel.CloseHandle(duplicate)
            raise
        return os.fdopen(fd, mode)

    def read(self):
        self.check()
        with self._stream("rb") as inp:
            inp.seek(0)
            data = inp.read(32769)
        if len(data) > 32768:
            raise StageRefused("oversized object")
        return data

    def append(self, data):
        self.check()
        with self._stream("r+b") as out:
            out.seek(0, os.SEEK_END)
            if out.tell() + len(data) > 32768:
                raise StageRefused("oversized write")
            if out.write(data) != len(data):
                raise StageRefused("incomplete write")
            out.flush()
            os.fsync(out.fileno())

    def check(self):
        if ownership_native._facts(self.handle)[0] != self.identity:
            raise StageRefused("object identity changed")

    def delete(self):
        self.check()
        flag = ctypes.c_ubyte(1)
        if not ownership_native._k32.SetFileInformationByHandle(self.handle, 4,
                                                              ctypes.byref(flag), 1):
            raise StageRefused("retirement refused")
        self.close()

    def close(self):
        if self.handle is not None:
            ownership_native._k32.CloseHandle(self.handle)
            self.handle = None
