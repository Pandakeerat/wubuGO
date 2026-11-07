"""Optional Discord Rich Presence over local IPC, using no account tokens.

Discord's displayed application name is controlled by its developer application.
Use an application named exactly ``wubuGO``; this module cannot rename it.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import socket
import struct
import threading
import time
import uuid

MAX_FRAME = 65536


def ipc_paths():
    """Return native and common sandbox Discord IPC endpoints without network IO."""
    if os.name == 'nt':
        return [rf'\\.\pipe\discord-ipc-{i}' for i in range(10)]
    roots = []
    for key in ('XDG_RUNTIME_DIR', 'TMPDIR', 'TMP', 'TEMP'):
        if os.environ.get(key):
            roots.append(Path(os.environ[key]))
    if hasattr(os, 'getuid'):
        roots.append(Path('/run/user') / str(os.getuid()))
    roots.append(Path('/tmp'))
    candidates = []
    for root in dict.fromkeys(roots):
        for sub in ('', 'app/com.discordapp.Discord', 'snap.discord', 'discord'):
            for i in range(10):
                candidates.append(str(root / sub / f'discord-ipc-{i}'))
    return candidates


class _SocketTransport:
    def __init__(self, path):
        self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.socket.settimeout(0.25)
        try:
            self.socket.connect(path)
        except OSError:
            self.socket.close()
            raise

    def read(self, count):
        return self.socket.recv(count)

    def write(self, data):
        self.socket.sendall(data)

    def close(self):
        self.socket.close()


class _PipeTransport:
    """Windows named pipe with polled reads (ReadFile never waits for a frame)."""
    def __init__(self, path):
        import ctypes
        from ctypes import wintypes
        self.ctypes = ctypes
        self.api = ctypes.WinDLL('kernel32', use_last_error=True)
        self.api.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                        wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD,
                                        wintypes.HANDLE]
        self.api.CreateFileW.restype = wintypes.HANDLE
        self.api.PeekNamedPipe.argtypes = [wintypes.HANDLE, wintypes.LPVOID, wintypes.DWORD,
                                          wintypes.LPVOID, wintypes.LPVOID, wintypes.LPVOID]
        self.api.ReadFile.argtypes = [wintypes.HANDLE, wintypes.LPVOID, wintypes.DWORD,
                                     wintypes.LPVOID, wintypes.LPVOID]
        self.api.WriteFile.argtypes = self.api.ReadFile.argtypes
        self.api.CloseHandle.argtypes = [wintypes.HANDLE]
        self.api.SetNamedPipeHandleState.argtypes = [wintypes.HANDLE, wintypes.LPVOID,
                                                     wintypes.LPVOID, wintypes.LPVOID]
        self.handle = self.api.CreateFileW(path, 0xC0000000, 0, None, 3, 0, None)
        if self.handle == wintypes.HANDLE(-1).value:
            raise OSError(ctypes.get_last_error(), 'Discord IPC unavailable')
        # PIPE_NOWAIT bounds both reads and writes; an unresponsive Discord
        # must never strand the worker in a synchronous WriteFile call.
        mode = wintypes.DWORD(1)
        if not self.api.SetNamedPipeHandleState(self.handle, ctypes.byref(mode), None, None):
            error = ctypes.get_last_error()
            self.close()
            raise OSError(error, 'Discord IPC nonblocking mode unavailable')

    def read(self, count):
        c = self.ctypes
        available = c.c_ulong()
        if not self.api.PeekNamedPipe(self.handle, None, 0, None, c.byref(available), None):
            raise OSError(c.get_last_error(), 'Discord IPC closed')
        if not available.value:
            time.sleep(0.05)
            raise TimeoutError('No IPC data yet')
        buffer = c.create_string_buffer(min(count, available.value))
        read = c.c_ulong()
        if not self.api.ReadFile(self.handle, buffer, len(buffer), c.byref(read), None):
            raise OSError(c.get_last_error(), 'Discord IPC read failed')
        return buffer.raw[:read.value]

    def write(self, data):
        c = self.ctypes
        buffer = c.create_string_buffer(data)
        written = c.c_ulong()
        if not self.api.WriteFile(self.handle, buffer, len(data), c.byref(written), None):
            raise OSError(c.get_last_error(), 'Discord IPC write failed')
        if written.value != len(data):
            raise OSError('Discord IPC partial write')

    def close(self):
        if self.handle is not None:
            self.api.CloseHandle(self.handle)
            self.handle = None


def _connect():
    transport = _PipeTransport if os.name == 'nt' else _SocketTransport
    for path in ipc_paths():
        try:
            return transport(path)
        except OSError:
            continue
    raise OSError('Discord desktop is not running or its local IPC is unavailable')


def _frame(opcode, payload):
    data = json.dumps(payload, separators=(',', ':'), ensure_ascii=True).encode('utf-8')
    if len(data) > MAX_FRAME:
        raise ValueError('Discord IPC frame too large')
    return struct.pack('<II', opcode, len(data)) + data


class Presence:
    """Opt-in background client. Never connects until :meth:`start` is called.

    ``status`` is disabled/connecting/connected/disconnected/error/closed.
    ``error`` contains a useful local failure description. Changes are eventually
    sent; Discord may enforce its own update rate limits.
    """
    def __init__(self, client_id, *, _connector=None):
        if not isinstance(client_id, str) or not re.fullmatch(r'[0-9]{16,24}', client_id):
            raise ValueError('Enter the numeric Discord application ID (16–24 digits), not a token')
        self.client_id = client_id
        self._connector = _connector or _connect
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._thread = None
        self._transport = None
        self._activity = {}
        self._revision = 0
        self._status = 'disabled'
        self._error = ''
        self._buffer = bytearray()
        self._started_at = int(time.time())

    @property
    def status(self):
        with self._lock:
            return self._status

    @property
    def error(self):
        with self._lock:
            return self._error

    def _set_status(self, status, error=''):
        with self._lock:
            self._status, self._error = status, error

    def start(self, state='In launcher'):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self.set_activity('wubuGO', state)
        self._thread = threading.Thread(target=self._run, name='wubuGO-discord', daemon=True)
        self._thread.start()

    def set_activity(self, details, state='Offline / private'):
        if not isinstance(details, str) or not isinstance(state, str):
            raise ValueError('Presence details and state must be strings')
        with self._lock:
            self._activity = {'details': details[:128], 'state': state[:128],
                              'timestamps': {'start': self._started_at}, 'instance': False}
            self._revision += 1
        self._wake.set()

    def _read_frame(self, transport):
        """Maintain partial data across timed reads; reject oversized peer frames."""
        while not self._stop.is_set():
            if len(self._buffer) >= 8:
                opcode, size = struct.unpack('<II', self._buffer[:8])
                if size > MAX_FRAME:
                    raise ValueError('Discord IPC returned an oversized frame')
                if len(self._buffer) >= size + 8:
                    payload = bytes(self._buffer[8:8 + size])
                    del self._buffer[:8 + size]
                    return opcode, json.loads(payload.decode('utf-8'))
            data = transport.read(4096)
            if not data:
                raise OSError('Discord IPC disconnected')
            self._buffer.extend(data)
        raise OSError('Presence stopped')

    def _run(self):
        while not self._stop.is_set():
            transport = None
            try:
                self._set_status('connecting')
                transport = self._connector()
                self._transport = transport
                self._buffer.clear()
                transport.write(_frame(0, {'v': 1, 'client_id': self.client_id}))
                handshake_until = time.monotonic() + 5
                ready = False
                sent_revision = -1
                last_send = 0.0
                while not self._stop.is_set():
                    now = time.monotonic()
                    if not ready and now > handshake_until:
                        raise OSError('Discord IPC handshake timed out')
                    with self._lock:
                        activity = dict(self._activity)
                        revision = self._revision
                    if ready and revision != sent_revision and now - last_send >= 5:
                        transport.write(_frame(1, {'cmd': 'SET_ACTIVITY',
                            'args': {'pid': os.getpid(), 'activity': activity}, 'nonce': uuid.uuid4().hex}))
                        sent_revision, last_send = revision, now
                    try:
                        opcode, payload = self._read_frame(transport)
                    except (TimeoutError, socket.timeout):
                        continue
                    if not isinstance(payload, dict):
                        raise ValueError('Discord IPC returned invalid payload')
                    if opcode == 3:  # Discord ping
                        transport.write(_frame(4, payload))
                    elif opcode == 2:
                        raise OSError('Discord closed IPC: ' + str(payload.get('message', 'unknown reason'))[:200])
                    elif opcode == 1 and payload.get('evt') == 'READY':
                        ready = True
                        self._set_status('connected')
                    elif opcode == 1 and payload.get('evt') == 'ERROR':
                        data = payload.get('data', {})
                        message = data.get('message', 'Discord rejected activity') if isinstance(data, dict) else str(data)
                        raise ValueError(str(message)[:200])
            except (OSError, ValueError, UnicodeError) as exc:
                if not self._stop.is_set():
                    self._set_status('disconnected', str(exc))
            finally:
                if transport is not None:
                    try:
                        transport.close()
                    except OSError:
                        pass
                self._transport = None
            self._stop.wait(5)
        self._set_status('closed')

    def close(self):
        self._stop.set()
        self._wake.set()
        # Transports use bounded reads. Avoid closing a Windows handle while a
        # worker is using it; the worker owns transport cleanup.
        if self._thread and self._thread is not threading.current_thread():
            self._thread.join(timeout=1)
        if not self._thread or not self._thread.is_alive():
            self._set_status('closed')
