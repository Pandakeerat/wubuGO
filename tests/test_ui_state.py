"""Display-independent tests of launcher callbacks and restored preference state."""
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import Mock, patch
from launcher.app import Studio
from launcher.pages import ExtraPages
from launcher.runtime import VERSION, DEFAULT_UPDATE_MANIFEST, DEFAULT_UPDATE_HOSTS
from modkit.game_settings import install_settings, read_installed_settings
from test_studio import fake_game


class UIStateTests(unittest.TestCase):
    def test_page_wheel_handles_child_widgets_and_preserves_text_controls(self):
        scroll=Mock()
        app=SimpleNamespace(scroll=scroll)
        for widget in ('Label','Button','Frame'):
            Studio._wheel(app,SimpleNamespace(widget=SimpleNamespace(winfo_class=lambda:widget),delta=-120))
        self.assertEqual(scroll.yview_scroll.call_count,3)
        scroll.yview_scroll.assert_called_with(1,'units')
        for widget in ('Text','Entry','TCombobox'):
            Studio._wheel(app,SimpleNamespace(widget=SimpleNamespace(winfo_class=lambda:widget),delta=-120))
        self.assertEqual(scroll.yview_scroll.call_count,3)
        Studio._wheel(app,SimpleNamespace(widget=SimpleNamespace(winfo_class=lambda:'Label'),delta=1))
        scroll.yview_scroll.assert_called_with(-1,'units')

    def dummy(self,game):
        app=SimpleNamespace(settings={'preferences':{'volume':0.4}},_require_game=lambda:game,_save_settings=Mock())
        app._task=lambda name,fn:fn()
        return app

    def test_rollback_synchronizes_saved_launcher_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            game=fake_game(Path(tmp)/'game')
            install_settings(game,{'volume':0.2})
            install_settings(game,{'volume':0.4})
            app=self.dummy(game)
            ExtraPages.restore_preferences(app)
            self.assertEqual(app.settings['preferences']['volume'],0.2)
            self.assertEqual(read_installed_settings(game)['volume'],0.2)
            app._save_settings.assert_called_once()

    def test_original_foreign_cfg_is_never_parsed_as_launcher_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            game=fake_game(Path(tmp)/'game')
            target=game/'csgo/cfg/wubugo_preferences.cfg';target.parent.mkdir()
            target.write_text('volume "0.9"\nexec foreign.cfg\n')
            install_settings(game,{'volume':0.4})
            app=self.dummy(game)
            ExtraPages.restore_preferences(app)
            self.assertNotIn('preferences',app.settings)
            self.assertEqual(target.read_text(),'volume "0.9"\nexec foreign.cfg\n')
            self.assertIsNone(read_installed_settings(game))

    def test_explicit_update_check_uses_default_repo_feed_without_startup_network(self):
        app=SimpleNamespace(settings={},_task=lambda name,fn:fn())
        with patch('modkit.downloads.check_update',return_value={'version':'6.0.0','available':False}) as check, \
             patch('launcher.pages.atomic_json') as save:
            ExtraPages.check_app_update(app)
        check.assert_called_once_with(DEFAULT_UPDATE_MANIFEST,current_version=VERSION,
                                      trusted_hosts={'raw.githubusercontent.com',DEFAULT_UPDATE_HOSTS})
        save.assert_called_once()

    def test_empty_saved_update_feed_disables_check(self):
        app=SimpleNamespace(settings={'update_manifest':''})
        with patch('modkit.downloads.check_update') as check, patch('launcher.pages.messagebox.showinfo'):
            ExtraPages.check_app_update(app)
        check.assert_not_called()
