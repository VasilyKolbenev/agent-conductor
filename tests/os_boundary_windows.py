"""AppContainer probe for the Windows OS-boundary checks (test support, not product code).

It is the smallest thing that can put a child into an AppContainer: an SID from a
per-attempt profile, ``CreateProcessW`` with ``PROC_THREAD_ATTRIBUTE_SECURITY_
CAPABILITIES`` and a handle list, a Popen-shaped view of the result that the one
``ProcessRunner`` can own, and the access-control helpers used to grant a container
rights on directories the attempt owns. There is no second runner here: the runner
tests substitute only ``ProcessRunner._launch`` with ``runner_launcher``.

Measured facts this module encodes (see the lane plan): the profile must exist, the
environment must carry LOCALAPPDATA, a deny entry for the container is not honoured
while an allow applies (protection is the ABSENCE of an entry), and a launch is
checked after creation with ``require_confinement`` because ``subprocess.Popen`` can
carry a handle list only and silently ignores any other attribute.
"""
from __future__ import annotations

import ctypes
import msvcrt
import os
import secrets
import subprocess
import threading
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

if os.name != "nt":
    raise ImportError("os_boundary_windows is the Windows AppContainer probe")

_k32 = ctypes.WinDLL("kernel32", use_last_error=True)
_adv = ctypes.WinDLL("advapi32", use_last_error=True)
_userenv = ctypes.WinDLL("userenv", use_last_error=True)
_PSID = ctypes.c_void_p
SYSTEM32 = Path(os.environ["SystemRoot"]) / "System32"
POWERSHELL = SYSTEM32 / "WindowsPowerShell" / "v1.0" / "powershell.exe"
CMD = SYSTEM32 / "cmd.exe"
ICACLS = SYSTEM32 / "icacls.exe"
CURL = SYSTEM32 / "curl.exe"
INTERNET_CLIENT = "S-1-15-3-1"
MODIFY = "(OI)(CI)M"
READ_EXECUTE = "(OI)(CI)RX"
FULL = "(OI)(CI)F"

_EXTENDED_STARTUPINFO_PRESENT = 0x00080000
_CREATE_SUSPENDED = 0x4
_CREATE_NO_WINDOW = 0x08000000
_CREATE_UNICODE_ENVIRONMENT = 0x400
_ATTR_SECURITY_CAPABILITIES = 0x00020009
_ATTR_HANDLE_LIST = 0x00020002
_SE_GROUP_ENABLED = 4
_WAIT_OBJECT_0, _WAIT_TIMEOUT, _INFINITE = 0, 0x102, 0xFFFFFFFF
_TOKEN_QUERY, _TOKEN_IS_APPCONTAINER, _TOKEN_APPCONTAINER_SID = 8, 29, 31
_ALREADY_EXISTS = 0x800700B7


class SECURITY_ATTRIBUTES(ctypes.Structure):
    _fields_ = [("nLength", wintypes.DWORD), ("lpSecurityDescriptor", ctypes.c_void_p),
                ("bInheritHandle", wintypes.BOOL)]


class SID_AND_ATTRIBUTES(ctypes.Structure):
    _fields_ = [("Sid", _PSID), ("Attributes", wintypes.DWORD)]


class SECURITY_CAPABILITIES(ctypes.Structure):
    _fields_ = [("AppContainerSid", _PSID), ("Capabilities", ctypes.POINTER(SID_AND_ATTRIBUTES)),
                ("CapabilityCount", wintypes.DWORD), ("Reserved", wintypes.DWORD)]


class STARTUPINFOW(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD), ("lpReserved", wintypes.LPWSTR), ("lpDesktop", wintypes.LPWSTR),
        ("lpTitle", wintypes.LPWSTR), ("dwX", wintypes.DWORD), ("dwY", wintypes.DWORD),
        ("dwXSize", wintypes.DWORD), ("dwYSize", wintypes.DWORD),
        ("dwXCountChars", wintypes.DWORD), ("dwYCountChars", wintypes.DWORD),
        ("dwFillAttribute", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
        ("wShowWindow", wintypes.WORD), ("cbReserved2", wintypes.WORD),
        ("lpReserved2", ctypes.c_void_p), ("hStdInput", wintypes.HANDLE),
        ("hStdOutput", wintypes.HANDLE), ("hStdError", wintypes.HANDLE)]


class STARTUPINFOEXW(ctypes.Structure):
    _fields_ = [("StartupInfo", STARTUPINFOW), ("lpAttributeList", ctypes.c_void_p)]


class PROCESS_INFORMATION(ctypes.Structure):
    _fields_ = [("hProcess", wintypes.HANDLE), ("hThread", wintypes.HANDLE),
                ("dwProcessId", wintypes.DWORD), ("dwThreadId", wintypes.DWORD)]


def _declare(function, restype, *argtypes) -> None:
    function.restype = restype
    function.argtypes = list(argtypes)


_declare(_userenv.CreateAppContainerProfile, ctypes.c_long, wintypes.LPCWSTR, wintypes.LPCWSTR,
         wintypes.LPCWSTR, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(_PSID))
_declare(_userenv.DeleteAppContainerProfile, ctypes.c_long, wintypes.LPCWSTR)
_declare(_adv.ConvertSidToStringSidW, wintypes.BOOL, _PSID, ctypes.POINTER(wintypes.LPWSTR))
_declare(_adv.ConvertStringSidToSidW, wintypes.BOOL, wintypes.LPCWSTR, ctypes.POINTER(_PSID))
_declare(_adv.FreeSid, _PSID, _PSID)
_declare(_adv.OpenProcessToken, wintypes.BOOL, wintypes.HANDLE, wintypes.DWORD,
         ctypes.POINTER(wintypes.HANDLE))
_declare(_adv.GetTokenInformation, wintypes.BOOL, wintypes.HANDLE, ctypes.c_int,
         ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD))
_declare(_adv.GetNamedSecurityInfoW, wintypes.DWORD, wintypes.LPCWSTR, wintypes.DWORD,
         wintypes.DWORD, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
         ctypes.POINTER(ctypes.c_void_p))
_declare(_adv.ConvertSecurityDescriptorToStringSecurityDescriptorW, wintypes.BOOL,
         ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(wintypes.LPWSTR),
         ctypes.c_void_p)
_declare(_k32.LocalFree, ctypes.c_void_p, ctypes.c_void_p)
_declare(_k32.InitializeProcThreadAttributeList, wintypes.BOOL, ctypes.c_void_p, wintypes.DWORD,
         wintypes.DWORD, ctypes.POINTER(ctypes.c_size_t))
_declare(_k32.UpdateProcThreadAttribute, wintypes.BOOL, ctypes.c_void_p, wintypes.DWORD,
         ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p)
_declare(_k32.DeleteProcThreadAttributeList, None, ctypes.c_void_p)
_declare(_k32.CreatePipe, wintypes.BOOL, ctypes.POINTER(wintypes.HANDLE),
         ctypes.POINTER(wintypes.HANDLE), ctypes.c_void_p, wintypes.DWORD)
_declare(_k32.SetHandleInformation, wintypes.BOOL, wintypes.HANDLE, wintypes.DWORD,
         wintypes.DWORD)
_declare(_k32.CloseHandle, wintypes.BOOL, wintypes.HANDLE)
_declare(_k32.CreateFileW, wintypes.HANDLE, wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
         ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE)
_declare(_k32.WaitForSingleObject, wintypes.DWORD, wintypes.HANDLE, wintypes.DWORD)
_declare(_k32.GetExitCodeProcess, wintypes.BOOL, wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
_declare(_k32.TerminateProcess, wintypes.BOOL, wintypes.HANDLE, wintypes.UINT)
_declare(_k32.CreateProcessW, wintypes.BOOL, wintypes.LPCWSTR, wintypes.LPWSTR, ctypes.c_void_p,
         ctypes.c_void_p, wintypes.BOOL, wintypes.DWORD, ctypes.c_void_p, wintypes.LPCWSTR,
         ctypes.POINTER(STARTUPINFOEXW), ctypes.POINTER(PROCESS_INFORMATION))


def _fail(what: str) -> OSError:
    return OSError(ctypes.get_last_error(), f"{what} failed")


def sid_text(sid) -> str:
    out = wintypes.LPWSTR()
    if not _adv.ConvertSidToStringSidW(sid, ctypes.byref(out)):
        raise _fail("ConvertSidToStringSid")
    try:
        return out.value
    finally:
        _k32.LocalFree(out)


def _sid_from_text(text: str):
    sid = _PSID()
    if not _adv.ConvertStringSidToSidW(text, ctypes.byref(sid)):
        raise _fail(f"ConvertStringSidToSid({text!r})")
    return sid


class Container:
    """A per-attempt AppContainer profile: created on entry, deleted on exit."""

    def __init__(self) -> None:
        self.name = f"conduct-h-probe-{os.getpid()}-{secrets.token_hex(4)}"
        self.sid = ""

    def __enter__(self) -> "Container":
        sid = _PSID()
        result = _userenv.CreateAppContainerProfile(
            self.name, self.name, self.name, None, 0, ctypes.byref(sid))
        if result != 0:
            raise OSError(result & 0xFFFFFFFF, "CreateAppContainerProfile failed")
        try:
            self.sid = sid_text(sid)
        finally:
            _adv.FreeSid(sid)
        return self

    def __exit__(self, *exc) -> None:
        self.delete()

    def delete(self) -> int:
        """Delete the profile; returns the HRESULT (0 is success)."""
        return _userenv.DeleteAppContainerProfile(self.name)


class PolicyNotApplied(RuntimeError):
    """A process that was meant to be confined is not (or not in the named container)."""


def _query(token, information_class: int, buffer, size: int) -> int:
    needed = wintypes.DWORD()
    _adv.GetTokenInformation(token, information_class, buffer, size, ctypes.byref(needed))
    return needed.value


def confinement_of(process_handle: int) -> str | None:
    """The AppContainer SID of a process, or None when its token is not a container token."""
    token = wintypes.HANDLE()
    if not _adv.OpenProcessToken(process_handle, _TOKEN_QUERY, ctypes.byref(token)):
        raise _fail("OpenProcessToken")
    try:
        flag = wintypes.DWORD()
        if not _adv.GetTokenInformation(token, _TOKEN_IS_APPCONTAINER, ctypes.byref(flag), 4,
                                        ctypes.byref(wintypes.DWORD())):
            raise _fail("GetTokenInformation(TokenIsAppContainer)")
        if not flag.value:
            return None
        buffer = ctypes.create_string_buffer(512)
        if not _adv.GetTokenInformation(token, _TOKEN_APPCONTAINER_SID, buffer, 512,
                                        ctypes.byref(wintypes.DWORD())):
            raise _fail("GetTokenInformation(TokenAppContainerSid)")
        return sid_text(ctypes.cast(buffer, ctypes.POINTER(ctypes.c_void_p))[0])
    finally:
        _k32.CloseHandle(token)


def require_confinement(process_handle: int, expected_sid: str) -> None:
    """Raise PolicyNotApplied unless the process is confined to exactly ``expected_sid``."""
    actual = confinement_of(process_handle)
    if actual != expected_sid:
        raise PolicyNotApplied(
            "the child is not confined to the attempt's container "
            f"(token container: {actual!r})")


def _environment_block(env: Mapping[str, str]):
    text = "".join(f"{key}={value}\0" for key, value in sorted(env.items())) + "\0"
    return ctypes.create_unicode_buffer(text, len(text))


class _Attributes:
    """A PROC_THREAD_ATTRIBUTE_LIST that keeps everything it points at alive."""

    def __init__(self, count: int) -> None:
        size = ctypes.c_size_t(0)
        _k32.InitializeProcThreadAttributeList(None, count, 0, ctypes.byref(size))
        self.buffer = ctypes.create_string_buffer(size.value)
        if not _k32.InitializeProcThreadAttributeList(self.buffer, count, 0, ctypes.byref(size)):
            raise _fail("InitializeProcThreadAttributeList")
        self._keep: list[object] = []

    def add(self, attribute: int, value, size: int) -> None:
        self._keep.append(value)
        if not _k32.UpdateProcThreadAttribute(
                self.buffer, 0, attribute, value, size, None, None):
            raise _fail("UpdateProcThreadAttribute")

    def add_container(self, sid_string: str, capabilities: Sequence[str]) -> None:
        caps = (SID_AND_ATTRIBUTES * max(1, len(capabilities)))()
        for index, text in enumerate(capabilities):
            caps[index].Sid = _sid_from_text(text)
            caps[index].Attributes = _SE_GROUP_ENABLED
        block = SECURITY_CAPABILITIES(
            _sid_from_text(sid_string), caps if capabilities else None, len(capabilities), 0)
        self._keep.append(caps)
        self.add(_ATTR_SECURITY_CAPABILITIES, ctypes.byref(block), ctypes.sizeof(block))
        self._keep.append(block)

    def close(self) -> None:
        _k32.DeleteProcThreadAttributeList(self.buffer)


class ConfinedProcess:
    """A Popen-shaped process created by ``launch``: what the runner needs and no more."""

    def __init__(self, handle: int, pid: int, out_fd: int | None) -> None:
        self._handle = handle
        self.pid = pid
        self.stdout = os.fdopen(out_fd, "rb", buffering=0) if out_fd is not None else None
        self.stdin = None
        self.stderr = None
        self.returncode: int | None = None

    @property
    def handle(self) -> int:
        return self._handle

    def poll(self) -> int | None:
        if self.returncode is None and self._handle is not None:
            if _k32.WaitForSingleObject(self._handle, 0) == _WAIT_OBJECT_0:
                code = wintypes.DWORD()
                _k32.GetExitCodeProcess(self._handle, ctypes.byref(code))
                self.returncode = code.value
        return self.returncode

    def wait(self, timeout: float | None = None) -> int | None:
        milliseconds = _INFINITE if timeout is None else int(timeout * 1000)
        if _k32.WaitForSingleObject(self._handle, milliseconds) == _WAIT_TIMEOUT:
            raise subprocess.TimeoutExpired("confined", timeout)
        return self.poll()

    def kill(self) -> None:
        if self._handle is not None:
            _k32.TerminateProcess(self._handle, 1)

    terminate = kill

    def read_output(self, timeout: float = 15.0) -> str:
        """Everything the child wrote, read on a helper thread so a stuck pipe cannot hang us."""
        if self.stdout is None:
            return ""
        chunks: list[bytes] = []
        reader = threading.Thread(target=lambda: chunks.append(self.stdout.read()), daemon=True)
        reader.start()
        reader.join(timeout)
        return b"".join(chunks).decode("oem", errors="replace")

    def discard(self) -> None:
        """Kill, reap and release: for a process a test only inspected."""
        self.kill()
        self.wait(10)
        self.close()

    def close(self) -> None:
        if self.stdout is not None:
            self.stdout.close()
        if self._handle is not None:
            _k32.CloseHandle(self._handle)
            self._handle = None


def _inheritable(flag: bool = True):
    return SECURITY_ATTRIBUTES(ctypes.sizeof(SECURITY_ATTRIBUTES), None, flag)


def _stdio(capture: bool):
    """(NUL for input, the child's output handle, our read end or None)."""
    nul = _k32.CreateFileW("NUL", 0xC0000000, 3, ctypes.byref(_inheritable()), 3, 0, None)
    if not capture:
        return nul, nul, None
    read, write = wintypes.HANDLE(), wintypes.HANDLE()
    if not _k32.CreatePipe(ctypes.byref(read), ctypes.byref(write),
                           ctypes.byref(_inheritable()), 0):
        raise _fail("CreatePipe")
    _k32.SetHandleInformation(read, 1, 0)  # our end must not be inherited
    return nul, write, read


def _startup_info(attributes: _Attributes, nul, out) -> STARTUPINFOEXW:
    info = STARTUPINFOEXW()
    info.StartupInfo.cb = ctypes.sizeof(STARTUPINFOEXW)
    info.StartupInfo.dwFlags = 0x100  # STARTF_USESTDHANDLES
    info.StartupInfo.hStdInput = nul
    info.StartupInfo.hStdOutput = out
    info.StartupInfo.hStdError = out
    info.lpAttributeList = ctypes.cast(attributes.buffer, ctypes.c_void_p)
    return info


def launch(command_line: str, *, sid: str | None, capabilities: Sequence[str] = (),
           cwd: str, env: Mapping[str, str], suspended: bool = False,
           inherit: Sequence[int] = (), capture: bool = True) -> ConfinedProcess:
    """CreateProcessW; ``sid=None`` leaves the container attribute off (the control launch).

    Everything else is identical between the confined launch and its control, so a
    difference in outcome is the container's. The child's input is the null device.
    """
    nul, out, read = _stdio(capture)
    attributes = _Attributes(1 + (1 if sid else 0))
    try:
        if sid:
            attributes.add_container(sid, capabilities)
        listed = (wintypes.HANDLE * (2 + len(inherit)))(nul, out, *inherit)
        attributes.add(_ATTR_HANDLE_LIST, listed, ctypes.sizeof(listed))
        info = _startup_info(attributes, nul, out)
        proc = _create(command_line, cwd, env, info, suspended, read)
    finally:
        attributes.close()
        _k32.CloseHandle(nul)
        if capture:
            _k32.CloseHandle(out)
    return proc


def _create(command_line, cwd, env, info, suspended, read) -> ConfinedProcess:
    flags = _EXTENDED_STARTUPINFO_PRESENT | _CREATE_NO_WINDOW | _CREATE_UNICODE_ENVIRONMENT
    flags |= _CREATE_SUSPENDED if suspended else 0
    created = PROCESS_INFORMATION()
    block = _environment_block(env)
    ok = _k32.CreateProcessW(None, ctypes.create_unicode_buffer(command_line), None, None, True,
                             flags, ctypes.cast(block, ctypes.c_void_p), cwd, ctypes.byref(info),
                             ctypes.byref(created))
    error = ctypes.get_last_error()
    if not ok:
        if read is not None:
            _k32.CloseHandle(read)
        raise OSError(error, f"CreateProcessW failed: {ctypes.FormatError(error).strip()}")
    _k32.CloseHandle(created.hThread)
    out_fd = msvcrt.open_osfhandle(read.value, os.O_RDONLY) if read is not None else None
    return ConfinedProcess(created.hProcess, created.dwProcessId, out_fd)


_declare(_k32.OpenProcess, wintypes.HANDLE, wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
_INVALID_HANDLES = (None, 0, 0xFFFFFFFFFFFFFFFF, 0xFFFFFFFF)


def open_inheritable_file(path) -> int:
    """A write handle to ``path`` (created if absent) that a child may inherit."""
    handle = _k32.CreateFileW(str(path), 0x40000000, 3, ctypes.byref(_inheritable()), 4, 0, None)
    if handle in _INVALID_HANDLES:
        raise _fail(f"CreateFileW({path})")
    return handle


def close_handle(handle: int) -> None:
    _k32.CloseHandle(handle)


def process_is_gone(pid: int) -> bool:
    """True when no process with this id is left running (the wait is signalled or it is gone)."""
    handle = _k32.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE
    if handle in _INVALID_HANDLES:
        return True
    try:
        return _k32.WaitForSingleObject(handle, 0) == _WAIT_OBJECT_0
    finally:
        _k32.CloseHandle(handle)


def popen_with_ignored_security_capabilities(sid: str) -> "subprocess.Popen[bytes]":
    """Popen given a container entry it cannot honour: it starts suspended and unconfined."""
    info = subprocess.STARTUPINFO()
    info.lpAttributeList = {"security_capabilities": sid}
    return subprocess.Popen(
        [str(CMD), "/d", "/c", "exit 0"], startupinfo=info,
        creationflags=_CREATE_NO_WINDOW | _CREATE_SUSPENDED, stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL)


def acl_text(path) -> str:
    """The DACL and mandatory label of a path as SDDL text (locale independent)."""
    information = 0x4 | 0x10  # DACL_SECURITY_INFORMATION | LABEL_SECURITY_INFORMATION
    descriptor = ctypes.c_void_p()
    status = _adv.GetNamedSecurityInfoW(str(path), 1, information, None, None, None, None,
                                        ctypes.byref(descriptor))
    if status != 0:
        raise OSError(status, f"GetNamedSecurityInfo({path}) failed")
    try:
        text = wintypes.LPWSTR()
        if not _adv.ConvertSecurityDescriptorToStringSecurityDescriptorW(
                descriptor, 1, information, ctypes.byref(text), None):
            raise _fail("ConvertSecurityDescriptorToStringSecurityDescriptor")
        try:
            return text.value
        finally:
            _k32.LocalFree(text)
    finally:
        _k32.LocalFree(descriptor)


def _icacls(*args: str) -> None:
    done = subprocess.run([str(ICACLS), *args], capture_output=True, timeout=60)
    if done.returncode != 0:
        raise OSError(done.returncode, done.stdout.decode("oem", errors="replace"))


def grant(path, sid: str, rights: str = MODIFY) -> None:
    """Add ONE entry for the container SID on a directory the attempt owns."""
    _icacls(str(path), "/grant", f"*{sid}:{rights}")


def current_user_sid() -> str:
    done = subprocess.run(["whoami", "/user", "/fo", "csv", "/nh"], capture_output=True,
                          timeout=30, check=True)
    return done.stdout.decode("oem", errors="replace").strip().split(",")[1].strip('"')


def protect_entry(path) -> None:
    """Cut inheritance and leave only the owner: the container then has NO entry on it."""
    kind = "(OI)(CI)F" if Path(path).is_dir() else "F"
    _icacls(str(path), "/inheritance:r")
    _icacls(str(path), "/grant:r", f"*{current_user_sid()}:{kind}")


def deny(path, sid: str, rights: str = "F") -> None:
    _icacls(str(path), "/deny", f"*{sid}:{rights}")
