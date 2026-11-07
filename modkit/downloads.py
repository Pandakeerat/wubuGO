"""Explicit, bounded HTTPS downloads. Downloads are staged, never executed.

No network request occurs when constructing a manager or reading its history.
"""
from __future__ import annotations

import hashlib
import json
import os
import queue
import re
import threading
import time
import uuid
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, HTTPRedirectHandler, build_opener

_ACTIVE = {'queued', 'downloading', 'verifying'}
_MAX_HISTORY = 500
_USER_AGENT = 'wubuGO/6.0 (explicit user download)'


def _https_url(url, trusted_hosts=None):
    if not isinstance(url, str) or len(url) > 8192 or any(ord(c) < 32 for c in url):
        raise ValueError('Expected a bounded HTTPS URL')
    parts = urlsplit(url)
    try:
        port = parts.port
    except ValueError as exc:
        raise ValueError('Invalid URL port') from exc
    if (parts.scheme != 'https' or not parts.hostname or parts.username is not None
            or parts.password is not None or parts.fragment or port not in (None, 443)):
        raise ValueError('Only HTTPS URLs without credentials or fragments are supported')
    if trusted_hosts is not None and parts.hostname.lower() not in {str(h).lower() for h in trusted_hosts}:
        raise ValueError('URL host is not in the configured trusted host list')
    return url


class _HTTPSRedirects(HTTPRedirectHandler):
    def __init__(self, trusted_hosts=None):
        super().__init__()
        self.trusted_hosts = trusted_hosts

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _https_url(newurl, self.trusted_hosts)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _open_url(url, timeout, trusted_hosts=None):
    _https_url(url, trusted_hosts)
    opener = build_opener(_HTTPSRedirects(trusted_hosts))
    return opener.open(Request(url, headers={'User-Agent': _USER_AGENT, 'Accept-Encoding': 'identity'}), timeout=timeout)


def _filename(name):
    if (not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._ -]{0,179}', name)
            or name.endswith((' ', '.')) or name.split('.')[0].upper() in
            {'CON', 'PRN', 'AUX', 'NUL', *('COM'+str(i) for i in range(1, 10)),
             *('LPT'+str(i) for i in range(1, 10))}
            or name.lower() == 'history.json'):
        raise ValueError('Choose a plain safe filename (no paths or reserved names)')
    return name


def _checksum(value):
    if value is None:
        return None
    if not isinstance(value, str) or not re.fullmatch(r'[0-9a-fA-F]{64}', value):
        raise ValueError('SHA-256 must contain exactly 64 hexadecimal characters')
    return value.lower()


class DownloadManager:
    """One background download at a time, with JSON snapshots safe for GUI polling.

    Completed files are in downloads_dir. Partial files live in .partial/. A
    completed general download can be unverified if no digest was provided;
    application update staging always requires a SHA-256 digest.
    """
    def __init__(self, downloads_dir, *, max_bytes=2 * 1024**3, timeout=30):
        self.directory = Path(downloads_dir).expanduser().resolve()
        self.directory.mkdir(parents=True, exist_ok=True)
        self.partial_directory = self.directory / '.partial'
        self.partial_directory.mkdir(exist_ok=True)
        if self.partial_directory.is_symlink():
            raise ValueError('Partial download directory must not be a symlink')
        self.max_bytes = int(max_bytes)
        self.timeout = float(timeout)
        if self.max_bytes <= 0 or self.timeout <= 0:
            raise ValueError('Download size and timeout must be positive')
        self._lock = threading.RLock()
        self._jobs = {}
        self._cancel = {}
        self._queue = queue.Queue()
        self._closed = False
        self.history_path = self.directory / 'history.json'
        self._read_history()
        self._worker = threading.Thread(target=self._run, name='wubuGO-downloads', daemon=True)
        self._worker.start()

    def _read_history(self):
        try:
            if self.history_path.is_symlink() or self.history_path.stat().st_size > 2_000_000:
                return
            history = json.loads(self.history_path.read_text(encoding='utf-8'))
            if not isinstance(history, list):
                return
            for item in history[-_MAX_HISTORY:]:
                if not isinstance(item, dict) or not re.fullmatch(r'[0-9a-f]{32}', str(item.get('id', ''))):
                    continue
                try:
                    _filename(item.get('filename'))
                except ValueError:
                    continue
                if (item.get('status') not in _ACTIVE | {'complete', 'cancelled', 'failed', 'interrupted'}
                        or type(item.get('downloaded')) is not int or item['downloaded'] < 0
                        or (item.get('total') is not None and (type(item['total']) is not int or item['total'] < 0))):
                    continue
                # Never reuse paths supplied by a history file for filesystem writes.
                item['path'] = str(self.directory / item['filename'])
                item['temporary_path'] = str(self.partial_directory / (item['id'] + '.part'))
                if item.get('status') in _ACTIVE:
                    item.update(status='interrupted', error='Application stopped before this download completed. Start a new download to retry.')
                self._jobs[item['id']] = item
        except (OSError, ValueError, TypeError):
            return  # Corrupt history never prevents starting the manager.

    def _persist_locked(self):
        temporary = self.directory / '.history.pending.json'
        if temporary.is_symlink() or self.history_path.is_symlink():
            raise ValueError('Download history must not be a symlink')
        data = list(self._jobs.values())[-_MAX_HISTORY:]
        temporary.write_text(json.dumps(data, indent=2), encoding='utf-8')
        temporary.replace(self.history_path)

    def jobs(self):
        """Return independent snapshots, oldest first; progress is None if unknown."""
        with self._lock:
            snapshots = []
            for value in self._jobs.values():
                item = dict(value)
                total = item.get('total')
                item['progress'] = (1.0 if item.get('status') == 'complete' else
                    min(1.0, item.get('downloaded', 0) / total) if isinstance(total, int) and total > 0 else None)
                snapshots.append(item)
            return snapshots

    def submit(self, url, filename, expected_sha256=None, expected_size=None):
        """Queue a download and return its id. Reject collisions rather than overwrite."""
        _https_url(url)
        filename = _filename(filename)
        digest = _checksum(expected_sha256)
        if expected_size is not None and (type(expected_size) is not int or not 0 <= expected_size <= self.max_bytes):
            raise ValueError('Expected size exceeds download limit or is invalid')
        with self._lock:
            if self._closed:
                raise RuntimeError('Download manager is closed')
            target = self.directory / filename
            if target.exists() or target.is_symlink() or any(j['filename'].casefold() == filename.casefold() and j['status'] in _ACTIVE for j in self._jobs.values()):
                raise FileExistsError('A download with this filename already exists')
            if any(p.name.casefold() == filename.casefold() for p in self.directory.iterdir()):
                raise FileExistsError('A file with this filename already exists')
            job_id = uuid.uuid4().hex
            self._jobs[job_id] = dict(id=job_id, url=url, filename=filename, status='queued',
                downloaded=0, total=expected_size, expected_size=expected_size,
                expected_sha256=digest, sha256=None, sha256_verified=False,
                temporary_path=str(self.partial_directory / (job_id + '.part')),
                path=str(target), error=None, created_at=time.time())
            self._cancel[job_id] = threading.Event()
            self._persist_locked()
            self._queue.put(job_id)
            return job_id

    def cancel(self, job_id):
        """Request cancellation. Completed files are retained."""
        with self._lock:
            if job_id not in self._jobs:
                raise KeyError(job_id)
            event = self._cancel.get(job_id)
            if event is not None and self._jobs[job_id]['status'] in _ACTIVE:
                event.set()
                return True
            return False

    def close(self, wait=False):
        """Cancel pending work; do not block the GUI unless wait=True is requested."""
        with self._lock:
            if not self._closed:
                self._closed = True
                for event in self._cancel.values():
                    event.set()
                self._queue.put(None)
        if wait:
            self._worker.join(timeout=self.timeout + 2)

    def _update(self, job_id, *, persist=True, **changes):
        with self._lock:
            self._jobs[job_id].update(changes)
            if persist:
                self._persist_locked()

    def _run(self):
        while True:
            job_id = self._queue.get()
            try:
                if job_id is None:
                    return
                self._download(job_id)
            finally:
                self._queue.task_done()

    def _download(self, job_id):
        with self._lock:
            job = dict(self._jobs[job_id])
            cancelled = self._cancel[job_id]
        part = Path(job['temporary_path'])
        target = Path(job['path'])
        try:
            if cancelled.is_set():
                raise InterruptedError('Download cancelled')
            self._update(job_id, status='downloading')
            hasher = hashlib.sha256()
            count = 0
            with _open_url(job['url'], self.timeout) as response:
                _https_url(response.geturl())
                raw_length = response.headers.get('Content-Length')
                total = int(raw_length) if raw_length is not None else job['expected_size']
                if total is not None and (total < 0 or total > self.max_bytes):
                    raise ValueError('Response exceeds download size limit')
                if job['expected_size'] is not None and total is not None and total != job['expected_size']:
                    raise ValueError('Response size does not match expected size')
                self._update(job_id, total=total)
                last_saved = time.monotonic()
                with part.open('xb') as output:
                    while True:
                        if cancelled.is_set():
                            raise InterruptedError('Download cancelled')
                        chunk = response.read(128 * 1024)
                        if not chunk:
                            break
                        count += len(chunk)
                        if count > self.max_bytes or (total is not None and count > total):
                            raise ValueError('Download exceeds declared size or configured limit')
                        output.write(chunk)
                        hasher.update(chunk)
                        persist = time.monotonic() - last_saved > .5
                        self._update(job_id, downloaded=count, persist=persist)
                        if persist:
                            last_saved = time.monotonic()
                    output.flush()
                    os.fsync(output.fileno())
            if cancelled.is_set():
                raise InterruptedError('Download cancelled')
            if total is not None and count != total:
                raise ValueError('Download truncated before expected size')
            if job['expected_size'] is not None and count != job['expected_size']:
                raise ValueError('Downloaded size does not match expected size')
            self._update(job_id, status='verifying', downloaded=count, total=count)
            actual = hasher.hexdigest()
            if job['expected_sha256'] is not None and actual != job['expected_sha256']:
                raise ValueError('SHA-256 mismatch; download will not be published')
            if cancelled.is_set():
                raise InterruptedError('Download cancelled')
            # Hard-link publication fails if another process created the destination.
            # Downloads and .partial are deliberately on the same filesystem.
            os.link(part, target)
            part.unlink()
            self._update(job_id, status='complete', sha256=actual,
                         sha256_verified=job['expected_sha256'] is not None, completed_at=time.time())
        except Exception as exc:
            try:
                part.unlink(missing_ok=True)
            except OSError:
                pass
            try:
                self._update(job_id, status='cancelled' if isinstance(exc, InterruptedError) else 'failed',
                             error=str(exc), completed_at=time.time())
            except (OSError, ValueError):
                # A read-only/full history directory must not kill the queue worker.
                with self._lock:
                    self._jobs[job_id].update(status='failed', error=str(exc))


def _version(value):
    if not isinstance(value, str) or not re.fullmatch(r'\d+\.\d+\.\d+', value):
        raise ValueError('Release versions must be numeric major.minor.patch')
    return tuple(map(int, value.split('.')))


def check_update(manifest_url, *, current_version, trusted_hosts, timeout=15):
    """Explicitly check a publisher-controlled HTTPS JSON manifest.

    No default endpoint is invented. A checksum validates transfer integrity; it
    does not replace trusting the publisher and HTTPS manifest host.
    """
    if not trusted_hosts:
        raise ValueError('Configure trusted update hosts before checking updates')
    _https_url(manifest_url, trusted_hosts)
    current = _version(current_version)
    with _open_url(manifest_url, timeout, trusted_hosts) as response:
        _https_url(response.geturl(), trusted_hosts)
        raw = response.read(131_073)
    if len(raw) > 131_072:
        raise ValueError('Update manifest exceeds 128 KiB')
    manifest = json.loads(raw.decode('utf-8'))
    if not isinstance(manifest, dict):
        raise ValueError('Update manifest must be an object')
    release = _version(manifest.get('version'))
    assets = manifest.get('assets')
    if not isinstance(assets, dict) or not assets:
        raise ValueError('Update manifest must list platform assets')
    validated = {}
    for platform, asset in assets.items():
        if not isinstance(platform, str) or not isinstance(asset, dict):
            raise ValueError('Invalid update platform asset')
        digest = _checksum(asset.get('sha256'))
        if digest is None:
            raise ValueError('Every update asset requires a SHA-256 digest')
        size = asset.get('size')
        if type(size) is not int or size < 0 or size > 2 * 1024**3:
            raise ValueError('Every update asset requires a valid bounded size')
        validated[platform] = dict(url=_https_url(asset.get('url'), trusted_hosts),
            filename=_filename(asset.get('filename')), sha256=digest, size=size)
    return dict(version=manifest['version'], available=release > current,
                notes=str(manifest.get('notes', ''))[:10_000], assets=validated)


def stage_update(manager, release, platform):
    """Stage a checked platform installer; never execute it or replace a live app."""
    if not release.get('available'):
        raise ValueError('No newer update is available')
    asset = release['assets'][platform]
    if not _checksum(asset.get('sha256')):
        raise ValueError('Update staging requires a SHA-256 checksum')
    return manager.submit(asset['url'], asset['filename'], asset['sha256'], asset['size'])
