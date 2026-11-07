import json
import socket
import struct
import threading
import time
import unittest
from unittest.mock import patch

from modkit.presence import Presence, _frame, MAX_FRAME, ipc_paths


class FakeTransport:
    def __init__(self, incoming=b''):
        self.incoming = bytearray(incoming)
        self.outgoing = []
        self.closed = False

    def read(self, count):
        if self.incoming:
            data = bytes(self.incoming[:min(count, 3)])
            del self.incoming[:len(data)]
            return data
        time.sleep(0.005)
        raise socket.timeout()

    def write(self, data):
        self.outgoing.append(data)

    def close(self):
        self.closed = True


class PresenceTests(unittest.TestCase):
    def test_requires_application_id_not_token(self):
        for value in ('', 'abc', '123', 123456789012345678):
            with self.assertRaises(ValueError):
                Presence(value)

    def test_opt_in_no_connection_until_started(self):
        calls = []
        client = Presence('123456789012345678', _connector=lambda: calls.append(1))
        self.assertEqual(client.status, 'disabled')
        self.assertEqual(calls, [])
        client.close()

    def test_fragmented_frames_preserve_protocol(self):
        client = Presence('123456789012345678')
        transport = FakeTransport(_frame(1, {'evt': 'READY'}))
        opcode, payload = client._read_frame(transport)
        self.assertEqual(opcode, 1)
        self.assertEqual(payload['evt'], 'READY')

    def test_oversized_peer_rejected_before_allocation(self):
        client = Presence('123456789012345678')
        transport = FakeTransport(struct.pack('<II', 1, MAX_FRAME + 1))
        with self.assertRaises(ValueError):
            client._read_frame(transport)

    def test_handshake_activity_ping_and_close(self):
        transport = FakeTransport(_frame(1, {'evt': 'READY'}) + _frame(3, {'ping': 'test'}))
        client = Presence('123456789012345678', _connector=lambda: transport)
        client.start()
        deadline = time.monotonic() + 2
        while len(transport.outgoing) < 3 and time.monotonic() < deadline:
            time.sleep(0.01)
        client.close()
        decoded = [(struct.unpack('<II', item[:8])[0], json.loads(item[8:])) for item in transport.outgoing]
        self.assertEqual(decoded[0], (0, {'v': 1, 'client_id': '123456789012345678'}))
        self.assertTrue(any(code == 4 and data == {'ping': 'test'} for code, data in decoded))
        activity = next(data['args']['activity'] for code, data in decoded if data.get('cmd') == 'SET_ACTIVITY')
        self.assertEqual(activity['details'], 'wubuGO')
        self.assertEqual(client.status, 'closed')
        self.assertTrue(transport.closed)

    def test_missing_desktop_is_actionable_and_close_interrupts_retry(self):
        def unavailable():
            raise OSError('Discord desktop unavailable')
        client = Presence('123456789012345678', _connector=unavailable)
        client.start()
        deadline = time.monotonic() + 1
        while client.status != 'disconnected' and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertIn('Discord desktop', client.error)
        client.close()
        self.assertEqual(client.status, 'closed')

    @unittest.skipIf(__import__('os').name == 'nt', 'Linux endpoint test')
    def test_linux_flatpak_paths(self):
        with patch.dict('os.environ', {'XDG_RUNTIME_DIR': '/run/user/1234'}):
            paths = ipc_paths()
        self.assertIn('/run/user/1234/discord-ipc-0', paths)
        self.assertIn('/run/user/1234/app/com.discordapp.Discord/discord-ipc-0', paths)
