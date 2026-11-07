"""Exercise real offline per-user install/uninstall without needing Tk or Steam."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

@unittest.skipUnless(os.name == 'posix' and shutil.which('bash'), 'Linux installer test')
class PackagingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='wubugo packaging ')
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.source = self.base/'portable source';self.source.mkdir()
        (self.source/'_internal').mkdir()
        (self.source/'wubuGO').write_text('#!/bin/sh\nexit 0\n')
        (self.source/'wubuGO').chmod(0o755)
        (self.source/'wubugo.png').write_bytes(b'icon')
        for src,dst in [('install-linux.sh','install.sh'),('uninstall-linux.sh','uninstall.sh')]:
            shutil.copy2(ROOT/'packaging'/src, self.source/dst)
        self.data=self.base/'user data'
        self.env=dict(os.environ,XDG_DATA_HOME=str(self.data))

    def run_script(self,path):
        return subprocess.run(['bash',str(path)],env=self.env,text=True,capture_output=True)

    def test_install_and_uninstall_preserve_user_data(self):
        state=self.data/'wubugo';state.mkdir(parents=True)
        (state/'settings.json').write_text('retained')
        result=self.run_script(self.source/'install.sh')
        self.assertEqual(result.returncode,0,result.stderr)
        app=self.data/'wubugo-app'
        self.assertTrue((app/'wubuGO').is_file())
        desktop=self.data/'applications/wubugo.desktop'
        self.assertIn('Exec="'+str(app/'wubuGO')+'"',desktop.read_text())
        result=self.run_script(app/'uninstall.sh')
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertFalse(app.exists());self.assertFalse(desktop.exists())
        self.assertEqual((state/'settings.json').read_text(),'retained')

    def test_existing_install_is_not_overwritten(self):
        self.assertEqual(self.run_script(self.source/'install.sh').returncode,0)
        app=self.data/'wubugo-app';(app/'custom.txt').write_text('keep')
        self.assertNotEqual(self.run_script(self.source/'install.sh').returncode,0)
        self.assertEqual((app/'custom.txt').read_text(),'keep')

    def test_existing_shortcut_is_not_overwritten(self):
        shortcut=self.data/'applications/wubugo.desktop';shortcut.parent.mkdir(parents=True)
        shortcut.write_text('custom entry')
        self.assertNotEqual(self.run_script(self.source/'install.sh').returncode,0)
        self.assertEqual(shortcut.read_text(),'custom entry')
        self.assertFalse((self.data/'wubugo-app').exists())

    def test_uninstaller_refuses_source_copy(self):
        self.assertNotEqual(self.run_script(self.source/'uninstall.sh').returncode,0)
        self.assertTrue(self.source.is_dir())

    def test_modified_shortcut_survives_uninstall(self):
        self.assertEqual(self.run_script(self.source/'install.sh').returncode,0)
        shortcut=self.data/'applications/wubugo.desktop';shortcut.write_text('user changed')
        self.assertEqual(self.run_script(self.data/'wubugo-app/uninstall.sh').returncode,0)
        self.assertEqual(shortcut.read_text(),'user changed')

class SourcePortabilityTests(unittest.TestCase):
    def test_no_case_collisions_in_release_paths(self):
        # Both a Python freeze spec and an RPM recipe must survive Windows checkout.
        paths=[p.relative_to(ROOT).as_posix() for p in (ROOT/'packaging').rglob('*') if p.is_file() and '__pycache__' not in p.parts]
        self.assertEqual(len(paths),len({p.casefold() for p in paths}))
