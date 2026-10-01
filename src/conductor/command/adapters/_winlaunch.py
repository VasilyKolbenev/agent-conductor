"""Windows native helper of ProcessRunner: profiles, held ACLs and verified launch.

Only ProcessRunner supplies profile and ACL lifecycle callbacks. Launch is
suspended with explicit handles; the runner verifies policy before its existing
Job helper resumes the child. No ordinary Popen fallback exists here.
"""
from __future__ import annotations

import ctypes
import os
import subprocess
from ctypes import wintypes as w

if os.name != "nt":
    raise ImportError("Windows process creation is unavailable on this platform")

import msvcrt
import winreg

_kernel = ctypes.WinDLL("kernel32", use_last_error=True)
_adv = ctypes.WinDLL("advapi32", use_last_error=True)
_userenv = ctypes.WinDLL("userenv", use_last_error=True)


class _SidAttributes(ctypes.Structure):
    _fields_ = [("Sid", ctypes.c_void_p), ("Attributes", w.DWORD)]


class _Capabilities(ctypes.Structure):
    _fields_ = [("AppContainerSid", ctypes.c_void_p),
               ("Capabilities", ctypes.POINTER(_SidAttributes)),
               ("CapabilityCount", w.DWORD), ("Reserved", w.DWORD)]


class _Startup(ctypes.Structure):
    _fields_ = [("cb", w.DWORD), ("lpReserved", w.LPWSTR), ("lpDesktop", w.LPWSTR),
        ("lpTitle", w.LPWSTR), ("dwX", w.DWORD), ("dwY", w.DWORD),
        ("dwXSize", w.DWORD), ("dwYSize", w.DWORD), ("dwXCountChars", w.DWORD),
        ("dwYCountChars", w.DWORD), ("dwFillAttribute", w.DWORD), ("dwFlags", w.DWORD),
        ("wShowWindow", w.WORD), ("cbReserved2", w.WORD), ("lpReserved2", ctypes.c_void_p),
        ("hStdInput", w.HANDLE), ("hStdOutput", w.HANDLE), ("hStdError", w.HANDLE)]


class _ExtendedStartup(ctypes.Structure):
    _fields_ = [("startup", _Startup), ("attributes", ctypes.c_void_p)]


class _ProcessInfo(ctypes.Structure):
    _fields_ = [("process", w.HANDLE), ("thread", w.HANDLE),
               ("pid", w.DWORD), ("tid", w.DWORD)]


def _declare(lib, name, result, *args):
    method = getattr(lib, name)
    method.restype, method.argtypes = result, list(args)


_declare(_kernel, "InitializeProcThreadAttributeList", w.BOOL, ctypes.c_void_p,
         w.DWORD, w.DWORD, ctypes.POINTER(ctypes.c_size_t))
_declare(_kernel, "UpdateProcThreadAttribute", w.BOOL, ctypes.c_void_p, w.DWORD,
         ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p)
_declare(_kernel, "DeleteProcThreadAttributeList", None, ctypes.c_void_p)
_declare(_kernel, "CreateProcessW", w.BOOL, w.LPCWSTR, w.LPWSTR, ctypes.c_void_p,
         ctypes.c_void_p, w.BOOL, w.DWORD, ctypes.c_void_p, w.LPCWSTR,
         ctypes.POINTER(_ExtendedStartup), ctypes.POINTER(_ProcessInfo))
_declare(_kernel, "CloseHandle", w.BOOL, w.HANDLE)
_declare(_kernel, "WaitForSingleObject", w.DWORD, w.HANDLE, w.DWORD)
_declare(_kernel, "GetExitCodeProcess", w.BOOL, w.HANDLE, ctypes.POINTER(w.DWORD))
_declare(_kernel, "TerminateProcess", w.BOOL, w.HANDLE, w.UINT)
_declare(_kernel, "LocalFree", ctypes.c_void_p, ctypes.c_void_p)
_declare(_adv, "ConvertStringSidToSidW", w.BOOL, w.LPCWSTR, ctypes.POINTER(ctypes.c_void_p))
_declare(_adv, "ConvertSidToStringSidW", w.BOOL, ctypes.c_void_p, ctypes.POINTER(w.LPWSTR))
_declare(_adv, "OpenProcessToken", w.BOOL, w.HANDLE, w.DWORD, ctypes.POINTER(w.HANDLE))
_declare(_adv, "GetTokenInformation", w.BOOL, w.HANDLE, ctypes.c_int,
         ctypes.c_void_p, w.DWORD, ctypes.POINTER(w.DWORD))
_declare(_adv, "FreeSid", ctypes.c_void_p, ctypes.c_void_p)
_declare(_userenv, "DeriveAppContainerSidFromAppContainerName", w.LONG,
         w.LPCWSTR, ctypes.POINTER(ctypes.c_void_p))
_declare(_userenv, "CreateAppContainerProfile", w.LONG, w.LPCWSTR, w.LPCWSTR,
         w.LPCWSTR, ctypes.c_void_p, w.DWORD, ctypes.POINTER(ctypes.c_void_p))
_declare(_userenv, "DeleteAppContainerProfile", w.LONG, w.LPCWSTR)


def _profile_sid(pointer):
    result = w.LPWSTR()
    if not _adv.ConvertSidToStringSidW(pointer, ctypes.byref(result)):
        raise _error("ConvertSidToStringSidW")
    try:
        return result.value
    finally:
        _kernel.LocalFree(result)


def derive_profile_sid(moniker):
    sid = ctypes.c_void_p()
    result = _userenv.DeriveAppContainerSidFromAppContainerName(moniker, ctypes.byref(sid))
    if result:
        raise OSError(result & 0xFFFFFFFF, "DeriveAppContainerSidFromAppContainerName failed")
    try:
        return _profile_sid(sid)
    finally:
        _adv.FreeSid(sid)


def create_profile(moniker, display):
    sid = ctypes.c_void_p()
    result = _userenv.CreateAppContainerProfile(moniker, display, display,
                                                None, 0, ctypes.byref(sid))
    if result:
        raise OSError(result & 0xFFFFFFFF, "CreateAppContainerProfile failed")
    try:
        return _profile_sid(sid)
    finally:
        _adv.FreeSid(sid)


def inspect_profile(sid):
    """Read only the exact SID mapping; never enumerate profile namespaces."""
    route = (r"Software\Classes\Local Settings\Software\Microsoft\Windows"
             "\\CurrentVersion\\AppContainer\\Mappings\\" + sid)
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, route)
    except FileNotFoundError:
        return None
    with key:
        try:
            moniker, moniker_type = winreg.QueryValueEx(key, "Moniker")
            display, display_type = winreg.QueryValueEx(key, "DisplayName")
        except FileNotFoundError as error:
            raise OSError("AppContainer mapping lacks ownership metadata") from error
    if (moniker_type != winreg.REG_SZ or display_type != winreg.REG_SZ
            or type(moniker) is not str or type(display) is not str):
        raise OSError("AppContainer mapping metadata is invalid")
    return moniker, display


def delete_profile(moniker):
    result = _userenv.DeleteAppContainerProfile(moniker)
    if result:
        raise OSError(result & 0xFFFFFFFF, "DeleteAppContainerProfile failed")


_DACL = 0x4
_OWNER = 0x1
_PROTECTED_DACL = 0x80000000
_UNPROTECTED_DACL = 0x20000000
_SE_FILE_OBJECT = 1
_SE_DACL_PROTECTED = 0x1000
_declare(_adv, "GetSecurityInfo", w.DWORD, w.HANDLE, w.DWORD, w.DWORD,
         ctypes.POINTER(ctypes.c_void_p), ctypes.c_void_p, ctypes.c_void_p,
         ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p))
_declare(_adv, "SetSecurityInfo", w.DWORD, w.HANDLE, w.DWORD, w.DWORD,
         ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)
_declare(_adv, "ConvertSecurityDescriptorToStringSecurityDescriptorW", w.BOOL,
         ctypes.c_void_p, w.DWORD, w.DWORD, ctypes.POINTER(w.LPWSTR), ctypes.c_void_p)
_declare(_adv, "ConvertStringSecurityDescriptorToSecurityDescriptorW", w.BOOL,
         w.LPCWSTR, w.DWORD, ctypes.POINTER(ctypes.c_void_p), ctypes.c_void_p)
_declare(_adv, "GetSecurityDescriptorDacl", w.BOOL, ctypes.c_void_p,
         ctypes.POINTER(w.BOOL), ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(w.BOOL))
_declare(_adv, "GetSecurityDescriptorControl", w.BOOL, ctypes.c_void_p,
         ctypes.POINTER(w.WORD), ctypes.POINTER(w.DWORD))


def acl_snapshot(hold):
    """Return (DACL SDDL, protected, owner SID) for one caller-proven own path."""
    hold.check()
    owner, descriptor = ctypes.c_void_p(), ctypes.c_void_p()
    status = _adv.GetSecurityInfo(hold.handle, _SE_FILE_OBJECT, _OWNER | _DACL,
                                        ctypes.byref(owner), None, None, None,
                                        ctypes.byref(descriptor))
    if status:
        raise OSError(status, "GetSecurityInfo failed")
    try:
        present, dacl, defaulted = w.BOOL(), ctypes.c_void_p(), w.BOOL()
        if not _adv.GetSecurityDescriptorDacl(descriptor, ctypes.byref(present),
                                             ctypes.byref(dacl), ctypes.byref(defaulted)):
            raise _error("GetSecurityDescriptorDacl")
        if not present.value or not dacl.value:
            raise OSError("owned directory has an absent or NULL DACL")
        result = w.LPWSTR()
        if not _adv.ConvertSecurityDescriptorToStringSecurityDescriptorW(
                descriptor, 1, _OWNER | _DACL, ctypes.byref(result), None):
            raise _error("ConvertSecurityDescriptorToStringSecurityDescriptorW")
        try:
            sddl = result.value
        finally:
            _kernel.LocalFree(result)
        control, revision = w.WORD(), w.DWORD()
        if not _adv.GetSecurityDescriptorControl(descriptor, ctypes.byref(control),
                                                 ctypes.byref(revision)):
            raise _error("GetSecurityDescriptorControl")
        result = sddl, bool(control.value & _SE_DACL_PROTECTED), _profile_sid(owner)
        hold.check()
        return result
    finally:
        _kernel.LocalFree(descriptor)


def acl_set(hold, sddl, *, protected):
    """Set only a DACL on an already-verified product-owned directory."""
    hold.check()
    descriptor = ctypes.c_void_p()
    if not _adv.ConvertStringSecurityDescriptorToSecurityDescriptorW(
            sddl, 1, ctypes.byref(descriptor), None):
        raise _error("ConvertStringSecurityDescriptorToSecurityDescriptorW")
    try:
        present, dacl, defaulted = w.BOOL(), ctypes.c_void_p(), w.BOOL()
        if not _adv.GetSecurityDescriptorDacl(descriptor, ctypes.byref(present),
                                             ctypes.byref(dacl), ctypes.byref(defaulted)):
            raise _error("GetSecurityDescriptorDacl")
        if not present.value or not dacl.value:
            raise OSError("refusing to set an absent or NULL DACL")
        information = _DACL | (_PROTECTED_DACL if protected else _UNPROTECTED_DACL)
        status = _adv.SetSecurityInfo(hold.handle, _SE_FILE_OBJECT,
                                      information, None, None, dacl, None)
        if status:
            raise OSError(status, "SetSecurityInfo failed")
        hold.check()
    finally:
        _kernel.LocalFree(descriptor)


def acl_equal(observed_sddl, expected_sddl):
    """Compare parsed DACL bytes, not SDDL formatting or owner spellings."""
    def dacl_bytes(sddl):
        descriptor = ctypes.c_void_p()
        if not _adv.ConvertStringSecurityDescriptorToSecurityDescriptorW(
                sddl, 1, ctypes.byref(descriptor), None):
            raise _error("ConvertStringSecurityDescriptorToSecurityDescriptorW")
        try:
            present, dacl, defaulted = w.BOOL(), ctypes.c_void_p(), w.BOOL()
            if not _adv.GetSecurityDescriptorDacl(descriptor, ctypes.byref(present),
                                                 ctypes.byref(dacl), ctypes.byref(defaulted)):
                raise _error("GetSecurityDescriptorDacl")
            if not present.value or not dacl.value:
                raise OSError("ACL comparison requires a non-null DACL")
            size = ctypes.c_ushort.from_address(dacl.value + 2).value
            if size < 8 or size > 65535:
                raise OSError("ACL size is invalid")
            return ctypes.string_at(dacl, size)
        finally:
            _kernel.LocalFree(descriptor)
    return dacl_bytes(observed_sddl) == dacl_bytes(expected_sddl)


def _error(name):
    return OSError(ctypes.get_last_error(), name + " failed")


class _Attributes:
    def __init__(self):
        self.sids = []
        self.keep = []
        size = ctypes.c_size_t()
        _kernel.InitializeProcThreadAttributeList(None, 2, 0, ctypes.byref(size))
        self.buffer = ctypes.create_string_buffer(size.value)
        if not _kernel.InitializeProcThreadAttributeList(self.buffer, 2, 0, ctypes.byref(size)):
            raise _error("InitializeProcThreadAttributeList")

    def sid(self, text):
        value = ctypes.c_void_p()
        if not _adv.ConvertStringSidToSidW(text, ctypes.byref(value)):
            raise _error("ConvertStringSidToSidW")
        self.sids.append(value)
        return value

    def add(self, key, value):
        self.keep.append(value)
        if not _kernel.UpdateProcThreadAttribute(self.buffer, 0, key, ctypes.byref(value),
                                                 ctypes.sizeof(value), None, None):
            raise _error("UpdateProcThreadAttribute")

    def policy(self, policy):
        caps = (_SidAttributes * 1)()
        if policy.internet_client:
            caps[0] = _SidAttributes(self.sid("S-1-15-3-1"), 4)
        self.keep.append(caps)
        self.add(0x20009, _Capabilities(self.sid(policy.sid),
                 caps if policy.internet_client else None, int(policy.internet_client), 0))

    def close(self):
        _kernel.DeleteProcThreadAttributeList(self.buffer)
        for sid in self.sids:
            _kernel.LocalFree(sid)


class Child:
    """Only the Popen surface needed by ProcessRunner; the runner owns all cleanup."""
    def __init__(self, handle, pid, stdin, stdout):
        self._handle, self.pid = handle, pid
        self.stdin, self.stdout, self.stderr = stdin, stdout, None
        self.returncode = None

    def poll(self):
        if self.returncode is None:
            waited = _kernel.WaitForSingleObject(self._handle, 0)
            if waited == 0:
                code = w.DWORD()
                if not _kernel.GetExitCodeProcess(self._handle, ctypes.byref(code)):
                    raise _error("GetExitCodeProcess")
                self.returncode = code.value
            elif waited != 0x102:
                raise _error("WaitForSingleObject")
        return self.returncode

    def wait(self, timeout=None):
        result = _kernel.WaitForSingleObject(self._handle,
            0xFFFFFFFF if timeout is None else max(0, min(0xFFFFFFFE, int(timeout * 1000))))
        if result == 0x102:
            raise subprocess.TimeoutExpired("confined child", timeout)
        if result != 0:
            raise _error("WaitForSingleObject")
        return self.poll()

    def kill(self):
        if not _kernel.TerminateProcess(self._handle, 1) and self.poll() is None:
            raise _error("TerminateProcess")

    terminate = kill

    def release_handle(self):
        if self._handle is not None:
            _kernel.CloseHandle(self._handle)
            self._handle = None


def require_policy(child, expected_sid):
    """Must run while the child is still suspended; a mismatch cannot execute code."""
    token = w.HANDLE()
    if not _adv.OpenProcessToken(int(child._handle), 8, ctypes.byref(token)):
        raise _error("OpenProcessToken")
    try:
        flag, size = w.DWORD(), w.DWORD()
        if not _adv.GetTokenInformation(token, 29, ctypes.byref(flag), 4, ctypes.byref(size)):
            raise _error("TokenIsAppContainer")
        if flag.value != 1:
            raise OSError("AppContainer policy was not applied")
        buffer = ctypes.create_string_buffer(512)
        if not _adv.GetTokenInformation(token, 31, buffer, len(buffer), ctypes.byref(size)):
            raise _error("TokenAppContainerSid")
        sid = ctypes.cast(buffer, ctypes.POINTER(ctypes.c_void_p))[0]
        text = w.LPWSTR()
        if not _adv.ConvertSidToStringSidW(sid, ctypes.byref(text)):
            raise _error("ConvertSidToStringSidW")
        try:
            if text.value != expected_sid:
                raise OSError("child has another AppContainer policy")
        finally:
            _kernel.LocalFree(text)
    finally:
        _kernel.CloseHandle(token)


def launch(spec, cwd, env, payload, loan):
    """Create the requested container child, suspended; never grant extra rights."""
    if not os.path.isabs(spec.argv[0]):
        raise OSError("confined executable must be an absolute pinned path")
    fds, streams = [], []
    attributes = None
    created = _ProcessInfo()
    try:
        nul = os.open(os.devnull, os.O_RDWR | os.O_BINARY)
        fds.append(nul)
        stdout, output = os.pipe()
        fds.extend((stdout, output))
        input_fd, stdin = nul, None
        if payload is not None:
            input_fd, stdin = os.pipe()
            fds.extend((input_fd, stdin))
        child_fds = {nul, output, input_fd}
        for fd in child_fds:
            os.set_inheritable(fd, True)
        handles = [msvcrt.get_osfhandle(fd) for fd in child_fds]
        handles.extend(() if loan is None else loan.handles)
        attributes = _Attributes()
        attributes.policy(spec.boundary)
        attributes.add(0x20002, (w.HANDLE * len(handles))(*handles))
        info = _ExtendedStartup()
        info.startup.cb = ctypes.sizeof(info)
        info.startup.dwFlags = 0x100
        info.startup.hStdInput = msvcrt.get_osfhandle(input_fd)
        info.startup.hStdOutput = msvcrt.get_osfhandle(output)
        info.startup.hStdError = msvcrt.get_osfhandle(nul if spec.separate_stderr else output)
        info.attributes = ctypes.cast(attributes.buffer, ctypes.c_void_p)
        text = "".join(f"{key}={value}\0" for key, value in sorted(env.items(), key=lambda pair: pair[0].upper())) + "\0"
        environment = ctypes.create_unicode_buffer(text)
        ok = _kernel.CreateProcessW(spec.argv[0], ctypes.create_unicode_buffer(subprocess.list2cmdline(spec.argv)),
            None, None, True, 0x80000 | 0x08000000 | 0x400 | 4,
            ctypes.cast(environment, ctypes.c_void_p), str(cwd), ctypes.byref(info), ctypes.byref(created))
        if not ok:
            raise _error("CreateProcessW")
        _kernel.CloseHandle(created.thread)
        created.thread = None
        out = os.fdopen(stdout, "rb", buffering=0)
        fds.remove(stdout)
        streams.append(out)
        inp = None
        if stdin is not None:
            inp = os.fdopen(stdin, "wb", buffering=0)
            fds.remove(stdin)
            streams.append(inp)
        child = Child(created.process, created.pid, inp, out)
        created.process = None
        streams.clear()
        return child
    finally:
        if created.process:
            _kernel.TerminateProcess(created.process, 1)
            _kernel.WaitForSingleObject(created.process, 5000)
            _kernel.CloseHandle(created.process)
        if created.thread:
            _kernel.CloseHandle(created.thread)
        if attributes is not None:
            attributes.close()
        for stream in streams:
            stream.close()
        for fd in fds:
            os.close(fd)
