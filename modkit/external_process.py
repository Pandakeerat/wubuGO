"""Launch external software without inheriting the frozen app's library search path.

PyInstaller changes SetDllDirectoryW on Windows and LD_LIBRARY_PATH on Linux.
Those settings belong to the manager's bundled runtime, never to Steam/the game.
"""
from __future__ import annotations
from contextlib import contextmanager
import ctypes
import os
from pathlib import Path
import subprocess
import sys
import threading

_LOCK = threading.RLock()


def external_environment(env=None):
    result = dict(os.environ if env is None else env)
    if not getattr(sys, 'frozen', False):
        return result
    for name in ('LD_LIBRARY_PATH', 'DYLD_LIBRARY_PATH', 'DYLD_FALLBACK_LIBRARY_PATH', 'LIBPATH'):
        original = result.pop(name + '_ORIG', None)
        if original is None:
            result.pop(name, None)
        else:
            result[name] = original
    bundle = getattr(sys, '_MEIPASS', None)
    if bundle and 'PATH' in result:
        root = os.path.normcase(os.path.abspath(bundle))
        def bundled(entry):
            value = os.path.normcase(os.path.abspath(entry.strip('"')))
            try:
                return os.path.commonpath((root, value)) == root
            except ValueError:  # Different Windows drives.
                return False
        result['PATH'] = os.pathsep.join(p for p in result['PATH'].split(os.pathsep)
                                         if not p or not bundled(p))
    for name in list(result):
        if name.startswith('_PYI_') or name in {'_MEIPASS2', 'PYINSTALLER_RESET_ENVIRONMENT'}:
            result.pop(name, None)
    return result


def _kernel32():
    from ctypes import wintypes
    api = ctypes.WinDLL('kernel32', use_last_error=True)
    api.GetDllDirectoryW.argtypes = [wintypes.DWORD, wintypes.LPWSTR]
    api.GetDllDirectoryW.restype = wintypes.DWORD
    api.SetDllDirectoryW.argtypes = [wintypes.LPCWSTR]
    api.SetDllDirectoryW.restype = wintypes.BOOL
    return api


def get_dll_directory(api=None):
    api = api or _kernel32()
    ctypes.set_last_error(0)
    size = api.GetDllDirectoryW(0, None)
    if not size:
        error = ctypes.get_last_error()
        if error:
            raise ctypes.WinError(error)
        return None
    value = ctypes.create_unicode_buffer(size)
    if api.GetDllDirectoryW(size, value) >= size:
        raise OSError('DLL search directory changed while reading it')
    return value.value or None


def set_dll_directory(directory, api=None):
    api = api or _kernel32()
    if not api.SetDllDirectoryW(directory):
        raise ctypes.WinError(ctypes.get_last_error())


@contextmanager
def clean_dll_directory():
    # SetDllDirectory is process-global; serialize our launches and restore even
    # when CreateProcess fails so the Tk/Python runtime can keep using its DLLs.
    with _LOCK:
        if sys.platform != 'win32' or not getattr(sys, 'frozen', False):
            yield
            return
        api = _kernel32()
        previous = get_dll_directory(api)
        set_dll_directory(None, api)
        try:
            yield
        finally:
            set_dll_directory(previous, api)


def popen_external(args, *, env=None, **kwargs):
    child_env = external_environment(env)
    with clean_dll_directory():
        return subprocess.Popen(args, env=child_env, **kwargs)


def run_external(args, *, env=None, **kwargs):
    child_env = external_environment(env)
    with clean_dll_directory():
        return subprocess.run(args, env=child_env, **kwargs)
