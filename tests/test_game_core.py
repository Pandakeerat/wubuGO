import json
import os
import tempfile
import unittest
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch
from modkit import retrokit
from modkit.game_integrity import create_baseline, verify_baseline, inspect_install
from test_studio import fake_game

class GameCoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
    def tearDown(self): self.tmp.cleanup()

    def test_discovery_reads_manifest_and_extra_library(self):
        steam=self.root/'steam';other=self.root/'library'
        (steam/'steamapps').mkdir(parents=True)
        (steam/'steamapps/libraryfolders.vdf').write_text('"libraryfolders" { "1" { "path" "'+str(other)+'" } }')
        game=fake_game(other/'steamapps/common/custom')
        (other/'steamapps/appmanifest_4465480.acf').write_text('"AppState" { "installdir" "custom" }')
        with patch.object(retrokit,'_steam_roots',return_value=[steam]):
            self.assertEqual(retrokit.detect_games(),[game.resolve()])

    def test_windows_launch_uses_exe_and_tasklist_guard(self):
        game=fake_game(self.root/'game')
        with patch.object(retrokit,'os',SimpleNamespace(name='nt')), \
             patch.object(retrokit.subprocess,'run',return_value=SimpleNamespace(stdout='"steam.exe","1"\n')) as tasks, \
             patch.object(retrokit.subprocess,'Popen') as proc:
            retrokit.launch(game)
            tasks.assert_called_once()
            self.assertEqual(proc.call_args.args[0][0],str(game/'csgo.exe'))
            self.assertIn('-insecure',proc.call_args.args[0])

    def test_cs2_only_rejected(self):
        game=self.root/'cs2';(game/'csgo').mkdir(parents=True)
        (game/'game/bin/win64').mkdir(parents=True)
        (game/'game/bin/win64/cs2.exe').touch()
        with self.assertRaises(ValueError):retrokit.game_root(game)

    def test_malformed_manifest_cannot_escape_library(self):
        steam=self.root/'steam';(steam/'steamapps/common').mkdir(parents=True)
        fake_game(steam/'steamapps/evil')
        (steam/'steamapps/appmanifest_4465480.acf').write_text('"installdir" "../evil"')
        with patch.object(retrokit,'_steam_roots',return_value=[steam]):
            self.assertEqual(retrokit.detect_games(),[])

    def test_symlink_cfg_escape_is_blocked(self):
        if os.name=='nt': self.skipTest('symlink creation may require Windows privilege')
        game=fake_game(self.root/'game');outside=self.root/'outside';outside.mkdir()
        (game/'csgo/cfg').symlink_to(outside, target_is_directory=True)
        with self.assertRaises(ValueError):retrokit.install_profile(game)
        self.assertEqual(list(outside.iterdir()),[])

    def test_running_game_blocks_profile_write(self):
        game=fake_game(self.root/'game')
        with patch.object(retrokit,'running_game_processes',return_value=['123:csgo.exe']):
            with self.assertRaises(ValueError):retrokit.install_profile(game)
        self.assertFalse((game/'csgo/cfg').exists())

    def test_publication_failure_recovers_previous_addon(self):
        game=fake_game(self.root/'game');(game/'migi.exe').touch()
        (game/'migi/csgo').mkdir(parents=True);(game/'migi/csgo/gameinfo.txt').touch()
        addon=self.root/'m_wubugo_2016';scripts=addon/'scripts/items';scripts.mkdir(parents=True)
        source=scripts/'items_game_wubugo_2016.txt';source.write_text('first')
        target=retrokit.install_addon(game,addon)
        source.write_text('second')
        original=Path.rename
        def fail_stage(path,dest):
            if path.name.endswith('.wubugo-staging'):
                raise OSError('simulated publication failure')
            return original(path,dest)
        with patch.object(Path,'rename',fail_stage):
            with self.assertRaises(OSError):retrokit.install_addon(game,addon,replace=True)
        self.assertEqual((target/'scripts/items'/source.name).read_text(),'first')

    def test_baseline_detects_changes_and_is_not_official(self):
        game=fake_game(self.root/'game');(game/'csgo/gameinfo.txt').write_text('game')
        baseline=self.root/'baseline.json'
        create_baseline(game,baseline)
        self.assertTrue(verify_baseline(game,baseline)['ok'])
        (game/'csgo/gameinfo.txt').write_text('changed')
        report=verify_baseline(game,baseline)
        self.assertFalse(report['ok']);self.assertIn('csgo/gameinfo.txt',report['changed'])
        self.assertFalse(report['official_integrity_verified'])
        self.assertFalse(inspect_install(game)['official_integrity_verified'])

    def test_malicious_baseline_blocked(self):
        game=fake_game(self.root/'game');baseline=self.root/'baseline.json'
        create_baseline(game,baseline)
        data=json.loads(baseline.read_text());data['files']={'../outside':{'size':0,'sha256':'0'*64}}
        baseline.write_text(json.dumps(data))
        with self.assertRaises(ValueError):verify_baseline(game,baseline)

    @unittest.skipIf(os.name=='nt','Linux launch test')
    def test_windows_build_requires_explicit_proton(self):
        game=fake_game(self.root/'game');(game/'csgo_linux64').unlink()
        with self.assertRaises(ValueError):retrokit.launch(game)
        steam=self.root/'steam';(steam/'steamapps').mkdir(parents=True)
        proton=self.root/'proton';proton.write_text('#!/bin/sh\nexit 0\n');proton.chmod(0o755)
        with patch.object(retrokit,'_steam_roots',return_value=[steam]),patch.object(retrokit.subprocess,'Popen') as proc:
            retrokit.launch(game,proton=proton)
            cmd=proc.call_args.args[0]
            self.assertEqual(cmd[:3],[str(proton),'run',str(game/'csgo.exe')])
            self.assertIn('-insecure',cmd)
            self.assertEqual(proc.call_args.kwargs['env']['SteamAppId'],'4465480')

    def test_windows_game_bin_precedes_other_library_paths(self):
        game=fake_game(self.root/'game');(game/'bin').mkdir()
        with patch.object(retrokit,'os',SimpleNamespace(name='nt')), \
             patch.object(retrokit,'running_game_processes',return_value=[]), \
             patch.object(retrokit.subprocess,'Popen') as proc:
            retrokit.launch(game)
            self.assertTrue(proc.call_args.kwargs['env']['PATH'].startswith(str(game/'bin')+';'))
