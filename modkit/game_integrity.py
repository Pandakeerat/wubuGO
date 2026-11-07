"""Local game inventory and owner-created baselines, not Valve depot verification."""
from __future__ import annotations
import hashlib
import json
import os
import tempfile
from pathlib import Path
from .retrokit import APP_ID, game_root, ensure_game_stopped, protected_target

STEAM_VERIFY_URI = f'steam://validate/{APP_ID}'
STEAM_INSTALL_URI = f'steam://install/{APP_ID}'
EXCLUDED_DIRS = {'migi', '.git', '__pycache__'}


def inspect_install(root):
    root = game_root(root)
    manifest = root.parent.parent / f'appmanifest_{APP_ID}.acf'
    problems = []
    for name in ('csgo/gameinfo.txt', 'csgo/steam.inf'):
        path = root / name
        if not path.is_file():
            problems.append('Missing: ' + name)
        elif not os.access(path, os.R_OK):
            problems.append('Not readable: ' + name)
    return {'root': str(root), 'steam_manifest_present': manifest.is_file(),
            'inventory_ok': not problems, 'problems': problems,
            'official_integrity_verified': False,
            'verification_note': 'Local file presence only. Steam verifies depot content via its own validation workflow.',
            'steam_verify_uri': STEAM_VERIFY_URI}


def _base_files(root):
    for path in sorted(root.rglob('*')):
        relative = path.relative_to(root)
        if any(part in EXCLUDED_DIRS for part in relative.parts):
            continue
        if path.is_symlink() or any(parent.is_symlink() for parent in path.parents if parent != root):
            continue
        if not path.is_file():
            continue
        if '.wubugo' in path.name or path.name.startswith('wubugo_'):
            continue
        yield path


def _hash(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def create_baseline(root, destination, progress=None):
    """Snapshot local base files. progress(done_files, total_files, relative_path)."""
    root = game_root(root)
    ensure_game_stopped()
    destination = Path(destination).expanduser().resolve()
    if destination == root or root in destination.parents:
        raise ValueError('Store integrity baselines outside the Steam game folder')
    files = list(_base_files(root))
    records = {}
    for i, path in enumerate(files, 1):
        name = path.relative_to(root).as_posix()
        before = path.stat()
        digest = _hash(path)
        after = path.stat()
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise ValueError('File changed while hashing: ' + name)
        records[name] = {'size': after.st_size, 'sha256': digest}
        if progress:
            progress(i, len(files), name)
    result = {'format': 1, 'app_id': APP_ID, 'root': str(root), 'kind': 'local-owner-baseline',
              'official_integrity_verified': False, 'files': records}
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix='.baseline-', dir=destination.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(result, stream, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        Path(tmp).replace(destination)
    finally:
        Path(tmp).unlink(missing_ok=True)
    return result


def verify_baseline(root, baseline, progress=None):
    root = game_root(root)
    ensure_game_stopped()
    baseline = Path(baseline)
    if baseline.stat().st_size > 32_000_000:
        raise ValueError('Integrity baseline exceeds size limit')
    data = json.loads(baseline.read_text(encoding='utf-8'))
    if data.get('format') != 1 or data.get('kind') != 'local-owner-baseline' or data.get('app_id') != APP_ID:
        raise ValueError('Unrecognised local baseline format')
    records = data.get('files')
    if not isinstance(records, dict) or len(records) > 200000:
        raise ValueError('Invalid baseline file records')
    changed, missing, unsafe = [], [], []
    for i, (name, record) in enumerate(records.items(), 1):
        if not isinstance(name, str) or '\\' in name or ':' in name or name.startswith('/') or '..' in Path(name).parts:
            raise ValueError('Unsafe baseline path')
        path = root / name
        try:
            protected_target(root, path)
        except ValueError:
            unsafe.append(name)
            continue
        if not isinstance(record, dict) or not isinstance(record.get('size'), int) or not isinstance(record.get('sha256'), str):
            raise ValueError('Invalid baseline hash record')
        if not path.is_file():
            missing.append(name)
        elif path.stat().st_size != record['size'] or _hash(path) != record['sha256']:
            changed.append(name)
        if progress:
            progress(i, len(records), name)
    return {'ok': not (changed or missing or unsafe), 'checked': len(records),
            'changed': changed, 'missing': missing, 'unsafe': unsafe,
            'official_integrity_verified': False,
            'note': 'Compared against your local snapshot. This does not authenticate files against Valve depots.'}
