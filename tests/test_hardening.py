import io
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
from modkit.bridge_manager import import_bridge_bytes, inspect_bridge
from modkit.retrokit import launch, install_profile, install_addon
from modkit.recovery import restore_profile, restore_addon
from test_studio import fake_game

class HardeningTests(unittest.TestCase):
    def archive(self, prefix='', extra=None):
        buf=io.BytesIO()
        with zipfile.ZipFile(buf,'w') as z:
            if prefix: z.writestr(prefix, '')
            z.writestr(prefix+'Setup.cmd','echo setup')
            z.writestr(prefix+'Launch.cmd','echo launch')
            if extra: z.writestr(*extra)
        return buf.getvalue()

    def test_zip_layouts(self):
        with tempfile.TemporaryDirectory() as t:
            for i,prefix in enumerate(('', 'repository/')):
                dest=import_bridge_bytes(self.archive(prefix),Path(t)/str(i))
                self.assertTrue((dest/'Setup.cmd').is_file())
                self.assertFalse(inspect_bridge(dest)['offline_dependencies_verified'])

    def test_unsafe_windows_paths_preserve_empty_destination(self):
        with tempfile.TemporaryDirectory() as t:
            dest=Path(t)/'bridge';dest.mkdir()
            for name in ('..\\escape', '/absolute', 'CON.txt', 'bad:stream', 'file.'):
                with self.assertRaises(ValueError):
                    import_bridge_bytes(self.archive(extra=(name,'bad')),dest)
                self.assertTrue(dest.is_dir())
                self.assertEqual(list(dest.iterdir()), [])

    def test_overrides_blocked(self):
        with tempfile.TemporaryDirectory() as t:
            game=fake_game(Path(t)/'game')
            for args in (['+connect','example.org'], ['+exec','unsafe.cfg'], ['+map','de_dust2;+connect x'], ['-secure']):
                with patch('modkit.retrokit.running_game_processes', return_value=[]), patch('modkit.retrokit.subprocess.Popen') as proc:
                    with self.assertRaises(ValueError): launch(game,extra=args)
                    proc.assert_not_called()
            with patch('modkit.retrokit.running_game_processes', return_value=[]), patch('modkit.retrokit.subprocess.Popen') as proc:
                launch(game,extra=['+map','de_dust2'])
                cmd=proc.call_args.args[0]
                self.assertIn('-insecure',cmd)
                self.assertEqual(cmd[cmd.index('+sv_lan')+1],'1')

    def test_profile_rollback_and_edit_protection(self):
        with tempfile.TemporaryDirectory() as t:
            game=fake_game(Path(t)/'game')
            cfg=game/'csgo/cfg/wubugo_2016.cfg';cfg.parent.mkdir()
            cfg.write_text('original')
            install_profile(game,replace=True)
            restore_profile(game)
            self.assertEqual(cfg.read_text(),'original')
            with self.assertRaises(ValueError): restore_profile(game)

    def test_latest_addon_rollback_keeps_modified_copy(self):
        with tempfile.TemporaryDirectory() as t:
            game=fake_game(Path(t)/'game')
            (game/'migi.exe').touch()
            build=game/'migi/csgo';build.mkdir(parents=True)
            (build/'gameinfo.txt').touch()
            source=Path(t)/'m_wubugo_2016/scripts/items';source.mkdir(parents=True)
            f=source/'items_game_wubugo_2016.txt'
            for value in ('first','second','third'):
                f.write_text(value)
                target=install_addon(game,source.parent.parent,replace=True)
            restore_addon(game)
            self.assertEqual((target/'scripts/items'/f.name).read_text(),'second')
            self.assertTrue(target.with_name(target.name+'.wubugo.disabled').is_dir())
