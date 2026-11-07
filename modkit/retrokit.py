"""wubuGO Steam CS:GO (2026 standalone App 4465480) local mod manager.

No Valve binaries bundled. Uses only -insecure launches for mods, with optional MIGI.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import csv
import io
import tempfile
from pathlib import Path

from .panorama_ui import patch_files, patch_zip, install_to_bridge, restore_bridge
from .schema_audit import audit
from .weapon_balance import generate, create_2016_addon
from .sources import download_2016, validate_2016
from .external_process import popen_external, run_external, external_environment

APP_ID = '4465480'
CFG_NAME = 'wubugo_2016.cfg'
GAME_FOLDER_NAMES = ['csgo legacy', 'Counter-Strike Global Offensive', 'Counter-Strike Global Offensive Legacy']
PROFILE = r'''// wubuGO 2016-inspired HUD/preferences; not real Scaleform.
cl_hud_background_alpha "0.75"
cl_hud_bomb_under_radar "1"
cl_hud_color "0"
cl_hud_healthammo_style "0"
cl_hud_playercount_showcount "0"
cl_hud_playercount_pos "0"
cl_radar_always_centered "0"
cl_radar_scale "0.4"
cl_radar_icon_scale_min "0.6"
cl_showloadout "1"
hud_scaling "0.85"
safezonex "0.95"
safezoney "0.95"
viewmodel_fov "60"
viewmodel_offset_x "1"
viewmodel_offset_y "1"
viewmodel_offset_z "-1"
viewmodel_presetpos "0"
'''


def _steam_roots():
    homes = [Path(os.environ['STEAM_ROOT'])] if os.environ.get('STEAM_ROOT') else []
    homes += [Path.home() / '.local/share/Steam', Path.home() / '.steam/steam',
             Path.home() / '.var/app/com.valvesoftware.Steam/.local/share/Steam']
    if os.name == 'nt':
        for var in ['PROGRAMFILES(X86)', 'PROGRAMFILES', 'STEAM_ROOT']:
            if os.environ.get(var):
                homes.append(Path(os.environ[var]) / 'Steam' if var != 'STEAM_ROOT' else Path(os.environ[var]))
        for drive in 'CDEFGHIJKLMNOPQRSTUVWXYZ':
            homes.extend([Path(f'{drive}:/Steam'), Path(f'{drive}:/SteamLibrary'), Path(f'{drive}:/Program Files (x86)/Steam')])
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Valve\Steam') as k:
                homes.append(Path(winreg.QueryValueEx(k, 'SteamPath')[0]))
        except (OSError, ImportError):
            pass
    return list(dict.fromkeys(x for x in homes))


def _game_executable(root):
    names = ('csgo.exe',) if os.name == 'nt' else ('csgo_linux64', 'csgo_linux', 'csgo.sh', 'csgo.exe')
    return next((root / name for name in names if (root / name).is_file()), None)


def _is_install(root):
    # CS2 stores binaries under game/bin; a Source 1 executable is required.
    return (root / 'csgo').is_dir() and bool(_game_executable(root))


def running_game_processes():
    """Return visible CS:GO processes. Unknown process status fails closed on writes."""
    if os.name == 'nt':
        try:
            output = run_external(['tasklist', '/FO', 'CSV', '/NH'], capture_output=True,
                                    text=True, timeout=8, check=True).stdout
            return [row[0] for row in csv.reader(io.StringIO(output)) if row and
                    row[0].lower() in {'csgo.exe', 'csgo_linux', 'csgo_linux64'}]
        except (OSError, subprocess.SubprocessError) as exc:
            raise OSError('Cannot check running games; close CS:GO and retry: ' + str(exc)) from exc
    proc = Path('/proc')
    if not proc.is_dir():
        raise OSError('Cannot check running games: /proc is unavailable')
    found = []
    for path in proc.iterdir():
        if not path.name.isdigit():
            continue
        try:
            name = (path / 'comm').read_text().strip().lower()
        except OSError:
            continue
        if name in {'csgo.exe', 'csgo_linux', 'csgo_linux64'}:
            found.append(path.name + ':' + name)
    return found


def ensure_game_stopped():
    if running_game_processes():
        raise ValueError('Close CS:GO before changing files or starting another session')


def protected_target(root, target):
    """Reject linked paths before writing inside a selected installation."""
    root, target = Path(root).resolve(), Path(target)
    try:
        rel = target.relative_to(root)
    except ValueError as exc:
        raise ValueError('Target is outside the selected game') from exc
    current = root
    for part in rel.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError('Refusing to modify a linked game path: ' + str(current))
    return target


def _atomic_text(path, content):
    fd, pending = tempfile.mkstemp(prefix='.wubugo-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        Path(pending).replace(path)
    finally:
        Path(pending).unlink(missing_ok=True)



def detect_games():
    matches = []
    for steam in _steam_roots():
        libraries = [steam]
        lib_file = steam / 'steamapps/libraryfolders.vdf'
        if lib_file.is_file():
            try:
                text = lib_file.read_text(encoding='utf-8-sig', errors='replace')
            except OSError:
                text = ''
            libraries += [Path(m.group(1).replace('\\\\', '\\')) for m in re.finditer(r'"path"\s+"([^"]+)"', text, re.I)]
        for lib in libraries:
            common = lib / 'steamapps/common'
            for name in GAME_FOLDER_NAMES:
                game = common / name
                if _is_install(game):
                    matches.append(game.resolve())
            # Handle non-standard manually renamed folders only when manifest points there.
            manifest = lib / f'steamapps/appmanifest_{APP_ID}.acf'
            if manifest.is_file():
                try:
                    contents = manifest.read_text(encoding='utf-8-sig', errors='replace')
                except OSError:
                    continue
                install_dir = re.search(r'"installdir"\s+"([^"]+)"', contents, re.I)
                if install_dir:
                    folder = install_dir.group(1)
                    if '/' in folder or '\\' in folder or folder in {'.', '..'} or ':' in folder:
                        continue
                    game = common / folder
                    if _is_install(game):
                        matches.append(game.resolve())
    return list(dict.fromkeys(matches))


def game_root(path=None):
    if path:
        candidate = Path(path).expanduser().resolve()
        if candidate.is_file():
            candidate = candidate.parent
        # Can pass a csgo subfolder or a Steam library common path.
        if candidate.name.lower() == 'csgo' and _is_install(candidate.parent):
            candidate = candidate.parent
        if not _is_install(candidate):
            raise ValueError(f'{candidate} is not an installed Source 1 CS:GO directory with csgo.exe and csgo/. Select Steam > CS:GO > Manage > Browse local files. NOT CS2.')
        return candidate
    matches = detect_games()
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        raise ValueError('Multiple CS:GO installs found. Specify --game: ' + ' | '.join(map(str, matches)))
    raise FileNotFoundError('Steam CS:GO not detected. Select your "csgo legacy" game folder explicitly.')


def _cfg(root):
    return root / 'csgo' / 'cfg' / CFG_NAME


def _addons(root):
    return root / 'migi' / 'csgo' / 'addons'


def doctor(root):
    root = game_root(root)
    exe = _game_executable(root)
    inf = root / 'csgo/steam.inf'
    inf_text = inf.read_text(errors='replace') if inf.exists() else ''
    ids = re.search(r'(?im)^appID\s*=\s*(\d+)', inf_text)
    info = {
        'game_folder': str(root),
        'native_linux_available': any((root/name).is_file() for name in ('csgo_linux64','csgo_linux','csgo.sh')),
        'platform_note': 'Windows csgo.exe on Linux requires a locally installed Proton runtime selected in Settings. MIGI/Bridge remain unverified under Proton.',
        'executable': str(exe),
        'standalone_manifest_found': (root.parent.parent / f'appmanifest_{APP_ID}.acf').is_file(),
        'steam_inf_app_id': ids.group(1) if ids else None,
        'steam_inf_note': '730 in older game data can be normal; Steam manifests determine the installed app. Do not hand-edit steam.inf.',
        'migi_exe_exists': (root / 'migi.exe').is_file(),
        'migi_initialized': (root / 'migi/csgo/gameinfo.txt').is_file(),
        'hud_cfg_installed': _cfg(root).is_file(),
        'weapon_addon_installed': (_addons(root) / 'm_wubugo_2016').is_dir(),
        'in_game_menu_installed': (_addons(root) / 'p_wubugo_2016menu').is_dir(),
        'scaleform_hud_addon_installed': (_addons(root) / 'p_scaleform').is_dir(),
        'scaleform_note': 'The legacy client uses Panorama. A working in-game 2016-like HUD needs a compatible Panorama replacement loader; cannot enable original 2016 Scaleform in game settings.',
    }
    return info


def install_profile(root, replace=False):
    root = game_root(root)
    ensure_game_stopped()
    cfg = protected_target(root, _cfg(root))
    protected_target(root, cfg.with_suffix('.cfg.wubugo.bak'))
    cfg.parent.mkdir(parents=True, exist_ok=True)
    if cfg.is_file():
        current = cfg.read_text(encoding='utf-8')
        if current == PROFILE:
            return cfg  # repeatable, harmless
        if not replace:
            raise FileExistsError(f'{cfg} already exists and differs. Use --replace to back it up.')
        backup = cfg.with_suffix('.cfg.wubugo.bak')
        if backup.exists():
            raise FileExistsError(f'Backup already exists: {backup}')
        shutil.copy2(cfg, backup)
    _atomic_text(cfg, PROFILE)
    return cfg


def install_addon(root, source, replace=False):
    """Install a MIGI addon safely, preserving prior versions on repeat setup."""
    root = game_root(root)
    ensure_game_stopped()
    src = Path(source).expanduser().resolve()
    if any(p.is_symlink() for p in src.rglob('*')):
        raise ValueError('Addon source contains linked files')
    if src.name not in {'m_wubugo_2016', 'p_wubugo_2016menu'}:
        raise ValueError('Expected a wubuGO-generated MIGI addon directory')
    if src.name.startswith('m_') and not (src / 'scripts/items/items_game_wubugo_2016.txt').exists():
        raise ValueError('Weapon addon is incomplete')
    if src.name.startswith('p_') and not (src / 'panorama/layout/mainmenu.xml').exists():
        raise ValueError('UI addon is incomplete')
    if not (root / 'migi.exe').is_file():
        raise ValueError('MIGI is missing. Download MIGI3 from its official page and place migi.exe next to csgo.exe; initialise it first.')
    if not (root / 'migi/csgo/gameinfo.txt').exists():
        raise ValueError('MIGI not initialised yet. Run migi.exe according to official instructions.')
    destination = protected_target(root, _addons(root) / src.name)
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Idempotence: if every source file matches, no backup or rewrite needed.
    if destination.exists():
        if any(p.is_symlink() for p in destination.rglob('*')):
            raise ValueError('Installed addon contains linked files; inspect it before replacement')
        files = [p for p in src.rglob('*') if p.is_file()]
        target_files = {p.relative_to(destination) for p in destination.rglob('*') if p.is_file()}
        if target_files == {p.relative_to(src) for p in files} and all((destination / p.relative_to(src)).is_file() and
               (destination / p.relative_to(src)).read_bytes() == p.read_bytes()
               for p in files):
            return destination
        if not replace:
            raise FileExistsError('An older addon is installed; use replace to back it up.')
    stage = protected_target(root, destination.parent / (src.name + '.wubugo-staging'))
    if stage.exists():
        raise FileExistsError('A previous incomplete install exists: ' + str(stage))
    shutil.copytree(src, stage)
    try:
        if destination.exists():
            backup = destination.with_name(destination.name + '.wubugo.backup')
            i = 1
            while backup.exists():
                backup = destination.with_name(destination.name + f'.wubugo.backup.{i}')
                i += 1
            protected_target(root, backup)
            destination.rename(backup)
        try:
            stage.rename(destination)
        except OSError:
            if 'backup' in locals() and backup.exists() and not destination.exists():
                backup.rename(destination)
            raise
    finally:
        if stage.exists():
            shutil.rmtree(stage)
    return destination


def launch(root, use_migi=False, extra=(), proton=None):
    """Launch genuine Steam client's binary with the proper working directory.

    Not a way of injecting Panorama; see separate optional Bridge setup.
    """
    root = game_root(root)
    exe = _game_executable(root)
    ensure_game_stopped()
    if os.name != 'nt' and use_migi:
        raise ValueError('MIGI is Windows-only in this release; native/Proton MIGI builds are unverified. Use a plain local launch.')
    if use_migi and not (root / 'migi/csgo/gameinfo.txt').is_file():
        raise ValueError('MIGI is not initialised. Run migi.exe, Build / Update Build, then retry.')
    # Even plain launch runs insecure because this launcher is meant for local mod testing.
    args = ['-steam', '-insecure', '-console', '-novid']
    if os.name == 'nt':
        args.append('-worldwide')
    if use_migi:
        args += ['-game', 'migi/csgo']
    profile = protected_target(root, _cfg(root))
    if profile.is_file():
        if profile.read_text(encoding='utf-8') != PROFILE:
            raise ValueError('The wubuGO profile has been edited; restore it before launching through wubuGO')
        args += ['+exec', CFG_NAME]
    preferences = protected_target(root, root/'csgo/cfg/wubugo_preferences.cfg')
    if preferences.is_file():
        from .game_settings import verify_installed_settings
        verify_installed_settings(root)
        args += ['+exec', 'wubugo_preferences.cfg']
    safe_extra = list(extra)
    if safe_extra and (len(safe_extra) != 2 or safe_extra[0] != '+map'
                       or not re.fullmatch(r'[A-Za-z0-9_]+', str(safe_extra[1]))):
        raise ValueError('Only a local +map argument is supported; connection and console overrides are blocked')
    args += ['+sv_lan', '1']
    args.extend(safe_extra or ['+map', 'de_dust2'])
    env = None
    if os.name == 'nt':
        env = external_environment()
        if (root / 'bin').is_dir():
            env['PATH'] = str(root / 'bin') + ';' + env.get('PATH', '')
    if os.name != 'nt' and exe.suffix.lower() == '.exe':
        if not proton:
            raise ValueError('This is a Windows CS:GO build. Select your installed Proton executable in Settings, or select a native Linux game build.')
        proton_exe = Path(proton).expanduser().resolve()
        if not proton_exe.is_file() or not os.access(proton_exe, os.X_OK):
            raise ValueError('Selected Proton executable is missing or not executable')
        # Proton must know Steam's client and compatibility prefix, even for a direct launch.
        steamapps = root.parent.parent
        steam_client = next((p for p in _steam_roots() if (p/'steamapps').is_dir()), None)
        if steam_client is None:
            raise ValueError('Steam client path not detected; set STEAM_ROOT to the installed Linux Steam folder')
        compat_data = protected_target(steamapps, steamapps/'compatdata'/APP_ID)
        compat_data.mkdir(parents=True, exist_ok=True)
        env = os.environ.copy()
        env.update({'STEAM_COMPAT_CLIENT_INSTALL_PATH': str(steam_client),
                    'STEAM_COMPAT_DATA_PATH': str(compat_data),
                    'SteamAppId': APP_ID, 'SteamGameId': APP_ID})
        cmd = [str(proton_exe), 'run', str(exe), *args]
    else:
        if os.name != 'nt' and not os.access(exe, os.X_OK):
            raise ValueError('Native CS:GO launcher is not executable. Repair the game through Steam.')
        cmd = [str(exe), *args]
    print('Starting:', subprocess.list2cmdline(cmd) if os.name == 'nt' else ' '.join(cmd))
    return popen_external(cmd, cwd=str(root), env=env)


def main(argv=None):
    p = argparse.ArgumentParser(description='wubuGO: CS:GO 2016-style local mod tools (not CS2).')
    sub = p.add_subparsers(dest='command', required=True)
    sub.add_parser('detect')
    for name in ['doctor', 'install-profile', 'launch', 'uninstall-profile', 'install-addon']:
        q = sub.add_parser(name)
        q.add_argument('--game', help='Steam CS:GO directory (csgo legacy) or csgo.exe')
        if name in {'install-profile', 'install-addon'}:
            q.add_argument('--replace', action='store_true')
        if name == 'install-addon':
            q.add_argument('--addon', required=True)
        if name == 'launch':
            q.add_argument('--migi', action='store_true')
            q.add_argument('--proton', help='Linux: explicit path to an installed Proton executable')
            q.add_argument('--map', help='Offline map, e.g. de_dust2')
    imp = sub.add_parser('import-2016-weapons')
    imp.add_argument('--2016', dest='old_schema', required=True)
    imp.add_argument('--current', dest='current_schema')
    imp.add_argument('--game')
    imp.add_argument('--out', default='build/2016-weapon-addon')
    fetch = sub.add_parser('fetch-2016')
    fetch.add_argument('--out', default='data/wubugo_offline_2016_subset.json')
    build = sub.add_parser('build-2016')
    build.add_argument('--2016', dest='source', default='data/wubugo_offline_2016_subset.json')
    build.add_argument('--out', default='build/weapons')
    au = sub.add_parser('audit-items')
    au.add_argument('schema')
    ui = sub.add_parser('build-in-game-menu')
    mx = ui.add_mutually_exclusive_group(required=True)
    mx.add_argument('--original-zip', help='Original CS:GO Panorama ZIP, exported locally by a compatible bridge')
    mx.add_argument('--mainmenu-xml', help='Extracted CS:GO Panorama layout/mainmenu.xml from your own client')
    ui.add_argument('--out', default='build/2016-menu')
    bridge = sub.add_parser('bridge-menu')
    bridge.add_argument('--bridge', required=True, help='Existing Panorama Bridge directory with Launch.cmd and generated panorama.my.zip')
    bridge.add_argument('--restore', action='store_true', help='Restore the previous working bridge menu ZIP')
    args = p.parse_args(argv)
    try:
        if args.command == 'detect':
            print(json.dumps({'expected_steam_app_id': APP_ID, 'installations': list(map(str, detect_games()))}, indent=2))
        elif args.command == 'fetch-2016':
            path, info = download_2016(Path(args.out))
            print(f'Downloaded {path}, {info["audit"]["weapon_item_count"]} weapons, source {info["source_url"]}')
        elif args.command == 'build-2016':
            validate_2016(Path(args.source))
            addon, report, n = create_2016_addon(Path(args.source), Path(args.out))
            print(f'Generated {n} 2016 weapon overrides: {addon} (report: {report})')
        elif args.command == 'audit-items':
            print(json.dumps(audit(args.schema), indent=2))
        elif args.command == 'build-in-game-menu':
            out = Path(args.out)
            if args.original_zip:
                path = patch_zip(Path(args.original_zip), out / 'panorama.wubugo.zip')
                print('Patched Panorama archive:', path)
                print('Requires a separately configured compatible archive loader. Do not overwrite originals.')
            else:
                print('Generated MIGI/Bridge candidate menu files:', patch_files(Path(args.mainmenu_xml), out))
                print('These are integration assets, not a guaranteed loaded in-game menu.')
        elif args.command == 'bridge-menu':
            if args.restore:
                print('Restored original Bridge replacement:', restore_bridge(Path(args.bridge)))
            else:
                updated, backup = install_to_bridge(Path(args.bridge))
                print('Patched in-game Panorama menu ZIP:', updated)
                print('Recovery copy:', backup)
                print('Run the existing Bridge Launch.cmd (offline -insecure); this is a Panorama replica, not real Scaleform.')
        elif args.command == 'import-2016-weapons':
            validate_2016(Path(args.old_schema))
            current = Path(args.current_schema) if args.current_schema else None
            addon, report, n = create_2016_addon(Path(args.old_schema), Path(args.out), current)
            print(f'{n} verified weapons. MIGI addon: {addon}. Report: {report}')
        else:
            root = game_root(args.game)
            if args.command == 'doctor':
                print(json.dumps(doctor(root), indent=2))
            elif args.command == 'install-profile':
                print('HUD profile installed:', install_profile(root, args.replace))
            elif args.command == 'uninstall-profile':
                ensure_game_stopped()
                cfg = protected_target(root, _cfg(root))
                if not cfg.is_file():
                    print('No wubuGO profile found.')
                elif cfg.read_text(encoding='utf-8') != PROFILE:
                    raise ValueError('Profile has been edited; will not remove without permission')
                else:
                    cfg.unlink()
                    print('Removed:', cfg)
            elif args.command == 'install-addon':
                print('Installed:', install_addon(root, args.addon, args.replace))
                print('Open MIGI and click Build / Update Build before launching. Compatible loader may also be needed for Panorama UI.')
            elif args.command == 'launch':
                extra = []
                if args.map:
                    if not re.fullmatch(r'[A-Za-z0-9_]+', args.map):
                        raise ValueError('Invalid map name')
                    extra = ['+map', args.map]
                launch(root, args.migi, extra, proton=args.proton)
        return 0
    except (OSError, ValueError, KeyError, UnicodeError, EOFError) as exc:
        print('ERROR:', exc, file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
