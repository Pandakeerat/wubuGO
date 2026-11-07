import hashlib
import io
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from modkit.downloads import DownloadManager, check_update, stage_update, _HTTPSRedirects


class Response(io.BytesIO):
    def __init__(self, blob, length='auto', url='https://example.test/asset'):
        super().__init__(blob)
        self.headers = {} if length is None else {'Content-Length': str(len(blob) if length == 'auto' else length)}
        self.url = url

    def geturl(self):
        return self.url


def wait_for(manager, job_id):
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        job = next(j for j in manager.jobs() if j['id'] == job_id)
        if job['status'] not in {'queued', 'downloading', 'verifying'}:
            return job
        time.sleep(.005)
    raise AssertionError('Download worker did not finish')


class DownloadsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.manager = DownloadManager(self.root / 'downloads', max_bytes=1024)

    def tearDown(self):
        self.manager.close(wait=True)
        self.tmp.cleanup()

    def test_init_and_history_do_not_use_network(self):
        with patch('modkit.downloads._open_url', side_effect=AssertionError('network')):
            manager = DownloadManager(self.root / 'other')
            self.assertEqual(manager.jobs(), [])
            manager.close(wait=True)

    def test_verified_download_progress_and_history(self):
        payload = b'correct asset'
        with patch('modkit.downloads._open_url', return_value=Response(payload)):
            job_id = self.manager.submit('https://example.test/asset', 'asset.zip', hashlib.sha256(payload).hexdigest(), len(payload))
            job = wait_for(self.manager, job_id)
        self.assertEqual(job['status'], 'complete')
        self.assertTrue(job['sha256_verified'])
        self.assertEqual(job['progress'], 1)
        self.assertEqual(Path(job['path']).read_bytes(), payload)
        self.assertFalse(Path(job['temporary_path']).exists())
        history = json.loads(self.manager.history_path.read_text())
        self.assertEqual(history[0]['status'], 'complete')
        manager = DownloadManager(self.manager.directory)
        try:
            self.assertEqual(manager.jobs()[0]['downloaded'], len(payload))
        finally:
            manager.close(wait=True)

    def test_unknown_length_without_digest_is_explicitly_unverified(self):
        with patch('modkit.downloads._open_url', return_value=Response(b'asset', None)):
            job = wait_for(self.manager, self.manager.submit('https://example.test/asset', 'asset.zip'))
        self.assertEqual(job['status'], 'complete')
        self.assertFalse(job['sha256_verified'])
        self.assertEqual(job['downloaded'], 5)

    def test_digest_mismatch_never_publishes(self):
        with patch('modkit.downloads._open_url', return_value=Response(b'corrupt')):
            job = wait_for(self.manager, self.manager.submit('https://example.test/a', 'bad.zip', '0' * 64))
        self.assertEqual(job['status'], 'failed')
        self.assertIn('SHA-256', job['error'])
        self.assertFalse(Path(job['path']).exists())
        self.assertFalse(Path(job['temporary_path']).exists())

    def test_truncated_and_oversized_downloads_fail(self):
        for i, response in enumerate((Response(b'short', 20), Response(b'a' * 1025, None), Response(b'a', 5000))):
            with patch('modkit.downloads._open_url', return_value=response):
                job = wait_for(self.manager, self.manager.submit('https://example.test/a', f'bad{i}.zip'))
            self.assertEqual(job['status'], 'failed')
            self.assertFalse(Path(job['path']).exists())

    def test_size_mismatch_fails(self):
        with patch('modkit.downloads._open_url', return_value=Response(b'abc')):
            job = wait_for(self.manager, self.manager.submit('https://example.test/a', 'bad.zip', expected_size=4))
        self.assertEqual(job['status'], 'failed')

    def test_cancel_before_publish(self):
        entered, proceed = threading.Event(), threading.Event()
        class SlowResponse(Response):
            def read(self, size=-1):
                entered.set()
                proceed.wait(2)
                return super().read(size)
        with patch('modkit.downloads._open_url', return_value=SlowResponse(b'asset')):
            job_id = self.manager.submit('https://example.test/a', 'asset.zip')
            self.assertTrue(entered.wait(1))
            self.assertTrue(self.manager.cancel(job_id))
            proceed.set()
            job = wait_for(self.manager, job_id)
        self.assertEqual(job['status'], 'cancelled')
        self.assertFalse(Path(job['path']).exists())
        self.assertFalse(Path(job['temporary_path']).exists())

    def test_inflight_progress_and_queue_cancellation(self):
        entered, proceed = threading.Event(), threading.Event()
        class PausedResponse(Response):
            calls = 0
            def read(self, size=-1):
                self.calls += 1
                if self.calls == 1:
                    return b'abc'
                if self.calls == 2:
                    entered.set()
                    proceed.wait(2)
                    return b'def'
                return b''
        with patch('modkit.downloads._open_url', return_value=PausedResponse(b'', length=6)) as opener:
            first = self.manager.submit('https://example.test/one', 'one.zip')
            self.assertTrue(entered.wait(1))
            active = next(j for j in self.manager.jobs() if j['id'] == first)
            self.assertEqual(active['downloaded'], 3)
            self.assertEqual(active['progress'], .5)
            self.assertTrue(Path(active['temporary_path']).exists())
            second = self.manager.submit('https://example.test/two', 'two.zip')
            with self.assertRaises(FileExistsError):
                self.manager.submit('https://example.test/two', 'TWO.zip')
            self.manager.cancel(second)
            proceed.set()
            self.assertEqual(wait_for(self.manager, first)['status'], 'complete')
            self.assertEqual(wait_for(self.manager, second)['status'], 'cancelled')
            self.assertEqual(opener.call_count, 1)

    def test_existing_files_never_overwritten(self):
        (self.manager.directory / 'asset.zip').write_bytes(b'original')
        for name in ('asset.zip', 'ASSET.zip'):
            with self.assertRaises(FileExistsError):
                self.manager.submit('https://example.test/a', name)
        self.assertEqual((self.manager.directory / 'asset.zip').read_bytes(), b'original')

    def test_external_collision_during_download_never_overwritten(self):
        target = self.manager.directory / 'asset.zip'
        class RacingResponse(Response):
            def read(self, size=-1):
                target.write_bytes(b'external file')
                return super().read(size)
        with patch('modkit.downloads._open_url', return_value=RacingResponse(b'asset')):
            job = wait_for(self.manager, self.manager.submit('https://example.test/a', 'asset.zip'))
        self.assertEqual(job['status'], 'failed')
        self.assertEqual(target.read_bytes(), b'external file')

    def test_invalid_urls_names_sizes_and_checksums(self):
        for name in ('../escape', '/absolute', 'CON.txt', 'file:stream', 'history.json', 'trailing.', 'NUL'):
            with self.assertRaises(ValueError): self.manager.submit('https://example.test/a', name)
        for url in ('http://example.test/a', 'https://user:password@example.test/a', 'file:///tmp/a', 'https://example.test:123/a'):
            with self.assertRaises(ValueError): self.manager.submit(url, 'asset.zip')
        for digest in ('wrong', 'a' * 63):
            with self.assertRaises(ValueError): self.manager.submit('https://example.test/a', 'asset.zip', digest)
        for size in (-1, True, 1025):
            with self.assertRaises(ValueError): self.manager.submit('https://example.test/a', 'asset.zip', expected_size=size)

    def test_redirect_downgrade_is_rejected(self):
        with self.assertRaises(ValueError):
            _HTTPSRedirects().redirect_request(None, None, 302, 'redirect', {}, 'http://example.test/file')
        with self.assertRaises(ValueError):
            _HTTPSRedirects({'example.test'}).redirect_request(None, None, 302, 'redirect', {}, 'https://other.test/file')

    def test_closed_manager_rejects_new_downloads(self):
        self.manager.close(wait=True)
        with self.assertRaises(RuntimeError): self.manager.submit('https://example.test/a', 'asset.zip')

    def test_interrupted_history_is_not_resumed(self):
        directory = self.root / 'history'
        directory.mkdir()
        (directory / 'history.json').write_text(json.dumps([{'id': 'a' * 32, 'filename': 'asset.zip', 'status': 'downloading', 'downloaded': 3}]))
        with patch('modkit.downloads._open_url', side_effect=AssertionError('network')):
            manager = DownloadManager(directory)
            try:
                self.assertEqual(manager.jobs()[0]['status'], 'interrupted')
            finally:
                manager.close(wait=True)


class UpdateTests(unittest.TestCase):
    def manifest(self):
        return {'version': '6.1.0', 'notes': 'Publisher release', 'assets': {'windows-x64': {
            'url': 'https://example.test/wubuGO-6.1.0.exe', 'filename': 'wubuGO-6.1.0.exe',
            'size': 5, 'sha256': hashlib.sha256(b'asset').hexdigest()}}}

    def check(self, manifest, **kwargs):
        with patch('modkit.downloads._open_url', return_value=Response(json.dumps(manifest).encode())):
            return check_update('https://example.test/releases.json', current_version='6.0.0', trusted_hosts={'example.test'}, **kwargs)

    def test_check_and_stage_never_execute(self):
        release = self.check(self.manifest())
        self.assertTrue(release['available'])
        with tempfile.TemporaryDirectory() as tmp:
            manager = DownloadManager(tmp)
            try:
                with patch('modkit.downloads._open_url', return_value=Response(b'asset')):
                    job = wait_for(manager, stage_update(manager, release, 'windows-x64'))
                self.assertEqual(job['status'], 'complete')
                self.assertTrue(job['sha256_verified'])
            finally:
                manager.close(wait=True)

    def test_no_newer_release(self):
        manifest = self.manifest();manifest['version'] = '5.9.0'
        release = self.check(manifest)
        self.assertFalse(release['available'])
        with self.assertRaises(ValueError): stage_update(None, release, 'windows-x64')

    def test_reject_untrusted_hosts_missing_digest_and_invalid_version(self):
        for field, value in (('url', 'https://untrusted.test/file'), ('sha256', None), ('size', -1), ('filename', '../file')):
            manifest = self.manifest();manifest['assets']['windows-x64'][field] = value
            with self.assertRaises(ValueError): self.check(manifest)
        manifest = self.manifest();manifest['version'] = 'latest'
        with self.assertRaises(ValueError): self.check(manifest)
        with self.assertRaises(ValueError):
            check_update('https://example.test/releases.json', current_version='6.0.0', trusted_hosts=set())
