"""Setup, download activity, settings and integrity pages for the existing Tk GUI."""
from __future__ import annotations
import json
import os
import shutil
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import ttk, filedialog, messagebox
import webbrowser
from .runtime import (VERSION, state_root, atomic_json, DEFAULT_UPDATE_MANIFEST,
                      DEFAULT_UPDATE_HOSTS)

class ExtraPages:
    def _setup_page(self):
        from .app import text, C
        from modkit.asset_integrity import verify_assets
        from modkit.sources import offline_source, validate_2016
        from .runtime import resource_root
        self._heading('First run', 'Set up your workspace',
                      'Bundled runtime builds run without a separate Python install. Steam owns and downloads the game.')
        s=self._area()
        report=verify_assets(resource_root())
        try:
            source=validate_2016(offline_source(resource_root()))
            source_note=f'{source["weapon_item_count"]} historical weapon records available offline'
        except (OSError,ValueError):
            source_note='Historical source unavailable'
        checks=[('Bundled asset checksums', 'PASS' if report['ok'] else 'FAILED'),
                ('Historical weapon source', source_note),
                ('Game folder', str(self.game) if self.game else 'Choose your existing Steam Source 1 installation'),
                ('Platform', 'Windows' if os.name=='nt' else 'Linux / Fedora'),
                ('App data / downloads', str(state_root())),
                ('In-game HUD / menu', 'Unverified; external Bridge required on Windows')]
        for title,detail in checks:
            self._labelled(s,title,detail)
        self._row_buttons(s,[('PREPARE OFFLINE ASSETS',self.generate_weapons,'primary'),
                             ('CHOOSE GAME',self.choose_game,'secondary'),
                             ('INSTALL GAME IN STEAM',lambda:webbrowser.open('steam://install/4465480'),'outline')])
        s=self._area()
        text(s,'WHAT IS INCLUDED',12,'bold').pack(anchor='w')
        text(s,'The launcher, historical data, addon generator, preferences, backups, download manager and optional Discord IPC.\n'
               'Steam, the game, MIGI, Bridge injection tools and Proton are separate installations. No network requests happen at startup.\n'
               'Fedora can launch a native Source 1 client or use a locally installed Proton selected in Settings.\n'
               'MIGI/Bridge injection on Linux remains unsupported. No secure matchmaking with mods.',
             10,fg=C['muted'],wraplength=790).pack(anchor='w',pady=(10,0))
        self._row_buttons(s,[('PREPARE GAME PROFILE',self.prepare_all,'primary'),
                             ('OPEN SETTINGS',lambda:self.show_page('Settings'),'outline')])

    def _downloads_page(self):
        from .app import text, C
        self._heading('Downloads + installations','Your files, visible at every step',
                      'Downloads stay in Downloads/.partial until complete. Nothing downloaded is executed automatically.')
        s=self._area()
        text(s,str(self.download_manager.directory),10,fg=C['gold']).pack(anchor='w')
        self._row_buttons(s,[('OPEN DOWNLOADS',lambda:self.open_folder(self.download_manager.directory),'primary'),
                             ('CHECK APP UPDATE',self.check_app_update,'outline')])
        jobs=self.download_manager.jobs()
        if not jobs:
            text(s,'No downloads yet. Bundled assets need no download.',10,fg=C['muted']).pack(anchor='w',pady=(12,0))
        self.download_widgets={}
        for job in reversed(jobs):
            box=self._area()
            text(box,job['filename'],12,'bold').pack(anchor='w')
            status=text(box,'',9,fg=C['muted'],wraplength=790);status.pack(anchor='w',pady=(6,0))
            bar=ttk.Progressbar(box,mode='determinate',maximum=100)
            bar.pack(fill='x',pady=10)
            self.download_widgets[job['id']]=(status,bar)
            self._row_buttons(box,[('CANCEL',lambda jid=job['id']:self.download_manager.cancel(jid),'outline'),
                                   ('USE COMPLETED FILE',lambda jid=job['id']:self.use_download(jid),'secondary')])
        s=self._area()
        text(s,'INSTALL / BUILD ACTIVITY',12,'bold').pack(anchor='w')
        self.operation_widgets=[]
        for operation in reversed(self.operations[-15:]):
            text(s,operation['name']+' — '+operation['status'],10).pack(anchor='w',pady=(10,2))
            bar=ttk.Progressbar(s,maximum=100,mode='indeterminate' if operation['status']=='running' else 'determinate')
            bar.pack(fill='x',pady=3)
            if operation['status']=='running': bar.start(15)
            elif operation['status']=='complete': bar['value']=100
            if operation.get('error'): text(s,operation['error'],9,fg=C['red'],wraplength=770).pack(anchor='w')
            self.operation_widgets.append((operation,bar))
        self._refresh_download_rows()

    def _refresh_download_rows(self):
        if self.page!='Downloads': return
        for operation,bar in getattr(self,'operation_widgets',[]):
            if bar.winfo_exists() and operation.get('status') == 'running' and 'progress' in operation:
                bar.stop();bar.configure(mode='determinate',value=operation['progress']*100)
        for job in self.download_manager.jobs():
            widgets=self.download_widgets.get(job['id'])
            if not widgets: continue
            label,bar=widgets
            if not label.winfo_exists(): continue
            total=job.get('total')
            downloaded=job.get('downloaded',0)
            size=f'{downloaded/1048576:.1f} MiB / {total/1048576:.1f} MiB' if total else f'{downloaded/1048576:.1f} MiB / unknown size'
            label.configure(text=f'{job["status"].upper()}  •  {size}  •  SHA-256: {"verified" if job.get("sha256_verified") else "not verified"}\n'
                                 f'Temporary: {job.get("temporary_path", "")}\n'
                                 f'{job.get("error") or job.get("path") or ""}')
            progress=job.get('progress')
            if progress is None and job['status'] in {'queued','downloading','verifying'}:
                if str(bar.cget('mode'))!='indeterminate':
                    bar.configure(mode='indeterminate');bar.start(15)
            else:
                bar.stop();bar.configure(mode='determinate')
                bar['value']=(progress or 0)*100

    def queue_download(self,url,filename,kind,sha256=None):
        try:
            jid=self.download_manager.submit(url,filename,expected_sha256=sha256)
            self.settings.setdefault('download_kinds',{})[jid]=kind
            self._save_settings()
            self.show_page('Downloads')
        except (ValueError,OSError) as exc: messagebox.showerror('Download',str(exc))

    def use_download(self,jid):
        from .app import OLD_SOURCE, ADDON_ROOT
        from modkit.sources import validate_2016
        from modkit.weapon_balance import create_2016_addon
        from modkit.bridge_manager import import_bridge_archive
        jobs={j['id']:j for j in self.download_manager.jobs()}
        job=jobs.get(jid)
        if not job or job['status']!='complete':
            messagebox.showinfo('Download not ready','Wait for completion before using this file.');return
        kind=self.settings.get('download_kinds',{}).get(jid)
        path=Path(job['path'])
        if kind=='bridge':
            self._task('Import downloaded Bridge',lambda:str(import_bridge_archive(path,self.bridge_path)))
        elif kind=='weapons':
            def action():
                validate_2016(path)
                # Keep the downloaded source as the explicit selected source, not a replaced bundled file.
                addon,report,n=create_2016_addon(path,ADDON_ROOT)
                return f'Generated {n} sourced weapons at {addon}'
            self._task('Validate historical source + generate addon',action)
        elif kind == 'dependency':
            self.open_folder(path.parent)
            messagebox.showinfo('Dependency cached', 'Checksum: ' + ('verified' if job.get('sha256_verified') else 'not verified') +
                                '. The payload is cached only. See Classic UI for the manual Bridge dependency inventory. Nothing has been installed or run.')
        else:
            self.open_folder(path.parent)
            messagebox.showinfo('Update staged','The file is staged only. Close wubuGO and use the platform installer. Backups and settings stay in your app-data directory.')

    def check_app_update(self):
        from modkit.downloads import check_update
        url=self.settings.get('update_manifest',DEFAULT_UPDATE_MANIFEST).strip()
        if not url:
            messagebox.showinfo('Update checks disabled',
                'Set a trusted HTTPS release manifest in Settings to enable explicit update checks. The default feed is the wubuGO GitHub repository.');return
        def action():
            from urllib.parse import urlsplit
            hosts={urlsplit(url).hostname} | {h.strip() for h in self.settings.get('update_hosts',DEFAULT_UPDATE_HOSTS).split(',') if h.strip()}
            release=check_update(url,current_version=VERSION,trusted_hosts=hosts)
            atomic_json(state_root()/'available-update.json',release)
            return 'Release metadata saved. Use STAGE AVAILABLE UPDATE to download it; no code is run.'
        self._task('Check configured update source',action)

    def stage_app_update(self):
        from modkit.downloads import stage_update
        from .runtime import load_settings
        release=load_settings(state_root()/'available-update.json')
        if not release:
            self.check_app_update();return
        try:
            stage_update(self.download_manager,release,'windows-x64' if os.name=='nt' else 'linux-x64')
            self.show_page('Downloads')
        except (ValueError,OSError,KeyError) as exc: messagebox.showerror('Stage update',str(exc))

    def _settings_page(self):
        from .app import text,C
        from modkit.game_settings import DEFAULTS,LIMITS
        self._heading('Preferences','Make it yours','Settings are stored in your user data directory and survive app upgrades.')
        s=self._area()
        text(s,'GAME PREFERENCES',12,'bold').pack(anchor='w')
        text(s,'Values below are proposed preferences. Save installs them; restoring an original external cfg leaves its contents intact.',
             9,fg=C['muted'],wraplength=780).pack(anchor='w',pady=(8,8))
        self.pref_entries={}
        for key,default in DEFAULTS.items():
            row=tk.Frame(s,bg=C['panel']);row.pack(fill='x',pady=4)
            low,high=LIMITS[key]
            text(row,f'{key}  ({low}–{high})',10).pack(side='left')
            entry=tk.Entry(row,bg=C['deep'],fg=C['text'],insertbackground=C['text'],width=16)
            entry.insert(0,str(self.settings.get('preferences',{}).get(key,default)));entry.pack(side='right')
            self.pref_entries[key]=entry
        self._row_buttons(s,[('SAVE + INSTALL PREFERENCES',self.save_preferences,'primary'),
                             ('RESTORE PREVIOUS PREFERENCES',self.restore_preferences,'outline')])
        s=self._area()
        text(s,'LAUNCHER + OPTIONAL SERVICES',12,'bold').pack(anchor='w')
        self.service_entries={}
        for key,label in [('proton','Proton executable (Linux, optional)'),
                          ('discord_client_id','Discord application ID (app name must be wubuGO)'),
                          ('update_manifest','Trusted HTTPS update manifest (optional)'),
                          ('update_hosts','Additional trusted update asset hosts, comma-separated (optional)')]:
            text(s,label,10).pack(anchor='w',pady=(12,4))
            entry=tk.Entry(s,bg=C['deep'],fg=C['text'],insertbackground=C['text'])
            default = DEFAULT_UPDATE_MANIFEST if key == 'update_manifest' else DEFAULT_UPDATE_HOSTS if key == 'update_hosts' else ''
            entry.insert(0,self.settings.get(key,default));entry.pack(fill='x');self.service_entries[key]=entry
        self.discord_enabled=tk.BooleanVar(value=bool(self.settings.get('discord_enabled',False)))
        tk.Checkbutton(s,text='Enable Discord rich presence (opt in)',variable=self.discord_enabled,
                       bg=C['panel'],fg=C['text'],selectcolor=C['deep'],activebackground=C['panel']).pack(anchor='w',pady=12)
        text(s,'Discord controls the displayed application name. Create an application named exactly wubuGO in the Discord Developer Portal,\n'
               'then paste its public Application ID here. No account token or password is needed. Discord must be running locally.',
             9,fg=C['muted'],wraplength=780).pack(anchor='w')
        self._row_buttons(s,[('SAVE LAUNCHER SETTINGS',self.save_services,'primary'),
                             ('STAGE AVAILABLE UPDATE',self.stage_app_update,'outline')])
        status=getattr(self.presence,'status','Disabled') if self.presence else 'Disabled'
        text(s,'Rich presence: '+str(status),9,fg=C['muted']).pack(anchor='w',pady=(10,0))

    def save_preferences(self):
        from modkit.game_settings import validate_settings,install_settings
        try:
            values=validate_settings({key:entry.get() for key,entry in self.pref_entries.items()})
            root=self._require_game()
        except (ValueError,OSError) as exc: messagebox.showerror('Preferences',str(exc));return
        def action():
            path=install_settings(root,values)
            self.settings['preferences']=values;self._save_settings()
            return str(path)
        self._task('Install game preferences',action)

    def restore_preferences(self):
        from modkit.game_settings import rollback_settings, read_installed_settings
        try: root=self._require_game()
        except (ValueError,OSError) as exc: messagebox.showerror('Preferences',str(exc));return
        def action():
            path=rollback_settings(root)
            restored=read_installed_settings(root)
            if restored is None:
                self.settings.pop('preferences',None)
                note='Original or absent preferences restored; proposed launcher values reset to defaults.'
            else:
                self.settings['preferences']=restored
                note='Launcher values now match the restored preferences.'
            self._save_settings()
            return str(path)+'; '+note
        self._task('Restore game preferences',action)

    def save_services(self):
        values={k:e.get().strip() for k,e in self.service_entries.items()}
        if self.discord_enabled.get() and (not values['discord_client_id'].isdigit()):
            messagebox.showerror('Discord','Enter your public numeric Discord Application ID.');return
        if values['proton'] and not Path(values['proton']).is_file():
            messagebox.showerror('Proton','Select an existing Proton executable.');return
        if values['update_manifest']:
            from urllib.parse import urlsplit
            if urlsplit(values['update_manifest']).scheme!='https':
                messagebox.showerror('Updates','Use an HTTPS manifest URL.');return
        if values['update_hosts']:
            import re
            if any(not re.fullmatch(r'[A-Za-z0-9.-]+',h.strip()) for h in values['update_hosts'].split(',')):
                messagebox.showerror('Updates','Enter hostnames only, separated by commas.');return
        self.settings.update(values);self.settings['discord_enabled']=self.discord_enabled.get();self._save_settings()
        self._start_presence();self._log('Saved launcher settings.');self.show_page('Settings')

    def _integrity_page(self):
        from .app import text,C
        self._heading('Game health','Integrity + recovery','Steam verifies official game files. A local baseline only detects changes since you recorded it.')
        s=self._area()
        text(s,'OFFICIAL STEAM VERIFICATION',12,'bold').pack(anchor='w')
        text(s,'Steam may replace modified files during verification. Restore your wubuGO profiles/addons first and keep backups.\n'
               'Steam shows its own verification/download progress; this launcher does not fabricate Steam progress.',
             10,fg=C['muted'],wraplength=780).pack(anchor='w',pady=9)
        self._row_buttons(s,[('INSPECT INSTALLATION',self.inspect_game,'primary'),
                             ('VERIFY VIA STEAM',self.verify_steam,'outline')])
        s=self._area()
        text(s,'LOCAL BASELINE',12,'bold').pack(anchor='w')
        text(s,'Records hashes of the base game, excluding manager configs and MIGI. Recording may take several minutes.\n'
               'Record only from a trusted, Steam-verified game. This does not prove files match Valve’s official release.',
             10,fg=C['muted'],wraplength=780).pack(anchor='w',pady=9)
        self._row_buttons(s,[('RECORD BASELINE',self.record_baseline,'secondary'),
                             ('COMPARE BASELINE',self.compare_baseline,'outline')])
        report=state_root()/'integrity-report.json'
        if report.is_file():
            text(s,report.read_text(encoding='utf-8')[:4000],9,fg=C['muted'],wraplength=780).pack(anchor='w',pady=12)

    def inspect_game(self):
        from modkit.game_integrity import inspect_install
        try: root=self._require_game()
        except (ValueError,OSError) as exc: messagebox.showerror('Integrity',str(exc));return
        def action():
            report=inspect_install(root);atomic_json(state_root()/'integrity-report.json',report)
            return json.dumps(report)
        self._task('Inspect game installation',action)

    def verify_steam(self):
        if messagebox.askyesno('Steam verification','Open official Steam verification? Steam may repair files and download game data. Restore modifications first.'):
            webbrowser.open('steam://validate/4465480')

    def _baseline_path(self):
        import hashlib
        root=self._require_game()
        return state_root()/'baselines'/(hashlib.sha256(str(root).encode()).hexdigest()[:16]+'.json')

    def record_baseline(self):
        from modkit.game_integrity import create_baseline
        try: root=self._require_game();path=self._baseline_path()
        except (ValueError,OSError) as exc: messagebox.showerror('Baseline',str(exc));return
        if path.exists() and not messagebox.askyesno('Replace baseline','Replace the existing local baseline with current file hashes?'):return
        self._task('Record base-game hashes',lambda:f'Recorded {len(create_baseline(root,path,self._operation_progress)["files"])} files at {path}')

    def compare_baseline(self):
        from modkit.game_integrity import verify_baseline
        try: root=self._require_game();path=self._baseline_path()
        except (ValueError,OSError) as exc: messagebox.showerror('Baseline',str(exc));return
        def action():
            report=verify_baseline(root,path,self._operation_progress);atomic_json(state_root()/'integrity-report.json',report)
            return json.dumps(report)
        self._task('Compare base-game hashes',action)

    def _start_presence(self):
        from modkit.presence import Presence
        if self.presence: self.presence.close()
        self.presence=None
        if self.settings.get('discord_enabled'):
            try:
                self.presence=Presence(str(self.settings.get('discord_client_id','')))
                self.presence.start()
            except (ValueError,OSError) as exc:self._log('Discord presence: '+str(exc))

    def _shutdown(self):
        if self.working:
            messagebox.showinfo('Operation in progress','Wait for the file operation to finish before closing.');return
        self.download_manager.close(wait=False)
        if self.presence:self.presence.close()
        self.destroy()
