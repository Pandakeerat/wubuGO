"""Explicit release-builder self-test; uses isolated temporary state, no network."""
from __future__ import annotations
import json
import os
from pathlib import Path
import tempfile
import traceback


def run(destination):
    destination=Path(destination).expanduser().resolve()
    report={'ok':False,'network_used':False,'game_started':False,'pages':[]}
    with tempfile.TemporaryDirectory(prefix='wubugo-selftest-') as temporary:
        os.environ['WUBUGO_DATA_DIR']=temporary
        app=None
        try:
            from .runtime import resource_root,VERSION
            from modkit.asset_integrity import verify_assets
            from modkit.sources import offline_source,validate_2016
            from modkit.weapon_balance import create_2016_addon
            report['version']=VERSION
            report['assets']=verify_assets(resource_root())
            if not report['assets']['ok']:raise ValueError('Bundled asset integrity failed')
            source=offline_source(resource_root())
            report['source']=validate_2016(source)
            addon,_,count=create_2016_addon(source,Path(temporary)/'build')
            report['generated_weapons']=count
            from . import app as gui
            if gui.STATE.resolve() != Path(temporary).resolve():
                raise ValueError('Self-test requires isolated launcher state')
            report['isolated_state']=True
            app=gui.Studio();app.update()
            for page in app.nav_buttons:
                app.show_page(page);app.update()
                report['pages'].append(page)
            report['tk_version']=str(app.tk.call('info','patchlevel'))
            report['logo_dimensions']=[app.logo_image.width(),app.logo_image.height()]
            from .loader_selftest import verify_external_loader
            report['external_process']=verify_external_loader()
            report['ok']=True
        except Exception:
            report['error']=traceback.format_exc()
        finally:
            if app is not None:
                app.download_manager.close(wait=True)
                if app.presence:app.presence.close()
                app.destroy()
    destination.parent.mkdir(parents=True,exist_ok=True)
    destination.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    return 0 if report['ok'] else 1
