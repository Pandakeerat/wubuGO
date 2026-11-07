"""Separate read-only release assets from per-user mutable app data."""
from __future__ import annotations
import json
import os
import sys
import tempfile
from pathlib import Path

VERSION = '6.0.0'


def resource_root():
    return Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent.parent))


def state_root():
    override = os.environ.get('WUBUGO_DATA_DIR')
    if override:
        return Path(override).expanduser().resolve()
    if os.name == 'nt':
        base = Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData/Local'))
        return base / 'wubuGO'
    return Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local/share')) / 'wubugo'


def atomic_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name+'.', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(data, stream, indent=2, allow_nan=False)
            stream.write('\n')
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def load_settings(path):
    try:
        data = json.loads(Path(path).read_text(encoding='utf-8'))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}
