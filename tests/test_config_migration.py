import unittest
import os
import json
import tempfile
from app.config_manager import ConfigManager, PresetConfig, DEFAULT_CONFIG

class TestConfigMigration(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.preset_path = os.path.join(self.tmp_dir, "test_preset.json")
        self.cm = ConfigManager(self.preset_path)

    def test_migrate_monitor_to_areas(self):
        # Setup legacy preset
        legacy_data = {
            "monitor": [
                {"left": 0, "top": 0, "width": 100, "height": 100}, # Area 1
                None,
                {"left": 50, "top": 50, "width": 50, "height": 50}  # Area 3 (Manual)
            ],
            "subtitle_colors": ["#ff0000"]
        }
        
        with open(self.preset_path, 'w') as f:
            json.dump(legacy_data, f)
            
        # Load (triggers migration)
        data = self.cm.load_preset(self.preset_path)
        
        self.assertTrue(hasattr(data, 'areas'))
        areas = data.areas
        self.assertEqual(len(areas), 2)
        
        # Check Area 1
        a1 = next((a for a in areas if a.id == 1), None)
        self.assertIsNotNone(a1)
        self.assertEqual(a1.type, 'continuous')
        self.assertEqual(a1.colors, ["#ff0000"])
        self.assertEqual(a1.rect['width'], 100)
        
        # Check Area 2 (Converted from old Area 3)
        a2 = next((a for a in areas if a.id == 2), None)
        self.assertIsNotNone(a2)
        self.assertEqual(a2.type, 'manual')
        self.assertEqual(a2.rect['width'], 50)

    def test_save_preserves_areas(self):
        data = {
            "areas": [
                {"id": 1, "type": "continuous", "rect": {}, "hotkey": "", "colors": []}
            ]
        }
        self.cm.save_preset(self.preset_path, PresetConfig._from_dict(data))
        
        reloaded = self.cm.load_preset(self.preset_path)
        self.assertEqual(len(reloaded.areas), 1)

if __name__ == '__main__':
    unittest.main()
