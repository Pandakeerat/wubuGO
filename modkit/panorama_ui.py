"""Create a Steam-CSGO Panorama *style* overlay from a user's own UI archive.

The replacement must be loaded by a compatible Panorama archive loader such as
an independently installed and tested bridge. Never edits the Steam game files.
The classic Scaleform runtime is NOT added by this module.
"""
from __future__ import annotations

import re
import zipfile
from pathlib import Path

STYLESHEET = r'''/* wubuGO 2016 look for legacy CS:GO Panorama; not genuine Scaleform. */
.Retro2016Panel {
    width: 328px;
    height: 100%;
    flow-children: down;
    background-color: gradient(linear, 0% 0%, 100% 0%, from(#1a2938ee), to(#0d1929e8));
    border-right: 2px solid #FFCE9F;
    padding: 42px 28px;
    vertical-align: top;
    horizontal-align: left;
    z-index: 150;
}
.Retro2016Title { color: #FFF5EA; font-size: 40px; font-weight: bold; margin-bottom: 3px; }
.Retro2016Subtitle { color: #FFCE9F; font-size: 14px; letter-spacing: 2px; margin-bottom: 40px; }
.Retro2016Button {
    width: 270px; height: 52px;
    padding: 12px 15px;
    background-color: #293f4cae;
    border-bottom: 1px solid #506777;
    margin-bottom: 8px;
}
.Retro2016Button:hover { background-color: #FFCE9F; }
.Retro2016Button Label { font-size: 23px; color: #1A1B1E; font-weight: bold; }
.Retro2016Foot { font-size: 13px; color: #adbac3; margin-top: 30px; }
'''

MENU = r'''<!-- wubuGO 2016 LOOK overlay; active inside Panorama when archive loader works -->
<Panel id="Retro2016MenuPanel" class="Retro2016Panel MainMenuModeOnly" hittest="true">
    <Label class="Retro2016Title" text="COUNTER-STRIKE" />
    <Label class="Retro2016Subtitle" text="GLOBAL OFFENSIVE / 2016" />
    <Button class="Retro2016Button" onactivate="GameInterfaceAPI.ConsoleCommand('sv_lan 1; map de_dust2');"><Label text="PLAY LOCAL DUST II" /></Button>
    <Button class="Retro2016Button" onactivate="MainMenu.NavigateToTab('JsInventory', 'mainmenu_inventory');"><Label text="INVENTORY" /></Button>
    <Button class="Retro2016Button" onactivate="MainMenu.NavigateToTab('JsWatch', 'mainmenu_watch'); MainMenu.WatchBtnPressedUpdateAlert();"><Label text="WATCH" /></Button>
    <Button class="Retro2016Button" onactivate="MainMenu.NavigateToTab('JsPlayerStats', 'mainmenu_playerstats');"><Label text="AWARDS / STATS" /></Button>
    <Button class="Retro2016Button" onactivate="MainMenu.NavigateToTab('JsSettings', 'settings/settings');"><Label text="OPTIONS" /></Button>
    <Button class="Retro2016Button" onactivate="GameInterfaceAPI.ConsoleCommand('sv_lan 1; map de_mirage');"><Label text="PLAY LOCAL MIRAGE" /></Button>
    <Label class="Retro2016Foot" text="WUBUGO | PRIVATE / OFFLINE" />
</Panel>
'''


def patch_mainmenu(xml: str) -> str:
    if 'id="Retro2016MenuPanel"' in xml:
        raise ValueError('This XML has already been patched by wubuGO')
    if 's2r://' in xml:
        raise ValueError('Source 2/CS2 Panorama XML supplied; expected Source 1 CS:GO mainmenu.xml')
    if '<CSGOMainMenu' not in xml or '</CSGOMainMenu>' not in xml or '</styles>' not in xml:
        raise ValueError('Unrecognised CS:GO Panorama main menu; do not apply incompatible patch')
    xml = xml.replace('</styles>', '    <include src="file://{resources}/styles/wubugo_2016.css" />\n</styles>', 1)
    # Keep game launch actions local; do not dispatch a matchmaking play menu.
    menu = MENU
    before, closing = xml.rsplit('</CSGOMainMenu>', 1)
    return before + menu + '\n</CSGOMainMenu>' + closing


def patch_zip(original: Path, dest: Path):
    """Patch one local user's UI archive; supports two common archive layouts."""
    original = Path(original)
    dest = Path(dest)
    if original.resolve() == dest.resolve():
        raise ValueError('Original and output archive cannot be the same path')
    import tempfile
    import os
    if dest.exists():
        raise FileExistsError('Output archive already exists; choose a new destination')
    with zipfile.ZipFile(original) as z:
        candidates = [name for name in z.namelist() if name.replace('\\', '/').lower().endswith('layout/mainmenu.xml')]
        if len(candidates) != 1:
            raise ValueError('Cannot locate a unique layout/mainmenu.xml in your original Panorama ZIP')
        entry = candidates[0]
        layout_dir = entry[: -len('layout/mainmenu.xml')]
        style_name = layout_dir + 'styles/wubugo_2016.css'
        if style_name in z.namelist():
            raise ValueError('Archive already contains wubugo_2016.css')
        patch = patch_mainmenu(z.read(entry).decode('utf-8-sig'))
        dest.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=dest.parent, suffix='.pending.zip', delete=False) as tmp:
            pending = Path(tmp.name)
        try:
            with zipfile.ZipFile(pending, 'w') as out:
                for item in z.infolist():
                    out.writestr(item, patch.encode('utf-8') if item.filename == entry else z.read(item.filename))
                out.writestr(style_name, STYLESHEET.encode('utf-8'), compress_type=zipfile.ZIP_DEFLATED)
            with zipfile.ZipFile(pending) as final:
                if final.testzip() is not None or b'Retro2016MenuPanel' not in final.read(entry):
                    raise ValueError('Generated UI archive failed integrity checks')
            os.replace(pending, dest)
        finally:
            pending.unlink(missing_ok=True)
    return dest


def patch_files(mainmenu: Path, output_dir: Path):
    """Build layout/style files for integration by an installed Panorama replacement tool."""
    output = Path(output_dir) / 'p_wubugo_2016menu' / 'panorama'
    (output / 'layout').mkdir(parents=True, exist_ok=True)
    (output / 'styles').mkdir(parents=True, exist_ok=True)
    (output / 'layout/mainmenu.xml').write_text(patch_mainmenu(Path(mainmenu).read_text(encoding='utf-8-sig')), encoding='utf-8')
    (output / 'styles/wubugo_2016.css').write_text(STYLESHEET, encoding='utf-8')
    return output.parent


def install_to_bridge(bridge_folder: Path):
    """Apply visual menu to an already generated Bridge ZIP (which may contain HUD).

    Requires user to set up the independent loader first. Keeps one recovery copy,
    and never modifies panorama.org.zip / Steam binaries. This is opt-in.
    """
    import shutil
    bridge_folder = Path(bridge_folder).expanduser().resolve()
    if not (bridge_folder / 'Launch.cmd').is_file():
        raise ValueError('Expected Panorama Bridge folder containing Launch.cmd')
    current = bridge_folder / 'panorama.my.zip'
    if not current.is_file():
        raise FileNotFoundError('Bridge has not generated panorama.my.zip yet. Follow Bridge Setup.cmd and launch it first.')
    backup = bridge_folder / 'panorama.my.zip.wubugo.bak'
    if backup.exists():
        raise FileExistsError('An existing backup was found. Restore it before running install again: ' + str(backup))
    candidate = bridge_folder / 'panorama.wubugo.pending.zip'
    try:
        patch_zip(current, candidate)
        shutil.copy2(current, backup)
        candidate.replace(current)
        return current, backup
    finally:
        if candidate.exists():
            candidate.unlink()


def restore_bridge(bridge_folder: Path):
    bridge_folder = Path(bridge_folder).expanduser().resolve()
    current = bridge_folder / 'panorama.my.zip'
    backup = bridge_folder / 'panorama.my.zip.wubugo.bak'
    if not backup.is_file():
        raise FileNotFoundError('No wubuGO backup exists')
    if not current.is_file():
        raise FileNotFoundError('Bridge target ZIP missing, refusing to overwrite')
    # Keep the modded file as a recovery artifact when rolling back.
    modded = bridge_folder / 'panorama.my.zip.wubugo.disabled'
    if modded.exists():
        raise FileExistsError('Recovery copy already exists: ' + str(modded))
    current.rename(modded)
    try:
        backup.rename(current)
    except OSError:
        modded.rename(current)
        raise
    return current
