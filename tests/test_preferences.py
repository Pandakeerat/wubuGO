import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from launcher.runtime import atomic_json, load_settings, state_root
from modkit.game_settings import render_settings, install_settings, rollback_settings
from test_studio import fake_game

class PreferencesTests(unittest.TestCase):
    def test_reject_cfg_injection_and_invalid_values(self):
        for value in ('1;connect example.org', float('nan'), float('inf'), True, -10):
            with self.assertRaises(ValueError): render_settings({'volume':value})
        with self.assertRaises(ValueError): render_settings({'exec':'unsafe'})

    def test_atomic_settings_and_corrupt_recovery(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'settings.json'
            atomic_json(p,{'test':True})
            self.assertEqual(load_settings(p), {'test':True})
            p.write_text('[')
            self.assertEqual(load_settings(p), {})
            self.assertEqual(list(Path(t).glob('*.tmp')), [])

    def test_preferences_restore(self):
        with tempfile.TemporaryDirectory() as t:
            game=fake_game(Path(t)/'game')
            path=install_settings(game,{'volume':0.2})
            old=path.read_bytes()
            install_settings(game,{'volume':0.3})
            rollback_settings(game)
            self.assertEqual(path.read_bytes(),old)

    def test_link_escape(self):
        with tempfile.TemporaryDirectory() as t:
            game=fake_game(Path(t)/'game');outside=Path(t)/'outside';outside.mkdir()
            try:
                (game/'csgo/cfg').symlink_to(outside, target_is_directory=True)
            except OSError as exc:
                if __import__('os').name == 'nt' and getattr(exc, 'winerror', None) == 1314:
                    self.skipTest('Windows symbolic-link privilege unavailable')
                raise
            with self.assertRaises(ValueError): install_settings(game,{})
            self.assertEqual(list(outside.iterdir()), [])

    def test_many_preference_versions_and_rollbacks(self):
        with tempfile.TemporaryDirectory() as t:
            game=fake_game(Path(t)/'game')
            texts=[]
            for volume in (0.1,0.2,0.3,0.4):
                p=install_settings(game,{'volume':volume});texts.append(p.read_bytes())
            for expected in reversed(texts[:-1]):
                rollback_settings(game)
                self.assertEqual(p.read_bytes(),expected)
            rollback_settings(game)
            self.assertFalse(p.exists())
            self.assertEqual(len(list(p.parent.glob('*.wubugo.disabled.*'))),4)

    def test_original_foreign_file_preserved(self):
        with tempfile.TemporaryDirectory() as t:
            game=fake_game(Path(t)/'game');p=game/'csgo/cfg/wubugo_preferences.cfg'
            p.parent.mkdir();p.write_text('original user settings')
            install_settings(game,{'volume':0.2})
            install_settings(game,{'volume':0.4})
            rollback_settings(game);rollback_settings(game)
            self.assertEqual(p.read_text(),'original user settings')
            with self.assertRaises(ValueError):rollback_settings(game)

    def test_retained_header_does_not_prove_ownership(self):
        with tempfile.TemporaryDirectory() as t:
            game=fake_game(Path(t)/'game');p=install_settings(game,{})
            p.write_text(p.read_text()+'exec something.cfg\n')
            with self.assertRaises(ValueError):rollback_settings(game)
            with self.assertRaises(ValueError):install_settings(game,{'volume':0.1})

    def test_backup_checksum_tampering_is_blocked(self):
        with tempfile.TemporaryDirectory() as t:
            game=fake_game(Path(t)/'game');p=install_settings(game,{'volume':0.2})
            install_settings(game,{'volume':0.3})
            next(p.parent.glob('*.wubugo.bak.*')).write_text('tampered')
            with self.assertRaises(ValueError):rollback_settings(game)
            self.assertIn('volume "0.3"',p.read_text())

    def test_running_game_blocks_preferences(self):
        with tempfile.TemporaryDirectory() as t:
            game=fake_game(Path(t)/'game')
            with patch('modkit.retrokit.running_game_processes',return_value=['csgo.exe']):
                with self.assertRaises(ValueError):install_settings(game,{})

    def test_metadata_failure_restores_previous_preferences(self):
        from modkit import game_settings
        with tempfile.TemporaryDirectory() as t:
            game=fake_game(Path(t)/'game');p=install_settings(game,{'volume':0.2})
            original=p.read_bytes();real=game_settings._atomic_bytes
            def fail_receipt(path,data):
                if path.suffix=='.json':raise OSError('simulated metadata write failure')
                return real(path,data)
            with patch.object(game_settings,'_atomic_bytes',side_effect=fail_receipt):
                with self.assertRaises(OSError):install_settings(game,{'volume':0.3})
            self.assertEqual(p.read_bytes(),original)
            install_settings(game,{'volume':0.4})

    def test_launcher_refuses_edited_or_untracked_cfg(self):
        from modkit.retrokit import launch, install_profile
        with tempfile.TemporaryDirectory() as t:
            game=fake_game(Path(t)/'game');p=install_settings(game,{})
            p.write_text(p.read_text()+'connect example.org\n')
            with self.assertRaises(ValueError):launch(game)
            p.unlink()
            profile=install_profile(game);profile.write_text('connect example.org')
            with self.assertRaises(ValueError):launch(game)
