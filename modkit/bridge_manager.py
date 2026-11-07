"""Separate opt-in bridge setup for an in-game Scaleform-style Panorama HUD."""
from __future__ import annotations
from pathlib import Path
from urllib.request import urlopen, Request
import io
import zipfile
import shutil

URL = 'https://github.com/wallbangs/panorama-bridge-csgo/archive/refs/heads/main.zip'


def fetch_bridge(destination: Path):
    destination = Path(destination)
    if destination.exists() and any(destination.iterdir()):
        raise FileExistsError(f'Bridge folder already has files: {destination}. Select existing bridge instead.')
    req = Request(URL, headers={'User-Agent': 'wubuGO-ModManager/4.0'})
    with urlopen(req, timeout=35) as response:
        blob = response.read(30_000_001)
    if len(blob) >= 30_000_001:
        raise ValueError('Bridge archive exceeds 30MB; refusing download')
    return import_bridge_bytes(blob, destination)


def import_bridge_archive(archive: Path, destination: Path):
    archive = Path(archive)
    if archive.stat().st_size > 30_000_000:
        raise ValueError('Bridge archive too large')
    return import_bridge_bytes(archive.read_bytes(), destination)


def import_bridge_bytes(blob: bytes, destination: Path):
    """Import rootless or GitHub ZIPs, validating everything before publication."""
    import tempfile
    from pathlib import PurePosixPath
    import stat
    destination = Path(destination).resolve()
    if destination.exists() and (not destination.is_dir() or any(destination.iterdir())):
        raise FileExistsError(f'Bridge folder already has files: {destination}')
    if len(blob) > 30_000_000:
        raise ValueError('Bridge archive too large')
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        entries = z.infolist()
        if len(entries) > 1000 or sum(e.file_size for e in entries) > 150_000_000:
            raise ValueError('Bridge archive exceeds extraction limits')
        names = []
        for e in entries:
            raw = e.filename.replace('\\', '/')
            parts = PurePosixPath(raw).parts
            if (not parts or raw.startswith('/') or any(
                    part in {'.', '..'} or ':' in part or part.endswith((' ', '.'))
                    or part.split('.')[0].upper() in {'CON','PRN','AUX','NUL',
                        *('COM'+str(i) for i in range(1,10)), *('LPT'+str(i) for i in range(1,10))}
                    for part in parts) or stat.S_ISLNK(e.external_attr >> 16)):
                raise ValueError('Unsafe repository entry: ' + e.filename)
            names.append(parts)
        files = [parts for e, parts in zip(entries, names) if not e.is_dir()]
        prefix = ()
        if not any(parts == ('Setup.cmd',) for parts in files):
            roots = {parts[0] for parts in files}
            if len(roots) != 1:
                raise ValueError('Expected one Bridge folder or a rootless ZIP')
            prefix = (next(iter(roots)),)
        mapped = [(e, parts[len(prefix):]) for e, parts in zip(entries, names)]
        keys = [ '/'.join(parts).casefold() for e, parts in mapped if parts ]
        if len(keys) != len(set(keys)):
            raise ValueError('Duplicate archive paths')
        if not all(any(parts == (name,) and not e.is_dir() for e, parts in mapped)
                   for name in ('Setup.cmd', 'Launch.cmd')):
            raise ValueError('Expected Setup.cmd and Launch.cmd in Bridge archive')
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='wubugo-import-', dir=destination.parent) as tmp:
            stage = Path(tmp) / 'bridge'
            stage.mkdir()
            for e, parts in mapped:
                if not parts:
                    continue
                target = stage.joinpath(*parts)
                if e.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with z.open(e) as src, target.open('xb') as dst:
                        shutil.copyfileobj(src, dst)
            if destination.exists():
                destination.rmdir()  # only an empty destination can be replaced
            stage.rename(destination)
    return destination


def dependency_catalog():
    """Reviewed upstream pins for optional downloads; never authorizes execution."""
    import json
    path = Path(__file__).resolve().parent.parent / 'data/bridge_dependencies.json'
    return json.loads(path.read_text(encoding='utf-8'))


def inspect_bridge(folder: Path, game_folder=None, downloads_folder=None, platform=None):
    """Read-only inventory with platform and missing-dependency details.

    Presence/checksum checks establish local file availability only. They cannot
    establish that an injector, engine build or UI event actually works.
    """
    import re
    import sys
    import json
    import hashlib
    folder = Path(folder)
    platform = sys.platform if platform is None else platform
    scripts = {}
    urls = set()
    script_files = ('Setup.cmd', 'Launch.cmd', 'setup.ps1', 'launch.ps1',
                    'install_addon.ps1', 'install_resources.ps1', 'install_migi.ps1',
                    'build_archive.py', 'apply_addon_patch.py')
    for name in script_files:
        path = folder / name
        scripts[name] = path.is_file()
        if path.is_file():
            urls.update(re.findall(r'https?://[^\s"<>]+', path.read_text(errors='replace')))
    payloads = {name: (folder / name).is_file() for name in (
        'PanoramaBridge32.dll', 'panorama-inject32.exe', 'enable-replacement.flag',
        'addon-patch.json')}
    config_path = folder / 'local-settings.json'
    config_error = None
    config_present = config_path.is_file()
    if config_present:
        try:
            config = json.loads(config_path.read_text(encoding='utf-8-sig'))
            if not isinstance(config, dict):
                raise ValueError('Expected object')
            # Do not trust a third-party config to silently select another game.
            if game_folder is not None and config.get('GameFolder'):
                if Path(config['GameFolder']).resolve() != Path(game_folder).resolve():
                    config_error = 'Bridge config points to a different game folder'
        except (OSError, ValueError, TypeError):
            config_error = 'Bridge local-settings.json is unreadable or malformed'
    missing = [name for name, present in {**scripts, **payloads}.items() if not present]
    if not config_present:
        missing.append('local-settings.json (manual setup not completed)')
    game_checks = {}
    if game_folder is not None:
        game = Path(game_folder)
        game_checks = {
            'windows_game_executable': (game / 'csgo.exe').is_file(),
            'migi_executable': (game / 'migi.exe').is_file(),
            'migi_initialized': (game / 'migi/csgo/gameinfo.txt').is_file(),
            'addon_layout': (game / 'migi/csgo/addons/p_scaleform/panorama/layout').is_dir(),
            'addon_styles': (game / 'migi/csgo/addons/p_scaleform/panorama/styles').is_dir(),
            'addon_scripts': (game / 'migi/csgo/addons/p_scaleform/panorama/scripts').is_dir(),
        }
        missing.extend(name for name, present in game_checks.items() if not present)
    cached = []
    if downloads_folder is not None:
        for dep in dependency_catalog()['dependencies']:
            path = Path(downloads_folder) / dep['filename']
            verified = False
            if path.is_file():
                try:
                    with path.open('rb') as stream:
                        digest = hashlib.sha256()
                        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                            digest.update(chunk)
                        verified = digest.hexdigest() == dep['sha256']
                except OSError:
                    pass
            cached.append({'id': dep['id'], 'filename': dep['filename'],
                           'present': path.is_file(), 'checksum_verified': verified})
    supported = platform == 'win32'
    return {'scripts': scripts, 'payloads': payloads, 'game_checks': game_checks,
            'referenced_urls': sorted(urls), 'cached_dependencies': cached,
            'missing': missing, 'config_present': config_present, 'config_error': config_error,
            'platform_supported': supported,
            'platform_note': 'Bridge requires a compatible Windows x86 Source 1 client and Windows injector. Fedora native Bridge support is unavailable.',
            'replacement_archive_present': (folder / 'panorama.my.zip').is_file(),
            'offline_dependencies_verified': False, 'in_game_verified': False,
            'note': 'Import never runs setup. ZIP presence is not runtime verification. '
                    'Review upstream setup and supply its dependencies locally. Automatic external script execution is disabled.'}
