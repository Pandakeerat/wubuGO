import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch,Mock
from modkit import external_process as external

class ExternalProcessTests(unittest.TestCase):
    def test_source_environment_is_preserved(self):
        env={'PATH':'user-path','LD_LIBRARY_PATH':'user-libraries','SteamAppId':'4465480'}
        with patch.object(sys,'frozen',False,create=True):
            self.assertEqual(external.external_environment(env),env)

    def test_frozen_environment_restores_original_library_paths(self):
        with tempfile.TemporaryDirectory() as t:
            bundle=str(Path(t)/'bundle')
            env={'PATH':os.pathsep.join((bundle,str(Path(bundle)/'bin'),'/usr/bin')),
                 'LD_LIBRARY_PATH':bundle,'LD_LIBRARY_PATH_ORIG':'/opt/game-libs',
                 '_PYI_ARCHIVE_FILE':'manager.exe','_MEIPASS2':bundle,'SteamAppId':'4465480'}
            previous=dict(env)
            with patch.object(sys,'frozen',True,create=True), patch.object(sys,'_MEIPASS',bundle,create=True):
                clean=external.external_environment(env)
            self.assertEqual(clean['LD_LIBRARY_PATH'],'/opt/game-libs')
            self.assertEqual(clean['PATH'],'/usr/bin')
            self.assertEqual(clean['SteamAppId'],'4465480')
            self.assertNotIn('_PYI_ARCHIVE_FILE',clean)
            self.assertNotIn('LD_LIBRARY_PATH_ORIG',clean)
            self.assertEqual(env,previous)

    def test_no_original_means_no_inherited_loader_path(self):
        with patch.object(sys,'frozen',True,create=True):
            self.assertNotIn('LD_LIBRARY_PATH',external.external_environment({'LD_LIBRARY_PATH':'bundled'}))
            self.assertEqual(external.external_environment({'LD_LIBRARY_PATH':'bundled','LD_LIBRARY_PATH_ORIG':''})['LD_LIBRARY_PATH'],'')

    def test_windows_search_directory_is_cleared_only_during_child_creation(self):
        events=[]
        def spawn(*args,**kwargs):
            events.append('spawn');return 'child'
        with patch.object(sys,'platform','win32'), patch.object(sys,'frozen',True,create=True), \
             patch.object(external,'_kernel32',return_value='kernel'), \
             patch.object(external,'get_dll_directory',return_value='bundle'), \
             patch.object(external,'set_dll_directory',side_effect=lambda value,api:events.append(value)), \
             patch.object(external.subprocess,'Popen',side_effect=spawn):
            self.assertEqual(external.popen_external(['game.exe']),'child')
        self.assertEqual(events,[None,'spawn','bundle'])

    def test_windows_search_directory_is_restored_when_spawn_fails(self):
        events=[]
        with patch.object(sys,'platform','win32'), patch.object(sys,'frozen',True,create=True), \
             patch.object(external,'_kernel32',return_value='kernel'), \
             patch.object(external,'get_dll_directory',return_value='bundle'), \
             patch.object(external,'set_dll_directory',side_effect=lambda value,api:events.append(value)), \
             patch.object(external.subprocess,'Popen',side_effect=OSError('missing game')):
            with self.assertRaises(OSError):external.popen_external(['game.exe'])
        self.assertEqual(events,[None,'bundle'])

    def test_game_loader_failure_is_reported_as_failure(self):
        from launcher.app import Studio
        from tkinter import messagebox
        app=SimpleNamespace(game_process=Mock(),game_started_at=100,presence=None,_log=Mock())
        app.game_process.poll.return_value=0xc0000139
        with patch('launcher.app.time.monotonic',return_value=101),patch.object(messagebox,'showerror') as error:
            Studio._poll_game_process(app)
        self.assertIsNone(app.game_process)
        self.assertIn('0xC0000139',app._log.call_args.args[0])
        error.assert_called_once()

    def test_zero_exit_is_not_claimed_as_verified_game_start(self):
        from launcher.app import Studio
        from tkinter import messagebox
        app=SimpleNamespace(game_process=Mock(),game_started_at=100,presence=None,_log=Mock())
        app.game_process.poll.return_value=0
        with patch('launcher.app.time.monotonic',return_value=101),patch.object(messagebox,'showerror') as error:
            Studio._poll_game_process(app)
        self.assertIn('not verified',app._log.call_args.args[0])
        error.assert_not_called()
