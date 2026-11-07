"""wubuGO cross-platform offline-first Python/Tk launcher. No game binaries bundled."""
from __future__ import annotations
import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from modkit.retrokit import (detect_games, game_root, doctor, install_profile,
                             install_addon, launch, _addons, _cfg)
from modkit.sources import DATE, COMMIT, SOURCES, download_2016, validate_2016, ensure_source, offline_source
from modkit.weapon_balance import create_2016_addon
from modkit.schema_audit import audit
from modkit.bridge_manager import fetch_bridge
from modkit.panorama_ui import install_to_bridge, restore_bridge
from modkit.asset_integrity import verify_assets
from .runtime import VERSION, resource_root, state_root, atomic_json, load_settings
from .pages import ExtraPages
from modkit.downloads import DownloadManager

PROJECT = resource_root()
STATE = state_root()
SETTINGS_FILE = STATE / 'config' / 'user_settings.json'
OLD_SOURCE = STATE / 'data' / 'weapons-1.35.4.4.json'
USER_SOURCE = PROJECT / 'data' / 'user_supplied_items_game_2023.txt'
ADDON_ROOT = STATE / 'build' / 'weapons'
BRIDGE_DEFAULT = STATE / 'third_party' / 'panorama-bridge-csgo'

C = {
    'bg': '#080f18', 'sidebar': '#0b1520', 'panel': '#111e2b',
    'panel2': '#152738', 'line': '#273b4b', 'muted': '#8da5b8',
    'text': '#eff5fa', 'gold': '#FFCE9F', 'blue': '#f6bc83',
    'green': '#63d6a3', 'red': '#eb7781', 'deep': '#0b141e',
}
FONT = 'Segoe UI' if sys.platform == 'win32' else 'DejaVu Sans'


def button(parent, label, action, style='secondary', width=None, small=False):
    colors = {
        'primary': ('#FFCE9F', '#15171c', '#ffdbb8'),
        'secondary': ('#223b50', C['text'], '#32536a'),
        'outline': (C['panel2'], '#cee2ef', '#29465c'),
        'danger': ('#462c35', '#f4c8ca', '#5a3541'),
    }
    bg, fg, hover = colors[style]
    f = (FONT, 9 if small else 10, 'bold')
    b = tk.Button(parent, text=label, command=action, font=f, bg=bg, fg=fg,
                  activebackground=hover, activeforeground=fg, relief='flat',
                  bd=0, cursor='hand2', padx=13 if small else 18,
                  pady=7 if small else 11, highlightthickness=0)
    if width:
        b.configure(width=width)
    b.bind('<Enter>', lambda event: b.configure(bg=hover))
    b.bind('<Leave>', lambda event: b.configure(bg=bg))
    return b


def text(parent, msg, size=10, weight='normal', fg=None, **kwargs):
    label = tk.Label(parent, text=msg, font=(FONT, size, weight), bg=parent.cget('bg'),
                     fg=fg or C['text'], anchor='w', justify='left', **kwargs)
    return label


def card(parent, margin=0):
    outer = tk.Frame(parent, bg=C['line'])
    inner = tk.Frame(outer, bg=C['panel'], padx=18, pady=17)
    inner.pack(fill='both', expand=True, padx=1, pady=1)
    return outer, inner


class Studio(ExtraPages, tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('wubuGO  |  CS:GO 2016 Mod Studio')
        self.geometry('1200x800')
        self.minsize(990, 690)
        self.configure(bg=C['bg'])
        self.game = None
        self.settings = self._read_settings()
        self.bridge_path = Path(self.settings.get('bridge', str(BRIDGE_DEFAULT)))
        self.page = 'Overview'
        self.presence = None
        self.game_process = None
        self.download_manager = DownloadManager(STATE / 'Downloads')
        self.download_widgets = {}
        self.operations = load_settings(STATE / 'operations.json').get('operations', [])
        for operation in self.operations:
            if operation.get('status') == 'running': operation['status'] = 'interrupted'
        self.active_operation = None
        self.events = queue.Queue()
        self.working = False
        self.log_history = []
        style = ttk.Style(self)
        style.theme_use('clam')
        style.configure('TProgressbar', background=C['gold'], troughcolor=C['deep'], bordercolor=C['line'], lightcolor=C['gold'], darkcolor=C['gold'])
        self._detect()
        self._build_shell()
        self.show_page('Overview' if self.settings.get('game') else 'Setup')
        self.after(120, self._drain)
        self.protocol('WM_DELETE_WINDOW', self._shutdown)
        self._start_presence()
        self._log(f'wubuGO {VERSION}. Offline historical data included. No network request at startup.')

    def _read_settings(self):
        return load_settings(SETTINGS_FILE)

    def _save_settings(self):
        atomic_json(SETTINGS_FILE, self.settings)

    def _detect(self):
        saved = self.settings.get('game')
        if saved:
            try:
                self.game = game_root(saved)
                return
            except (OSError, ValueError):
                pass
        games = detect_games()
        self.game = games[0] if len(games) == 1 else None
        if self.game:
            self.settings['game'] = str(self.game)
            self._save_settings()

    def _build_shell(self):
        self.side = tk.Frame(self, bg=C['sidebar'], width=233)
        self.side.pack(side='left', fill='y')
        self.side.pack_propagate(False)
        logo = tk.Frame(self.side, bg=C['sidebar'])
        logo.pack(fill='x', padx=23, pady=(27, 24))
        try:
            self.logo_image = tk.PhotoImage(file=str(PROJECT / 'assets/logo.png'))
            self.iconphoto(True, self.logo_image)
            self.sidebar_icon = self.logo_image.subsample(max(1, self.logo_image.width() // 64))
            tk.Label(logo, image=self.sidebar_icon, bg=C['sidebar']).pack(anchor='w', pady=(0, 8))
        except (tk.TclError, OSError):
            pass
        text(logo, 'wubuGO', 27, 'bold', C['gold']).pack(anchor='w')
        text(logo, '2016  /  MOD STUDIO', 11, 'bold').pack(anchor='w', pady=(0, 8))
        text(logo, f'OFFLINE-FIRST  /  {VERSION}', 8, fg=C['muted']).pack(anchor='w')
        tk.Frame(self.side, height=1, bg=C['line']).pack(fill='x', padx=19, pady=(1, 16))
        text(self.side, 'WORKSPACE', 9, 'bold', C['muted']).pack(anchor='w', padx=23, pady=(3, 9))
        self.nav_buttons = {}
        for index, page in enumerate(('Overview', 'Setup', 'Weapons', 'Classic UI', 'Launch', 'Downloads', 'Settings', 'Integrity', 'Diagnostics'), 1):
            b = tk.Button(self.side, text=f'  {index:02d}    {page}', anchor='w',
                          command=lambda name=page: self.show_page(name),
                          bg=C['sidebar'], fg=C['muted'], font=(FONT, 11),
                          relief='flat', bd=0, pady=8, padx=18,
                          activebackground=C['panel2'], activeforeground=C['text'],
                          highlightthickness=0, cursor='hand2')
            b.pack(fill='x', padx=9, pady=2)
            self.nav_buttons[page] = b
        tk.Frame(self.side, bg=C['sidebar']).pack(fill='both', expand=True)
        tk.Frame(self.side, bg=C['line'], height=1).pack(fill='x', padx=19)
        lower = tk.Frame(self.side, bg=C['sidebar'], padx=23, pady=18)
        lower.pack(fill='x')
        text(lower, 'STEAM CLIENT', 8, 'bold', C['muted']).pack(anchor='w')
        self.side_state = text(lower, 'NOT DETECTED', 10, 'bold', C['red'])
        self.side_state.pack(anchor='w', pady=(6, 4))
        text(lower, 'Offline / -insecure only', 9, fg=C['muted']).pack(anchor='w')
        self.right = tk.Frame(self, bg=C['bg'])
        self.right.pack(side='left', fill='both', expand=True)
        header = tk.Frame(self.right, bg=C['bg'], pady=23, padx=30)
        header.pack(fill='x')
        title_area = tk.Frame(header, bg=C['bg'])
        title_area.pack(side='left', fill='x', expand=True)
        text(title_area, 'COUNTER-STRIKE   /   wubuGO 2016', 16, 'bold').pack(anchor='w')
        self.path_label = text(title_area, '', 9, fg=C['muted'])
        self.path_label.pack(anchor='w', pady=(8, 0))
        button(header, 'CHANGE GAME FOLDER', self.choose_game, small=True).pack(side='right')
        tk.Frame(self.right, bg=C['line'], height=1).pack(fill='x')
        self.scroll = tk.Canvas(self.right, bg=C['bg'], highlightthickness=0, bd=0)
        self.scroll.pack(side='top', fill='both', expand=True)
        self.scrollbar = ttk.Scrollbar(self.right, orient='vertical', command=self.scroll.yview)
        self.scroll.configure(yscrollcommand=self.scrollbar.set)
        self.scrollbar.pack(side='right', fill='y', before=self.scroll)
        self.content = tk.Frame(self.scroll, bg=C['bg'])
        self.content_id = self.scroll.create_window((0, 0), window=self.content, anchor='nw')
        self.content.bind('<Configure>', lambda e: self.scroll.configure(scrollregion=self.scroll.bbox('all')))
        self.scroll.bind('<Configure>', lambda e: self.scroll.itemconfigure(self.content_id, width=e.width))
        self.scroll.bind('<MouseWheel>', self._wheel)
        self.content.bind('<MouseWheel>', self._wheel)
        self.scroll.bind_all('<Button-4>', lambda e:self.scroll.yview_scroll(-3,'units'))
        self.scroll.bind_all('<Button-5>', lambda e:self.scroll.yview_scroll(3,'units'))
        self.footer = tk.Frame(self.right, bg=C['sidebar'], padx=29, pady=12)
        self.footer.pack(side='bottom', fill='x')
        self.busy_label = text(self.footer, 'READY', 9, 'bold', C['green'])
        self.busy_label.pack(side='left')
        self.task_progress = ttk.Progressbar(self.footer, mode='determinate', length=100)
        self.task_progress.pack(side='left', padx=12)
        self.message = text(self.footer, 'wubuGO 2016 · offline-first', 9, fg=C['muted'])
        self.message.pack(side='right')
        self._refresh_top()

    def _wheel(self, e):
        self.scroll.yview_scroll(int(-1 * (e.delta / 120)), 'units')

    def _refresh_top(self):
        if self.game:
            self.side_state.configure(text='SOURCE 1 FOUND', fg=C['green'])
            self.path_label.configure(text=str(self.game))
        else:
            self.side_state.configure(text='NOT DETECTED', fg=C['red'])
            self.path_label.configure(text='Choose your Source 1 game folder (csgo.exe or native Linux executable)')

    def _log(self, info):
        from datetime import datetime
        msg = f'{datetime.now():%H:%M:%S}  {info}'
        self.log_history.append(msg)
        self.log_history = self.log_history[-150:]
        if getattr(self, 'log_text', None) is not None and self.log_text.winfo_exists():
            self.log_text.configure(state='normal')
            self.log_text.insert('end', msg + '\n')
            self.log_text.see('end')
            self.log_text.configure(state='disabled')
        if hasattr(self, 'message'):
            self.message.configure(text=info[:110])

    def _task(self, name, fn):
        if self.working:
            return
        self.working = True
        self.active_operation = {'name': name, 'status': 'running'}
        self.operations.append(self.active_operation)
        self.operations = self.operations[-50:]
        atomic_json(STATE / 'operations.json', {'operations': self.operations})
        self.task_progress.configure(mode='indeterminate');self.task_progress.start(15)
        self.busy_label.configure(text='WORKING  •', fg=C['gold'])
        self._log(name + '...')
        if self.page == 'Downloads':
            self.show_page('Downloads')

        def runner():
            try:
                result = fn()
                self.events.put(('done', name, result))
            except Exception as exc:
                self.events.put(('error', name, str(exc)))
        threading.Thread(target=runner, daemon=True).start()

    def _drain(self):
        try:
            while True:
                kind, name, result = self.events.get_nowait()
                if kind == 'progress':
                    done,total,relative = result
                    if total:
                        self.task_progress.stop();self.task_progress.configure(mode='determinate', value=done/total*100)
                        if self.active_operation: self.active_operation['progress'] = done/total
                    self.message.configure(text=f'{done}/{total}  {relative}'[:110])
                    continue
                self.working = False
                self.task_progress.stop()
                if self.active_operation:
                    self.active_operation['status'] = 'complete' if kind == 'done' else 'failed'
                    if kind != 'done': self.active_operation['error'] = str(result)
                    atomic_json(STATE / 'operations.json', {'operations': self.operations})
                self.task_progress.configure(mode='determinate', value=100 if kind == 'done' else 0)
                self.busy_label.configure(text='READY', fg=C['green'])
                if kind == 'done':
                    self._log(f'{name} completed. {result or ""}')
                    self.show_page(self.page)
                else:
                    self._log(f'{name} failed: {result}')
                    self.show_page(self.page)
                    messagebox.showerror(name, result)
        except queue.Empty:
            pass
        self._refresh_download_rows()
        if self.game_process and self.game_process.poll() is not None:
            self.game_process = None
            if self.presence: self.presence.set_activity('In launcher')
        self.after(120, self._drain)

    def _operation_progress(self, done, total, relative):
        self.events.put(('progress', 'file progress', (done,total,relative)))

    def _require_game(self):
        if not self.game:
            raise ValueError('Select your Steam legacy CS:GO folder with CHANGE GAME FOLDER first.')
        return game_root(self.game)

    def choose_game(self):
        path = filedialog.askdirectory(title='Select Steam legacy CS:GO folder (contains csgo.exe)', initialdir=str(self.game or Path.home()))
        if not path:
            return
        try:
            self.game = game_root(path)
        except (ValueError, OSError) as exc:
            messagebox.showerror('Wrong directory', str(exc))
            return
        self.settings['game'] = str(self.game)
        self._save_settings()
        self._refresh_top()
        self._log('Steam game folder: ' + str(self.game))
        self.show_page(self.page)

    def _heading(self, eyebrow, heading, description):
        top = tk.Frame(self.content, bg=C['bg'])
        top.pack(fill='x', padx=29, pady=(29, 20))
        text(top, eyebrow.upper(), 9, 'bold', C['gold']).pack(anchor='w')
        text(top, heading, 23, 'bold').pack(anchor='w', pady=(6, 6))
        text(top, description, 10, fg=C['muted'], wraplength=850).pack(anchor='w')

    def _area(self, pad_y=(3, 15)):
        outer, inner = card(self.content)
        outer.pack(fill='x', padx=29, pady=pad_y)
        return inner

    def _labelled(self, holder, heading, detail, action=None, action_name=None, style='secondary'):
        line = tk.Frame(holder, bg=C['panel'], pady=6)
        line.pack(fill='x')
        body = tk.Frame(line, bg=C['panel'])
        body.pack(side='left', fill='x', expand=True)
        text(body, heading, 11, 'bold').pack(anchor='w')
        text(body, detail, 9, fg=C['muted'], wraplength=600).pack(anchor='w', pady=(4, 0))
        if action:
            button(line, action_name, action, style, small=True).pack(side='right', padx=(10, 0))
        return line

    def _row_buttons(self, holder, buttons):
        r = tk.Frame(holder, bg=holder.cget('bg'))
        r.pack(fill='x', pady=(14, 0))
        for label, func, style in buttons:
            button(r, label, func, style, small=True).pack(side='left', padx=(0, 9))
        return r

    def _badge(self, holder, label, positive=False):
        bg = '#17382f' if positive else '#263848'
        fg = C['green'] if positive else '#a8bbcc'
        tk.Label(holder, text=label, bg=bg, fg=fg, font=(FONT, 9, 'bold'), padx=10, pady=5).pack(anchor='w')

    def _has_source(self):
        try:
            ensure_source(OLD_SOURCE, PROJECT)
            return True
        except (ValueError, OSError):
            return False

    def _installed(self):
        if not self.game:
            return {}
        try:
            return doctor(self.game)
        except (ValueError, OSError):
            return {}

    def show_page(self, name):
        self.page = name
        self._refresh_top()
        for page, item in self.nav_buttons.items():
            item.configure(bg=C['panel2'] if page == name else C['sidebar'],
                           fg=C['text'] if page == name else C['muted'],
                           font=(FONT, 11, 'bold' if page == name else 'normal'))
        self.log_text = None
        for child in self.content.winfo_children():
            child.destroy()
        self.scroll.yview_moveto(0)
        render = {
            'Overview': self._overview, 'Weapons': self._weapons,
            'Classic UI': self._classic, 'Launch': self._launch_page,
            'Diagnostics': self._diagnostics,
            'Setup': self._setup_page, 'Downloads': self._downloads_page,
            'Settings': self._settings_page, 'Integrity': self._integrity_page,
        }
        render[name]()

    def _overview(self):
        self._heading('Project dashboard', 'Build your 2016 experience',
                      'A real Steam legacy CS:GO mod workflow. Prepare the historical weapon data, enable MIGI, then launch locally.')
        status = self._installed()
        chips = tk.Frame(self.content, bg=C['bg'])
        chips.pack(fill='x', padx=29, pady=(0, 12))
        values = [('STEAM GAME', bool(self.game)), ('2016 WEAPON DATA', self._has_source()),
                  ('MIGI INSTALLED', status.get('migi_initialized', False)),
                  ('CLASSIC HUD BRIDGE', (self.bridge_path / 'Launch.cmd').is_file())]
        for idx, (label, yes) in enumerate(values):
            block = tk.Frame(chips, bg=C['panel2'], padx=17, pady=14)
            block.grid(row=0, column=idx, sticky='ew', padx=(0, 8 if idx < 3 else 0))
            chips.columnconfigure(idx, weight=1)
            text(block, label, 8, 'bold', C['muted']).pack(anchor='w')
            text(block, 'READY' if yes else 'NEEDS SETUP', 12, 'bold', C['green'] if yes else C['gold']).pack(anchor='w', pady=(10, 0))
        hero = self._area()
        text(hero, 'QUICK SETUP', 10, 'bold', C['gold']).pack(anchor='w')
        text(hero, 'One click for the files we can install safely', 19, 'bold').pack(anchor='w', pady=(7, 8))
        text(hero, 'Uses bundled August 2016 stats (33 sourced weapons) to build an offline MIGI addon and HUD config.\nNo GitHub download required. Install MIGI separately to activate the game addon.',
             10, fg=C['muted'], wraplength=760).pack(anchor='w')
        self._row_buttons(hero, [('PREPARE WEAPONS + HUD', self.prepare_all, 'primary'),
                                  ('LAUNCH LOCAL CS:GO', self.play_vanilla, 'outline')])
        steps = self._area()
        text(steps, 'RESTORATION PIPELINE', 11, 'bold').pack(anchor='w', pady=(0, 12))
        self._labelled(steps, '01   2016 weapon tuning',
                       'Offline 1.35.4.4 snapshot: 33 sourced weapons. Optional full archive available online.',
                       lambda: self.show_page('Weapons'), 'OPEN WEAPONS')
        tk.Frame(steps, height=1, bg=C['line']).pack(fill='x', pady=10)
        self._labelled(steps, '02   Authentic-looking gameplay HUD',
                       'Use an external Panorama Bridge to show a Scaleform-style HUD inside the game.',
                       lambda: self.show_page('Classic UI'), 'OPEN UI SETUP')
        tk.Frame(steps, height=1, bg=C['line']).pack(fill='x', pady=10)
        self._labelled(steps, '03   Launch offline',
                       'Direct launch uses -insecure, sv_lan 1 and a local map. External injection remains unverified.',
                       lambda: self.show_page('Launch'), 'OPEN LAUNCHER')

    def _weapons(self):
        self._heading('Weapon workshop', 'August 2016 weapon balance',
                      'The bundled 33-weapon 1.35.4.4 snapshot needs no download. Runtime effects remain unverified.')
        s = self._area()
        self._badge(s, '2016 DATA  •  ' + ('OFFLINE READY' if self._has_source() else 'MISSING FILE'), self._has_source())
        text(s, '03 AUG 2016  •  CS:GO 1.35.4.4', 17, 'bold').pack(anchor='w', pady=(12, 6))
        text(s, 'The offline bundle contains 33 sourced weapon records with sourced attribute values. It does not overwrite the remaining weapons. The full historical snapshot is bundled; fetching online is optional.',
             10, fg=C['muted'], wraplength=760).pack(anchor='w')
        self._row_buttons(s, [('GENERATE OFFLINE ADDON', self.generate_weapons, 'primary'),
                              ('FETCH COMPLETE ARCHIVE (OPTIONAL)', self.get_2016_source, 'secondary'),
                              ('OPEN SOURCE LINK', lambda: webbrowser.open(SOURCES[0]), 'outline')])
        s = self._area()
        text(s, 'MIGI INSTALLATION', 12, 'bold').pack(anchor='w')
        info = self._installed()
        self._badge(s, 'MIGI ' + ('INITIALISED' if info.get('migi_initialized') else 'NOT INITIALISED'), info.get('migi_initialized', False))
        text(s, 'Installing the addon does not automatically update MIGI’s VPK. Click Build / Update Build in MIGI after installation.',
             10, fg=C['muted'], wraplength=750).pack(anchor='w', pady=(9, 0))
        self._row_buttons(s, [('INSTALL WEAPON ADDON', self.install_weapons, 'primary'),
                              ('OPEN MIGI', self.open_migi, 'secondary'),
                              ('GET MIGI3', lambda: webbrowser.open('https://github.com/ZooLSmith/MIGI3'), 'outline')])
        report = ADDON_ROOT / 'weapon_report.json'
        if report.is_file():
            s = self._area()
            data = json.loads(report.read_text(encoding='utf-8'))
            text(s, f'GENERATED BALANCE  •  {len(data.get("weapons", {}))} WEAPONS', 12, 'bold').pack(anchor='w')
            text(s, 'Sample attribute values from the parsed historical file:', 9, fg=C['muted']).pack(anchor='w', pady=(7, 10))
            for weapon, details in list(data.get('weapons', {}).items())[:8]:
                attrs = details['attributes']
                snippet = '  |  '.join(f'{key}: {attrs[key]}' for key in ('damage','armor ratio','in game price','cycletime') if key in attrs)
                self._labelled(s, weapon.replace('weapon_', '').upper(), snippet)
        s = self._area()
        text(s, 'PREVIOUSLY UPLOADED FILE', 10, 'bold', C['gold']).pack(anchor='w')
        text(s, 'The earlier attachment is preserved but is not used to build 2016 gameplay stats. It contains post-2016 events and lacks weapon_* item entries.',
             10, fg=C['muted'], wraplength=770).pack(anchor='w', pady=(8, 0))
        self._row_buttons(s, [('AUDIT UPLOAD', self.audit_user_file, 'outline')])

    def _classic(self):
        self._heading('Scaleform-style in-game UI', '2016 HUD + main menu',
                      'The 2023-era Source 1 client uses Panorama. Bridge is intended to load a classic-looking archive in-game (unverified here); it cannot restore the original Scaleform runtime.')
        s = self._area()
        text(s, 'PANORAMA BRIDGE', 12, 'bold').pack(anchor='w')
        detected = (self.bridge_path / 'Setup.cmd').is_file()
        self._badge(s, 'BRIDGE ' + ('PRESENT' if detected else 'NOT DOWNLOADED'), detected)
        text(s, 'Source: wallbangs/panorama-bridge-csgo. This third-party loader uses a Windows x86 injector and is intended exclusively for local / -insecure play.',
             10, fg=C['muted'], wraplength=770).pack(anchor='w', pady=(10, 0))
        self._row_buttons(s, [('IMPORT BRIDGE ZIP (OFFLINE)', self.import_bridge_zip, 'primary'),
                              ('DOWNLOAD BRIDGE', self.get_bridge, 'secondary'),
                              ('SELECT EXISTING', self.select_bridge, 'outline'),
                              ('OPEN GITHUB', lambda: webbrowser.open('https://github.com/wallbangs/panorama-bridge-csgo'), 'outline')])
        s = self._area()
        text(s, 'IN-GAME HUD SETUP', 12, 'bold').pack(anchor='w')
        self._labelled(s, '1   Run the guided setup',
                       'Opens the Bridge folder and dependency inventory. Setup scripts are not executed automatically.')
        self._labelled(s, '2   Build MIGI',
                       'Open MIGI and use Build / Update Build so the HUD assets are included.')
        self._labelled(s, '3   Runtime verification required',
                       'Automatic Bridge launch is disabled until injection and private-session enforcement are verified.')
        from modkit.bridge_manager import dependency_catalog
        for dep in dependency_catalog()['dependencies']:
            self._row_buttons(s, [('DOWNLOAD ' + dep['name'].upper(),
                lambda d=dep:self.queue_download(d['url'],d['filename'],'dependency',d['sha256']), 'outline')])
        if os.name != 'nt':
            text(s, 'Windows injector only: native Fedora Bridge/MIGI injection is unsupported.', 10, fg=C['gold'], wraplength=770).pack(anchor='w', pady=10)
        self._row_buttons(s, [('MANUAL SETUP / DEPENDENCIES', self.run_bridge_setup, 'primary'),
                              ('OPEN MIGI', self.open_migi, 'secondary'),
                              ('PLAY WITH CLASSIC HUD', self.play_bridge, 'outline')])
        s = self._area()
        text(s, '2016-INSPIRED HOME MENU', 12, 'bold').pack(anchor='w')
        text(s, 'Patches a locally generated panorama.my.zip with retro menu styling and local-map buttons and navigation to Inventory, Watch, Stats and Settings (unverified).\nKeeps the original ZIP for rollback; compatibility depends on your UI revision.',
             10, fg=C['muted'], wraplength=760).pack(anchor='w', pady=(9, 0))
        self._row_buttons(s, [('APPLY MENU PATCH', self.patch_bridge_menu, 'primary'),
                              ('RESTORE PREVIOUS MENU', self.restore_bridge_menu, 'outline')])
        text(s, f'Bridge folder: {self.bridge_path}', 9, fg=C['muted'], wraplength=760).pack(anchor='w', pady=(14, 0))

    def _launch_page(self):
        self._heading('Game launcher', 'Start CS:GO',
                      'Launches the genuine Steam csgo.exe. Never launches a dummy server or a mock game.')
        s = self._area()
        text(s, 'BASE GAME', 13, 'bold').pack(anchor='w')
        text(s, 'Works without MIGI. Always starts with -insecure -steam -console. Steam must be running.',
             10, fg=C['muted']).pack(anchor='w', pady=(8, 12))
        self._row_buttons(s, [('PLAY CS:GO', self.play_vanilla, 'primary'),
                              ('PLAY DUST II WITH BOTS', lambda: self.play_vanilla('de_dust2'), 'secondary'),
                              ('PLAY MIRAGE WITH BOTS', lambda: self.play_vanilla('de_mirage'), 'outline'),
                              ('SAFE LOCAL LAUNCH', self.steam_fallback, 'outline')])
        s = self._area()
        text(s, '2016 MODDED GAME', 13, 'bold').pack(anchor='w')
        text(s, 'MIGI mode requires MIGI to be initialised and its Build / Update Build step completed.\nFor the classic in-game HUD, the third-party Bridge must also be compatible with your exact client.',
             10, fg=C['muted'], wraplength=760).pack(anchor='w', pady=(8, 12))
        self._row_buttons(s, [('PLAY VIA MIGI', self.play_migi, 'primary'),
                              ('PLAY VIA BRIDGE / CLASSIC HUD', self.play_bridge, 'secondary')])
        self._row_buttons(s, [('RESTORE HUD PROFILE', self.rollback_profile, 'outline'),
                              ('RESTORE WEAPON ADDON', self.rollback_weapons, 'outline')])
        s = self._area()
        text(s, 'LAUNCH OPTIONS', 12, 'bold').pack(anchor='w')
        text(s, 'Custom launch parameters are intentionally restricted: this manager only launches insecure/local testing sessions.\nSteam secure matchmaking is not supported when using modified UI or MIGI assets.',
             10, fg=C['muted'], wraplength=760).pack(anchor='w', pady=(8, 0))

    def _diagnostics(self):
        self._heading('System diagnostics', 'Installation details + logs',
                      'The actual status of your local Steam installation and project files, with plain-English fixes.')
        s = self._area()
        self._row_buttons(s, [('REFRESH CHECKS', lambda: self.show_page('Diagnostics'), 'primary'),
                              ('OPEN GAME FOLDER', self.open_game_folder, 'outline'),
                              ('OPEN PROJECT FOLDER', lambda: self.open_folder(PROJECT), 'outline')])
        info = self._installed()
        integrity = verify_assets(PROJECT)
        for heading, value in [('Offline asset checksums', integrity['ok']),
                               ('Steam game detected', bool(self.game)),
                               ('Standalone manifest', info.get('standalone_manifest_found', False)),
                               ('2016 stats bundled / cached', self._has_source()),
                               ('MIGI executable exists', info.get('migi_exe_exists', False)),
                               ('MIGI initialised', info.get('migi_initialized', False)),
                               ('Classic HUD config', info.get('hud_cfg_installed', False)),
                               ('Weapon addon installed', info.get('weapon_addon_installed', False)),
                               ('Bridge installed', (self.bridge_path / 'Launch.cmd').is_file()),
                               ('Bridge archive built', (self.bridge_path / 'panorama.my.zip').is_file()),
                               ('2016 menu backup', (self.bridge_path / 'panorama.my.zip.wubugo.bak').is_file())]:
            r = tk.Frame(s, bg=C['panel'], pady=3)
            r.pack(fill='x')
            text(r, heading, 10).pack(side='left')
            text(r, 'PASS' if value else 'NOT YET', 9, 'bold', C['green'] if value else C['gold']).pack(side='right')
        s = self._area()
        if not integrity['ok']:
            text(s, 'Bundled files missing/changed: ' + ' | '.join(integrity['failures'][:3]), 9, fg=C['red'], wraplength=740).pack(anchor='w', pady=6)
        text(s, 'ACTIVITY LOG', 12, 'bold').pack(anchor='w', pady=(0, 10))
        self.log_text = tk.Text(s, height=12, bg=C['deep'], fg='#b8cedd', insertbackground='white',
                                font=('Consolas' if sys.platform == 'win32' else 'DejaVu Sans Mono', 9),
                                wrap='word', relief='flat', padx=12, pady=12, state='normal')
        self.log_text.pack(fill='both', expand=True)
        self.log_text.insert('1.0', '\n'.join(self.log_history) + '\n')
        self.log_text.configure(state='disabled')
        self._row_buttons(s, [('SAVE LOG', self.save_log, 'outline')])

    # --- Working actions ---
    def get_2016_source(self):
        self.queue_download(SOURCES[0], 'weapons-1.35.4.4.json', 'weapons')

    def generate_weapons(self):
        def action():
            source, source_info = ensure_source(OLD_SOURCE, PROJECT)
            addon, report, n = create_2016_addon(source, ADDON_ROOT)
            return f'Generated {n} weapon overrides at {addon}; report: {report.name}.'
        self._task('Build historical weapon addon', action)

    def prepare_all(self):
        def action():
            root = self._require_game()
            source, source_info = ensure_source(OLD_SOURCE, PROJECT)
            addon, _, n = create_2016_addon(source, ADDON_ROOT)
            cfg = install_profile(root)
            if (root / 'migi.exe').is_file() and (root / 'migi/csgo/gameinfo.txt').is_file():
                dst = install_addon(root, addon, replace=True)
                return f'Prepared {n} weapons, HUD profile, and MIGI addon at {dst}. Open MIGI > Build / Update Build.'
            return f'Prepared {n} weapon overrides and {cfg.name}. Install/initialise MIGI3 before deploying the addon.'
        self._task('Prepare 2016 setup', action)

    def install_weapons(self):
        def action():
            root = self._require_game()
            addon = ADDON_ROOT / 'm_wubugo_2016'
            if not (addon / 'scripts/items/items_game_wubugo_2016.txt').is_file():
                source, source_info = ensure_source(OLD_SOURCE, PROJECT)
                create_2016_addon(source, ADDON_ROOT)
            dst = install_addon(root, addon, replace=True)
            return f'Installed at {dst}. Required next action: Build / Update Build in MIGI.'
        self._task('Install MIGI weapon addon', action)

    def audit_user_file(self):
        if not USER_SOURCE.exists():
            messagebox.showinfo('File missing', 'Previous upload was not bundled. Download the 2016 source instead.')
        else:
            a = audit(USER_SOURCE)
            messagebox.showinfo('Audit of earlier upload',
                                f'Item entries: {a["total_items"]}\nWeapon definitions: {a["weapon_item_count"]}\nPost-2016 markers: {", ".join(a["post_2016_markers"])}\n\n' +
                                'This is a newer economy file and cannot supply the 2016 weapon behaviour. Use the bundled weapon data instead.')

    def open_folder(self, location):
        p = Path(location)
        if not p.exists():
            messagebox.showerror('Folder missing', str(p))
            return
        if os.name == 'nt':
            os.startfile(str(p))
        else:
            subprocess.Popen(['xdg-open', str(p)])

    def open_game_folder(self):
        try:
            self.open_folder(self._require_game())
        except ValueError as exc:
            messagebox.showerror('Game missing', str(exc))

    def open_migi(self):
        try:
            root = self._require_game()
            exe = root / 'migi.exe'
            if not exe.is_file():
                raise ValueError('MIGI is not installed. Use GET MIGI3 to download the official app and place migi.exe next to csgo.exe.')
            if os.name != 'nt':
                raise ValueError('MIGI3 is a Windows executable; open it on Windows.')
            subprocess.Popen([str(exe)], cwd=str(root))
            self._log('Opened MIGI. Click Build / Update Build after changing addons.')
        except (ValueError, OSError) as exc:
            messagebox.showerror('MIGI', str(exc))

    def _launch_game(self, migi=False, map_name=None):
        try:
            root = self._require_game()
            if self.game_process and self.game_process.poll() is None:
                raise ValueError('The game launched by wubuGO is still running.')
            extra = ['+map', map_name] if map_name else []
            child = launch(root, use_migi=migi, extra=extra, proton=self.settings.get('proton') or None)
            self.game_process = child
            if self.presence: self.presence.set_activity('Playing a local game', 'Offline / private · -insecure')
            self._log(f'Launched Steam CS:GO (PID {child.pid})' + (' with MIGI.' if migi else '.'))
        except (ValueError, OSError) as exc:
            messagebox.showerror('Could not launch CS:GO', str(exc))

    def play_vanilla(self, map_name=None):
        self._launch_game(False, map_name if isinstance(map_name, str) else None)

    def steam_fallback(self):
        self._launch_game(False, 'de_dust2')

    def rollback_profile(self):
        from modkit.recovery import restore_profile
        self._task('Restore HUD profile', lambda: str(restore_profile(self._require_game())))

    def rollback_weapons(self):
        from modkit.recovery import restore_addon
        self._task('Restore weapon addon', lambda: str(restore_addon(self._require_game())) +
                   '; rebuild MIGI before launching.')

    def play_migi(self):
        try:
            root = self._require_game()
            if not (root / 'migi/csgo/addons/m_wubugo_2016').is_dir():
                raise ValueError('Historical addon not installed. Go to WEAPONS > INSTALL WEAPON ADDON.')
            if not messagebox.askyesno('MIGI build check', 'Did you click Build / Update Build inside MIGI after installing the weapon addon?\n\nContinue with -insecure?'):
                return
            self._launch_game(True)
        except (ValueError, OSError) as exc:
            messagebox.showerror('MIGI is not ready', str(exc))

    def select_bridge(self):
        p = filedialog.askdirectory(title='Select the existing Panorama Bridge folder containing Launch.cmd')
        if not p:
            return
        folder = Path(p)
        if not (folder / 'Launch.cmd').is_file():
            messagebox.showerror('Wrong folder', 'Expected a folder containing Launch.cmd from Panorama Bridge.')
            return
        self.bridge_path = folder
        self.settings['bridge'] = str(folder)
        self._save_settings()
        self._log('Selected Bridge folder: ' + str(folder))
        self.show_page(self.page)

    def get_bridge(self):
        from modkit.bridge_manager import URL
        self.queue_download(URL, 'panorama-bridge-source.zip', 'bridge')

    def run_bridge_setup(self):
        try:
            if os.name != 'nt':
                raise ValueError('Bridge setup runs on Windows and requires a compatible 32-bit CS:GO client.')
            self._require_game()
            script = self.bridge_path / 'Setup.cmd'
            if not script.is_file():
                raise ValueError('Bridge Setup.cmd missing. Import an existing Bridge folder or ZIP first.')
            from modkit.bridge_manager import inspect_bridge
            report = inspect_bridge(self.bridge_path, game_folder=self.game, downloads_folder=self.download_manager.directory)
            messagebox.showinfo('Manual Bridge setup',
                'Bridge imported. Setup is not run automatically because its downloads and Steam writes '
                'are outside wubuGO backup control. Review Setup.cmd and supply its dependencies locally. '
                'The source ZIP alone is not an offline dependency bundle.\n\n' + str(report))
            self.open_folder(self.bridge_path)
        except (ValueError, OSError) as exc:
            messagebox.showerror('Bridge setup', str(exc))

    def import_bridge_zip(self):
        path = filedialog.askopenfilename(title='Select Panorama Bridge GitHub source ZIP',
                                          filetypes=[('ZIP archive', '*.zip')])
        if not path:
            return
        from modkit.bridge_manager import import_bridge_archive
        self._task('Import Bridge ZIP (offline)', lambda: str(import_bridge_archive(Path(path), self.bridge_path)))

    def patch_bridge_menu(self):
        def action():
            dest, backup = install_to_bridge(self.bridge_path)
            return f'Updated {dest.name}; rollback is {backup.name}.'
        self._task('Patch in-game home menu', action)

    def restore_bridge_menu(self):
        def action():
            dest = restore_bridge(self.bridge_path)
            return f'Restored {dest.name} from the backup.'
        self._task('Restore previous in-game menu', action)

    def play_bridge(self):
        try:
            if os.name != 'nt':
                raise ValueError('Bridge works on Windows x86 legacy CS:GO; use Windows.')
            self._require_game()
            script = self.bridge_path / 'Launch.cmd'
            if not script.is_file():
                raise ValueError('Bridge not installed. Go to CLASSIC UI to download and configure it.')
            raise ValueError('External Bridge launch is disabled: this script has not been verified to '
                             'enforce -insecure and offline/private play. Use the direct offline launcher '
                             'for local tests. In-game Bridge HUD/menu remains unverified.')
        except (ValueError, OSError) as exc:
            messagebox.showerror('Bridge launch unavailable', str(exc))

    def save_log(self):
        p = filedialog.asksaveasfilename(defaultextension='.txt', filetypes=[('Text log', '*.txt')])
        if p:
            Path(p).write_text('\n'.join(self.log_history) + '\n', encoding='utf-8')
            self._log('Saved log: ' + str(p))


def main():
    if len(sys.argv) == 3 and sys.argv[1] == '--self-test':
        from .healthcheck import run
        raise SystemExit(run(sys.argv[2]))
    app = Studio()
    app.mainloop()


if __name__ == '__main__':
    main()
