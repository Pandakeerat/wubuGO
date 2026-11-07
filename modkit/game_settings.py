"""Whitelisted preferences with checksummed ownership and versioned recovery."""
from __future__ import annotations
import hashlib
import json
import math
import re
from pathlib import Path

DEFAULTS = {'volume': 0.7, 'sensitivity': 2.5, 'fps_max': 144, 'hud_scaling': 0.85,
            'cl_radar_scale': 0.4, 'cl_crosshairsize': 3.0, 'cl_crosshairgap': -1.0}
LIMITS = {'volume': (0,1), 'sensitivity': (0.1,20), 'fps_max': (30,1000),
          'hud_scaling': (0.5,0.95), 'cl_radar_scale': (0.25,1),
          'cl_crosshairsize': (0,20), 'cl_crosshairgap': (-10,10)}
HEADER = '// Generated wubuGO preferences. Offline/private use.\n'
NAME = 'wubugo_preferences.cfg'


def validate_settings(values):
    if not isinstance(values, dict) or set(values) - set(DEFAULTS):
        raise ValueError('Unknown game setting')
    result = {}
    for name, default in DEFAULTS.items():
        value = values.get(name, default)
        if isinstance(value, bool):
            raise ValueError('Invalid '+name)
        try:
            value = float(value)
        except (ValueError, TypeError) as exc:
            raise ValueError('Invalid '+name) from exc
        low, high = LIMITS[name]
        if not math.isfinite(value) or not low <= value <= high:
            raise ValueError(f'{name} must be between {low} and {high}')
        if name == 'fps_max' and not value.is_integer():
            raise ValueError('fps_max must be a whole number')
        result[name] = value
    return result


def render_settings(values):
    return HEADER + ''.join(f'{key} "{value:g}"\n' for key,value in validate_settings(values).items())


def _paths(root):
    from .retrokit import game_root, ensure_game_stopped, protected_target
    root = game_root(root)
    ensure_game_stopped()
    target = protected_target(root, root/'csgo/cfg'/NAME)
    receipt = protected_target(root, target.with_name(NAME+'.wubugo.json'))
    return root, target, receipt


def _digest(data):
    return hashlib.sha256(data).hexdigest()


def _load_receipt(receipt):
    if not receipt.exists():
        return None
    try:
        if receipt.stat().st_size > 2_000_000:
            raise ValueError('Receipt too large')
        data = json.loads(receipt.read_text(encoding='utf-8'))
        if data.get('format') != 1 or not isinstance(data.get('history'), list):
            raise ValueError('Unknown receipt format')
        for item in [data, *data['history']]:
            if not isinstance(item, dict) or not isinstance(item.get('managed'), bool):
                raise ValueError('Invalid ownership record')
            digest = item.get('sha256')
            if digest is not None and (not isinstance(digest,str) or not re.fullmatch('[a-f0-9]{64}',digest)):
                raise ValueError('Invalid receipt checksum')
        for item in data['history']:
            backup = item.get('backup')
            if backup is not None and (not isinstance(backup,str) or not re.fullmatch(re.escape(NAME)+r'\.wubugo\.bak\.\d+',backup)):
                raise ValueError('Unsafe backup name')
            if (backup is None) != (item.get('sha256') is None):
                raise ValueError('Invalid backup record')
        return data
    except (OSError, ValueError, TypeError, AttributeError) as exc:
        raise ValueError('Preferences recovery metadata is damaged; preserve files and inspect it before changing preferences') from exc


def _unique(root, target, suffix):
    from .retrokit import protected_target
    i = 1
    while True:
        path = protected_target(root,target.with_name(NAME+suffix+str(i)))
        if not path.exists():
            return path
        i += 1


def _atomic_bytes(path, data):
    import os
    import tempfile
    fd, temporary = tempfile.mkstemp(prefix='.wubugo-preferences-',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        Path(temporary).replace(path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def _publish(target, receipt, content, metadata, previous):
    """If publishing metadata fails, restore the previous target bytes."""
    _atomic_bytes(target,content) if content is not None else target.unlink()
    try:
        _atomic_bytes(receipt,json.dumps(metadata,indent=2).encode('utf-8'))
    except OSError:
        if previous is None:
            target.unlink(missing_ok=True)
        else:
            _atomic_bytes(target,previous)
        raise


def install_settings(root, values):
    content = render_settings(values).encode('utf-8')
    root, target, receipt = _paths(root)
    prior = target.read_bytes() if target.exists() else None
    data = _load_receipt(receipt)
    if data is not None and data['sha256'] != (_digest(prior) if prior is not None else None):
        raise ValueError('Preferences were edited outside wubuGO; preserve those edits before replacing them')
    if prior == content and data is not None and data['managed']:
        return target
    target.parent.mkdir(parents=True,exist_ok=True)
    history = list(data['history']) if data else []
    backup = _unique(root,target,'.wubugo.bak.') if prior is not None else None
    if backup:
        _atomic_bytes(backup,prior)
    history.append({'backup': backup.name if backup else None,
                    'sha256': _digest(prior) if prior is not None else None,
                    'managed': data['managed'] if data else False})
    metadata = {'format':1,'sha256':_digest(content),'managed':True,'history':history}
    _publish(target,receipt,content,metadata,prior)
    return target


def rollback_settings(root):
    from .retrokit import protected_target
    root,target,receipt = _paths(root)
    data = _load_receipt(receipt)
    if not data or not data['managed'] or not data['history'] or not target.is_file():
        raise ValueError('No tracked manager-owned preferences to restore')
    current = target.read_bytes()
    if _digest(current) != data['sha256']:
        raise ValueError('Preferences were edited outside wubuGO; refusing rollback')
    previous = data['history'][-1]
    content = None
    if previous['backup']:
        backup = protected_target(root,target.with_name(previous['backup']))
        if not backup.is_file():
            raise FileNotFoundError('Preferences backup is missing')
        content = backup.read_bytes()
        if _digest(content) != previous['sha256']:
            raise ValueError('Preferences backup checksum changed; refusing rollback')
    recovery = _unique(root,target,'.wubugo.disabled.')
    _atomic_bytes(recovery,current)
    metadata = {'format':1,'sha256':previous['sha256'],'managed':previous['managed'],
                'history':data['history'][:-1]}
    _publish(target,receipt,content,metadata,current)
    return target


def verify_installed_settings(root):
    """Require an intact tracked cfg before the launcher auto-executes it."""
    root,target,receipt = _paths(root)
    if not target.is_file():
        return False
    data = _load_receipt(receipt)
    if not data or not data['managed'] or _digest(target.read_bytes()) != data['sha256']:
        raise ValueError('Installed preferences are untracked or edited; restore/reinstall them before launching through wubuGO')
    return True


def read_installed_settings(root):
    """Read only intact, manager-owned preferences; never interpret foreign cfgs."""
    root,target,receipt = _paths(root)
    data = _load_receipt(receipt)
    if not target.is_file() or not data or not data['managed']:
        return None
    content = target.read_bytes()
    if _digest(content) != data['sha256']:
        raise ValueError('Preferences were edited outside wubuGO; saved values were not changed')
    text = content.decode('utf-8')
    if not text.startswith(HEADER):
        raise ValueError('Tracked preferences have an invalid header')
    values = {}
    for line in text[len(HEADER):].splitlines():
        match = re.fullmatch(r'([A-Za-z0-9_]+) "([^"\r\n]+)"', line)
        if not match or match[1] not in DEFAULTS or match[1] in values:
            raise ValueError('Tracked preferences do not match the supported setting format')
        values[match[1]] = match[2]
    if set(values) != set(DEFAULTS):
        raise ValueError('Tracked preferences are missing supported settings')
    result = validate_settings(values)
    if render_settings(result).encode('utf-8') != content:
        raise ValueError('Tracked preferences are not a generated settings file')
    return result
