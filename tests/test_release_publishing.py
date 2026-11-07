"""Release publication guardrails; all GitHub/git mutations are mocked."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def load_script(name):
    spec = importlib.util.spec_from_file_location('wubugo_' + name, ROOT / 'packaging' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


prepare = load_script('prepare_release')
publisher = load_script('publish_release')
COMMIT = 'a' * 40
REPOSITORY = 'example/wubugo'
TAG = 'v6.0.0-rc.1'


class PublisherTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.original_cwd = Path.cwd()
        self.addCleanup(os.chdir, self.original_cwd)
        self.root = Path(self.temp.name)
        self.stage = self.root / 'staged'
        self.stage.mkdir()
        (self.stage / 'SHA256SUMS').write_text('staged checksums')
        (self.stage / 'release-notes.md').write_text('release notes')
        (self.stage / 'update-manifest.json').write_text('{}')
        self.environment = {'GITHUB_ACTIONS': 'true', 'GITHUB_EVENT_NAME': 'workflow_dispatch',
                            'GITHUB_REF': 'refs/heads/main', 'GITHUB_REPOSITORY': REPOSITORY,
                            'GITHUB_SHA': COMMIT}

    def invoke(self):
        publisher.publish(self.stage, repository=REPOSITORY, tag=TAG,
                          source_commit=COMMIT, root=self.root)

    def fake_run(self, args, *, capture=False):
        if args[:3] == ['gh', 'release', 'view']:
            return json.dumps({'isDraft': True, 'tagName': TAG})
        if args[:3] == ['git', 'status', '--porcelain']:
            return ''
        if args[:2] == ['git', 'rev-parse']:
            return COMMIT
        if args[:2] == ['git', 'fetch']:
            return None
        if args[:2] == ['git', 'ls-remote']:
            return ''
        raise AssertionError('Unexpected external action: ' + repr(args))

    def test_nonmanual_nonmain_or_mismatched_context_never_contacts_github(self):
        for key, value in [('GITHUB_ACTIONS', 'false'), ('GITHUB_EVENT_NAME', 'pull_request'),
                           ('GITHUB_REF', 'refs/heads/feature'), ('GITHUB_REPOSITORY', 'other/repo'),
                           ('GITHUB_SHA', 'b' * 40)]:
            environment = dict(self.environment, **{key: value})
            with self.subTest(key=key), patch.dict(os.environ, environment), patch.object(publisher, 'run') as action:
                with self.assertRaises(ValueError):
                    self.invoke()
                action.assert_not_called()

    def test_existing_published_release_cannot_be_replaced(self):
        with patch.dict(os.environ, self.environment), patch.object(publisher, 'run',
                return_value=json.dumps({'isDraft': False, 'tagName': TAG})) as action:
            with self.assertRaisesRegex(ValueError, 'existing draft'):
                self.invoke()
            self.assertEqual(action.call_count, 1)
            self.assertEqual(action.call_args.args[0][:3], ['gh', 'release', 'view'])

    def test_advanced_main_aborts_before_upload(self):
        def action(args, **kwargs):
            if args == ['git', 'rev-parse', 'origin/main']:
                return 'b' * 40
            return self.fake_run(args, **kwargs)
        with patch.dict(os.environ, self.environment), patch.object(publisher, 'run', side_effect=action) as calls:
            with self.assertRaisesRegex(ValueError, 'Main advanced'):
                self.invoke()
            self.assertFalse(any(call.args[0][:3] == ['gh', 'release', 'upload'] for call in calls.call_args_list))
            self.assertFalse((self.root / 'releases/update-manifest.json').exists())

    def test_upload_failure_prevents_feed_write_push_and_publication(self):
        def action(args, **kwargs):
            if args[:3] == ['gh', 'release', 'upload']:
                raise subprocess.CalledProcessError(1, args)
            return self.fake_run(args, **kwargs)
        with patch.dict(os.environ, self.environment), patch.object(publisher, 'run', side_effect=action) as calls:
            with self.assertRaises(subprocess.CalledProcessError):
                self.invoke()
            actions = [call.args[0] for call in calls.call_args_list]
            self.assertFalse(any(args[:2] in [['git', 'push'], ['git', 'commit']] for args in actions))
            self.assertFalse(any(args[:3] == ['gh', 'release', 'edit'] for args in actions))
            self.assertFalse((self.root / 'releases/update-manifest.json').exists())


class PreparationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.windows, self.fedora = self.root / 'windows', self.root / 'fedora'
        for path in (self.windows, self.fedora): path.mkdir()
        self.names = {
            self.windows: ['wubuGO-6.0.0-windows-x64-setup.exe', 'wubuGO-6.0.0-windows-x64-portable.zip'],
            self.fedora: ['wubuGO-6.0.0-linux-x64-portable.tar.gz', 'wubugo-6.0.0-1.fc43.x86_64.rpm'],
        }
        gui = {'ok': True, 'game_started': False, 'network_used': False, 'isolated_state': True,
               'generated_weapons': 33, 'pages': sorted(prepare.PAGES), 'assets': {'ok': True}}
        for directory, names in self.names.items():
            for name in names: (directory / name).write_bytes(name.encode())
            (directory / 'SHA256SUMS').write_text(''.join(
                hashlib.sha256((directory / name).read_bytes()).hexdigest() + '  ' + name + '\n' for name in names))
            for name in ('frozen-selftest.json', 'installed-selftest.json',
                         'user-installed-selftest.json', 'rpm-installed-selftest.json'):
                (directory / name).write_text(json.dumps(gui))
            (directory / 'installer-smoke.json').write_text(json.dumps({'ok': True, 'game_started': False}))

    def invoke(self):
        return prepare.prepare(self.windows, self.fedora, self.root / 'output', repository=REPOSITORY,
                               tag=TAG, version='6.0.0', source_commit=COMMIT, run_id='123', root=self.root)

    def test_checksum_mismatch_prevents_staging_and_archive_creation(self):
        (self.windows / self.names[self.windows][0]).write_bytes(b'corrupted transfer')
        with patch.object(prepare.subprocess, 'check_output', return_value=COMMIT), \
                patch.object(prepare.subprocess, 'run') as archive:
            with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
                self.invoke()
            archive.assert_not_called()
            self.assertFalse((self.root / 'output/update-manifest.json').exists())

    def test_failed_native_report_prevents_release_manifest(self):
        (self.windows / 'installed-selftest.json').write_text(json.dumps({'ok': False, 'game_started': False}))
        with patch.object(prepare.subprocess, 'check_output', return_value=COMMIT), \
                patch.object(prepare.subprocess, 'run') as archive:
            with self.assertRaisesRegex(ValueError, 'report failed'):
                self.invoke()
            archive.assert_not_called()
            self.assertFalse((self.root / 'output/update-manifest.json').exists())


if __name__ == '__main__':
    unittest.main()
