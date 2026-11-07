"""Fetch independently archived CS:GO 2016 gameplay statistics.

2016-era items_game.txt holds item ids, prefabs and economic information,
NOT a complete collection of weapon damage/recoil numbers. Prior versions
tried to extract game balance from it and rejected valid downloads.

The separate archive is a historical, extracted weapon-script snapshot from
CS:GO 1.35.4.4, dated 3 August 2016. No Valve files are redistributed.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from urllib.request import Request, urlopen

COMMIT = '1dba1e4'  # schema reference (28 July 2016), not gameplay stats
DATE = '2016-08-03'
VERSION = '1.35.4.4'
FILENAME = f'weapons-{VERSION}.json'
SOURCE_REPO = 'twowordbird/csgo-weapon-json-output'
SOURCE_COMMIT = '16cf45aa6e77a440a698ac0fc3df4c23f839aa38'
SOURCE_SHA256 = '3f953c057bfa83ebdbec79229c939aa80a6c3b69fc090c31b076fa01516356cd'
SOURCES = [
    f'https://raw.githubusercontent.com/{SOURCE_REPO}/{SOURCE_COMMIT}/{FILENAME}',
    f'https://cdn.jsdelivr.net/gh/{SOURCE_REPO}@{SOURCE_COMMIT}/{FILENAME}',
]

# Historical schema remains useful for ID verification, but is not used to
# generate recoil/damage. This link was provided by the user.
ITEM_SCHEMA = f'https://raw.githubusercontent.com/SteamDatabase/GameTracking/{COMMIT}/csgo/csgo/scripts/items/items_game.txt'

REQUIRED_STATS = {'name', 'damage', 'price', 'recoil_magnitude', 'cycle_time', 'inaccuracy_stand', 'armor_ratio'}


def validate_2016(path: Path) -> dict:
    """Validate a complete, historic weapon-stat archive, not econ schema."""
    try:
        content = json.loads(Path(path).read_text(encoding='utf-8-sig'))
    except (ValueError, UnicodeError) as ex:
        raise ValueError('Expected the weapons-1.35.4.4.json file, not items_game.txt.') from ex
    if not isinstance(content, dict) or content.get('version') != VERSION:
        raise ValueError(f'Historical stats must be game version {VERSION} (August 2016).')
    weapons = content.get('weapons')
    if not isinstance(weapons, list) or len(weapons) < (15 if content.get('scope') == 'verified-subset' else 27):
        raise ValueError(f'Incomplete 2016 source: found {len(weapons) if isinstance(weapons,list) else 0} weapons.')
    import math
    names = set()
    for weapon in weapons:
        if not isinstance(weapon, dict) or (REQUIRED_STATS - ({'armor_ratio'} if content.get('scope') == 'verified-subset' else set())).difference(weapon):
            raise ValueError('Archive is missing required weapon fields.')
        if not isinstance(weapon.get('name'), str) or not weapon['name'].strip():
            raise ValueError('Invalid weapon name')
        if any(not math.isfinite(v) for v in weapon.values() if isinstance(v, (int, float))):
            raise ValueError('Nonfinite weapon statistics are not supported')
        if isinstance(weapon['damage'], bool) or not isinstance(weapon['damage'], (int, float)) or weapon['damage'] <= 0:
            raise ValueError('Archive contains an invalid damage value.')
        if weapon['name'] in names:
            raise ValueError('Archive repeats a weapon name.')
        names.add(weapon['name'])
    for w in ('AK-47', 'AWP', 'M4A4', 'M4A1-S', 'Desert Eagle'):
        if w not in names:
            raise ValueError(f'Historical archive is missing {w}.')
    source_digest = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    return {'version': VERSION, 'date': DATE, 'weapon_item_count': len(weapons),
            'source_sha256': source_digest, 'provenance_verified': source_digest == SOURCE_SHA256,
            'weapon_examples': [w['name'] for w in weapons[:10]], 'scope': content.get('scope','complete'),
            'suitable_as_2016_weapon_source': True, 'notes': ['2016 weapon statistics (not items_game schema).', 'Bundled subset leaves other weapons untouched.' if content.get('scope') == 'verified-subset' else 'Full upstream snapshot.']}


def download_2016(destination: Path):
    dest = Path(destination)
    dest.parent.mkdir(parents=True, exist_ok=True)
    failures = []
    for url in SOURCES:
        temporary = None
        try:
            request = Request(url, headers={'User-Agent': 'wubuGO/5.0 (CSGO local mod tool)', 'Accept': 'application/json'})
            with urlopen(request, timeout=30) as resp:
                data = resp.read(850_001)
            if len(data) > 850_000 or len(data) < 10_000:
                raise ValueError(f'Unexpected download size: {len(data)} bytes')
            if hashlib.sha256(data).hexdigest() != SOURCE_SHA256:
                raise ValueError('Historical source checksum mismatch')
            # Validate before replacing any previous known-good downloaded source.
            with tempfile.NamedTemporaryFile('wb', suffix='.json', dir=dest.parent, delete=False) as tmp:
                tmp.write(data)
                temporary = Path(tmp.name)
            audit = validate_2016(temporary)
            os.replace(temporary, dest)
            temporary = None
            metadata = {'source_url': url, 'source_repo': SOURCE_REPO,
                        'version': VERSION, 'date': DATE, 'source_commit': SOURCE_COMMIT,
                        'sha256': hashlib.sha256(data).hexdigest(), 'audit': audit}
            dest.with_suffix('.source.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')
            return dest, metadata
        except Exception as error:
            failures.append(f'{url}\n{error}')
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
    raise RuntimeError('Could not download 2016 weapon stats. Please check your connection or use IMPORT LOCAL JSON.\n\n' + '\n\n'.join(failures))


def offline_source(project_root: Path):
    """Bundled reference file requiring no internet to install or prepare."""
    path = Path(project_root) / 'data' / FILENAME
    if not path.is_file():
        path = Path(project_root) / 'data' / 'wubugo_offline_2016_subset.json'
    elif hashlib.sha256(path.read_bytes()).hexdigest() != SOURCE_SHA256:
        raise ValueError('Bundled historical source checksum mismatch; restore the application bundle')
    validate_2016(path)
    return path


def ensure_source(destination: Path, project_root: Path, allow_online=False):
    """Prefer a locally cached full source, then bundled offline source.

    Online mode is always explicit: no surprise access to GitHub during setup.
    """
    path = Path(destination)
    if path.exists():
        try:
            return path, validate_2016(path)
        except (OSError, ValueError):
            pass
    if allow_online:
        downloaded, metadata = download_2016(path)
        return downloaded, metadata['audit']
    offline = offline_source(project_root)
    return offline, validate_2016(offline)
