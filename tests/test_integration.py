"""Source provenance, optional Bridge inventory, and local-menu safeguards."""
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
import zipfile
from unittest.mock import patch

from modkit.bridge_manager import inspect_bridge, dependency_catalog, import_bridge_bytes
from modkit.sources import offline_source, validate_2016, SOURCE_SHA256
from modkit.weapon_balance import create_2016_addon, IDS
from modkit.panorama_ui import patch_mainmenu, patch_zip, restore_bridge

ROOT = Path(__file__).resolve().parent.parent

class IntegrationTests(unittest.TestCase):
    def test_full_bundle_provenance_and_all_firearms(self):
        source=offline_source(ROOT)
        self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(),SOURCE_SHA256)
        self.assertEqual(validate_2016(source)['weapon_item_count'],33)
        self.assertEqual({w['name'] for w in json.loads(source.read_text())['weapons']},set(IDS))
        with tempfile.TemporaryDirectory() as tmp:
            _,report,n=create_2016_addon(source,Path(tmp))
            data=json.loads(report.read_text())
            self.assertEqual(n,33)
            self.assertEqual(data['missing_weapons'],[])
            self.assertFalse(data['in_game_verified'])
            self.assertEqual(data['source_sha256'],SOURCE_SHA256)

    def test_full_bundle_tampering_is_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); (root/'data').mkdir()
            (root/'data/weapons-1.35.4.4.json').write_text('{}')
            with self.assertRaisesRegex(ValueError,'checksum'): offline_source(root)

    def test_bridge_reports_platform_and_missing_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)
            (folder/'Setup.cmd').write_text('powershell setup.ps1')
            (folder/'Launch.cmd').write_text('powershell launch.ps1')
            info=inspect_bridge(folder,platform='linux')
            self.assertFalse(info['platform_supported'])
            self.assertIn('setup.ps1',info['missing'])
            self.assertIn('PanoramaBridge32.dll',info['missing'])
            self.assertFalse(info['in_game_verified'])
            self.assertFalse(info['offline_dependencies_verified'])

    def test_bridge_invalid_config_is_actionable(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);(folder/'local-settings.json').write_text('not JSON')
            self.assertIn('malformed',inspect_bridge(folder)['config_error'])

    def test_dependencies_are_explicit_pins(self):
        deps=dependency_catalog()['dependencies']
        self.assertEqual(len(deps),3)
        for dep in deps:
            self.assertEqual(len(dep['sha256']),64)
            self.assertTrue(dep['url'].startswith('https://'))
            self.assertEqual(dep['platforms'],['win32'])

    def test_menu_launch_buttons_stay_local(self):
        patched=patch_mainmenu('<CSGOMainMenu><styles></styles></CSGOMainMenu>')
        self.assertIn('sv_lan 1; map de_dust2',patched)
        self.assertNotIn('OpenPlayMenu',patched)
        self.assertNotIn('openserverbrowser',patched)

    def test_existing_patch_output_is_protected(self):
        with tempfile.TemporaryDirectory() as tmp:
            original=Path(tmp)/'original.zip';dest=Path(tmp)/'output.zip'
            dest.write_bytes(b'keep')
            with zipfile.ZipFile(original,'w') as z:
                z.writestr('panorama/layout/mainmenu.xml','<CSGOMainMenu><styles></styles></CSGOMainMenu>')
            with self.assertRaises(FileExistsError): patch_zip(original,dest)
            self.assertEqual(dest.read_bytes(),b'keep')

    def test_bridge_restore_failure_keeps_current(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);current=root/'panorama.my.zip';backup=root/'panorama.my.zip.wubugo.bak'
            current.write_bytes(b'modified');backup.write_bytes(b'original')
            real_rename=Path.rename
            def fail_backup(path,target):
                if path.resolve()==backup.resolve(): raise OSError('simulated disk failure')
                return real_rename(path,target)
            with patch.object(Path,'rename',fail_backup):
                with self.assertRaises(OSError):restore_bridge(root)
            self.assertEqual(current.read_bytes(),b'modified')
            self.assertEqual(backup.read_bytes(),b'original')
