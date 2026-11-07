"""Run explicitly with a real X display: DISPLAY=:99 python3 tests/smoke_gui.py.
Uses temporary app data, synthetic game files, and mocked network responses.
"""
import hashlib
import io
import os
from pathlib import Path
import sys
import tempfile
import time
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))


def main():
    with tempfile.TemporaryDirectory() as tmp:
        os.environ['WUBUGO_DATA_DIR']=str(Path(tmp)/'state')
        from launcher.app import Studio
        from modkit.retrokit import PROFILE
        from tkinter import messagebox
        errors=[]
        with patch.object(messagebox,'showerror',side_effect=lambda *a,**k:errors.append(a)), patch.object(messagebox,'showinfo'):
            app=Studio();app.update()
            def wait_task():
                end=time.monotonic()+10
                while app.working and time.monotonic()<end:
                    app.update();time.sleep(.01)
                app.update();assert not app.working,'task did not finish'
            for page in app.nav_buttons:
                app.show_page(page);app.update()
            game=Path(tmp)/'game';(game/'csgo').mkdir(parents=True)
            (game/'csgo.exe').write_bytes(b'MZ test')
            native=game/'csgo_linux64';native.write_text('#!/bin/sh\nexit 0\n');native.chmod(0o755)
            app.game=game
            app.prepare_all();wait_task()
            assert (game/'csgo/cfg/wubugo_2016.cfg').read_text()==PROFILE
            app.show_page('Settings');app.update()
            app.pref_entries['volume'].delete(0,'end');app.pref_entries['volume'].insert(0,'0.4')
            app.save_preferences();wait_task()
            assert 'volume "0.4"' in (game/'csgo/cfg/wubugo_preferences.cfg').read_text()
            app.rollback_profile();wait_task()
            assert not (game/'csgo/cfg/wubugo_2016.cfg').exists()
            app.show_page('Integrity');app.record_baseline();wait_task();app.compare_baseline();wait_task()
            class Response(io.BytesIO):
                headers={'Content-Length':'7'}
                def geturl(self):return 'https://example.org/test.zip'
            with patch('modkit.downloads._open_url',return_value=Response(b'payload')):
                app.queue_download('https://example.org/test.zip','test.zip','dependency',hashlib.sha256(b'payload').hexdigest())
                end=time.monotonic()+5
                while time.monotonic()<end:
                    app.update();time.sleep(.01)
                    jobs=app.download_manager.jobs()
                    if jobs and jobs[-1]['status']=='complete':break
                app.update()
                assert jobs[-1]['status']=='complete',jobs
                assert len(app.download_widgets)==1
            app._launch_game(False,'de_dust2');app.update()
            end=time.monotonic()+2
            while app.game_process and time.monotonic()<end:app.update();time.sleep(.01)
            assert not errors,errors
            app._shutdown()
            print('PASS: nine pages; offline setup; preferences; rollback; integrity baseline; staged download rows; native local launch.')

if __name__=='__main__': main()
