import json
import tempfile
import unittest
from pathlib import Path
from modkit.asset_integrity import verify_assets

class AssetTests(unittest.TestCase):
    def test_missing_or_malformed_manifest_is_actionable(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t)
            self.assertFalse(verify_assets(root)['ok'])
            (root/'assets').mkdir();manifest=root/'assets/offline_manifest.json'
            for content in ('[]','{"sha256": []}','{"sha256": {}}','nonsense'):
                manifest.write_text(content)
                self.assertFalse(verify_assets(root)['ok'])

    def test_manifest_cannot_read_outside_bundle(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);(root/'assets').mkdir()
            for name in ('../outside','/outside','C:/outside','..\\outside'):
                (root/'assets/offline_manifest.json').write_text(json.dumps({'sha256':{name:'0'*64}}))
                self.assertFalse(verify_assets(root)['ok'])
