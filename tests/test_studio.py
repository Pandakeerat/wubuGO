"""wubuGO v5 regression suite: all local, without internet or Steam."""
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch, MagicMock

from modkit import kv
from modkit.asset_integrity import verify_assets
from modkit.sources import validate_2016, ensure_source, offline_source, download_2016
from modkit.weapon_balance import create_2016_addon
from modkit.bridge_manager import import_bridge_archive, import_bridge_bytes
from modkit.retrokit import game_root, doctor, install_addon, install_profile, launch
from modkit.panorama_ui import install_to_bridge, restore_bridge

ROOT = Path(__file__).resolve().parent.parent


def fake_game(root):
    root.mkdir(parents=True,exist_ok=True)
    (root / 'csgo').mkdir(exist_ok=True)
    (root / 'csgo.exe').write_bytes(b'MZ synthetic')
    native = root / 'csgo_linux64'
    native.write_text('#!/bin/sh\nexit 0\n')
    native.chmod(0o755)
    return root


class StudioTests(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.base = Path(self.t.name)

    def tearDown(self):
        self.t.cleanup()

    def test_offline_bundle_validation(self):
        path = offline_source(ROOT)
        meta = validate_2016(path)
        self.assertEqual(meta['version'], '1.35.4.4')
        self.assertEqual(meta['scope'], 'complete')
        self.assertEqual(meta['weapon_item_count'], 33)

    def test_no_network_on_setup(self):
        with patch('modkit.sources.urlopen', side_effect=AssertionError('unexpected network')):
            path, meta = ensure_source(self.base/'missing.json', ROOT)
        self.assertTrue(path.is_file())
        self.assertEqual(meta['weapon_item_count'], 33)

    def test_weapon_addon_generated_from_bundled_data(self):
        addon, report, n = create_2016_addon(offline_source(ROOT),self.base/'build')
        self.assertEqual(n,33)
        file=addon/'scripts/items/items_game_wubugo_2016.txt'
        doc=kv.read(file)
        self.assertEqual(doc['items_game']['items']['7']['attributes']['damage'],'36')
        self.assertEqual(doc['items_game']['items']['9']['attributes']['damage'],'115')
        self.assertEqual(doc['items_game']['items']['16']['attributes']['primary clip size'],'30')
        self.assertEqual(json.loads(report.read_text())['source_scope'],'complete')

    def test_full_source_supplies_dual_berettas_magazine(self):
        addon, _, _ = create_2016_addon(offline_source(ROOT),self.base/'build')
        doc=kv.read(addon/'scripts/items/items_game_wubugo_2016.txt')
        attrs=doc['items_game']['items']['2']['attributes']
        self.assertEqual(attrs['primary clip size'], '30')  # full upstream snapshot now bundled

    def test_migi_addon_filename_according_to_docs(self):
        addon,_,_=create_2016_addon(offline_source(ROOT),self.base/'build')
        self.assertTrue((addon/'scripts/items/items_game_wubugo_2016.txt').is_file())
        self.assertFalse((addon/'scripts/items/items_game_m_wubugo_2016.txt').exists())

    def test_reject_2023_economy_schema(self):
        file=self.base/'wrong.txt'
        file.write_text('"items_game" { "items" {"42" {} } }')
        with self.assertRaises(ValueError):
            validate_2016(file)

    def test_reject_duplicate_weapon(self):
        data=json.loads(offline_source(ROOT).read_text())
        data['weapons'].append(data['weapons'][0].copy())
        path=self.base/'broken.json'
        path.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError,'repeats'):
            validate_2016(path)

    def test_steam_folder_and_hud_cfg_idempotence(self):
        game=fake_game(self.base/'csgo legacy')
        self.assertEqual(game_root(game),game)
        cfg=install_profile(game)
        self.assertEqual(cfg,install_profile(game))
        self.assertTrue(doctor(game)['hud_cfg_installed'])

    def test_migi_install_and_backup(self):
        game=fake_game(self.base/'csgo legacy')
        (game/'migi.exe').write_bytes(b'MZ synthetic')
        (game/'migi/csgo').mkdir(parents=True)
        (game/'migi/csgo/gameinfo.txt').write_text('')
        addon,_,_=create_2016_addon(offline_source(ROOT),self.base/'build')
        install_addon(game,addon)
        install_addon(game,addon,replace=True)
        f=addon/'scripts/items/items_game_wubugo_2016.txt'
        f.write_text(f.read_text()+'\n// edit')
        install_addon(game,addon,replace=True)
        self.assertTrue((game/'migi/csgo/addons/m_wubugo_2016.wubugo.backup').exists())

    def test_game_launch_command_insecure(self):
        game=fake_game(self.base/'csgo legacy')
        with patch('modkit.retrokit.subprocess.Popen') as popen:
            launch(game,False,['+map','de_dust2'])
        cmd=popen.call_args.args[0]
        self.assertIn('-insecure',cmd)
        self.assertEqual(cmd[-2:],['+map','de_dust2'])
        self.assertEqual(Path(cmd[0]), game/('csgo.exe' if __import__('os').name == 'nt' else 'csgo_linux64'))

    def test_bridge_import_offline(self):
        zpath=self.base/'bridge.zip'
        with zipfile.ZipFile(zpath,'w') as z:
            z.writestr('panorama-bridge-csgo-main/Setup.cmd','echo setup')
            z.writestr('panorama-bridge-csgo-main/Launch.cmd','echo launch')
        dest=import_bridge_archive(zpath,self.base/'bridge')
        self.assertTrue((dest/'Setup.cmd').exists())
        self.assertTrue((dest/'Launch.cmd').exists())

    def test_zip_traversal_blocked(self):
        buf=io.BytesIO()
        with zipfile.ZipFile(buf,'w') as z:
            z.writestr('repo/../../oops.txt','bad')
        with self.assertRaises(ValueError):
            import_bridge_bytes(buf.getvalue(),self.base/'bridge')
        self.assertFalse((self.base/'oops.txt').exists())

    def test_in_game_menu_patch_backup_restore(self):
        bridge=self.base/'bridge';bridge.mkdir()
        (bridge/'Launch.cmd').write_text('echo launch')
        archive=bridge/'panorama.my.zip'
        xml='<CSGOMainMenu><styles></styles><Panel></Panel></CSGOMainMenu>'
        with zipfile.ZipFile(archive,'w') as z:
            z.writestr('panorama/layout/mainmenu.xml',xml)
        changed,backup=install_to_bridge(bridge)
        self.assertTrue(backup.exists())
        with zipfile.ZipFile(changed) as z:
            self.assertIn(b'Retro2016MenuPanel',z.read('panorama/layout/mainmenu.xml'))
        restore_bridge(bridge)
        with zipfile.ZipFile(archive) as z:
            self.assertNotIn(b'Retro2016MenuPanel',z.read('panorama/layout/mainmenu.xml'))

    def test_bundled_asset_integrity(self):
        result = verify_assets(ROOT)
        self.assertTrue(result['ok'],result['failures'])
        self.assertGreaterEqual(result['checked'], 5)

    def test_prebuilt_assets(self):
        p=ROOT/'assets/m_wubugo_2016/scripts/items/items_game_wubugo_2016.txt'
        self.assertTrue(p.is_file())
        doc=kv.read(p)
        self.assertEqual(len(doc['items_game']['items']),33)

if __name__=='__main__':
    unittest.main()
