import json
import os
from typing import Dict, Any, List, Optional

APP_CONFIG_FILE = 'app_config.json'

DEFAULT_CONFIG = {
    'recent_presets': [],
    'last_regex': r"",
    'subtitle_mode': 'Full Lines',
    'ocr_scale_factor': 1.0,
    'ocr_grayscale': False,
    'ocr_contrast': False,
    'last_resolution_key': 'Niestandardowa'
}


class ConfigManager:
    """Zarządza ładowaniem i zapisywaniem głównej konfiguracji aplikacji oraz presetów."""

    def __init__(self):
        self.settings = DEFAULT_CONFIG.copy()
        self.load_app_config()

    def load_app_config(self):
        try:
            if os.path.exists(APP_CONFIG_FILE):
                with open(APP_CONFIG_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.settings.update(data)
        except Exception as e:
            print(f"Błąd ładowania konfigu: {e}")

    def save_app_config(self):
        try:
            with open(APP_CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.settings, f, indent=2)
        except Exception as e:
            print(f"Błąd zapisu konfigu: {e}")

    def update_setting(self, key: str, value: Any):
        self.settings[key] = value
        self.save_app_config()

    def add_recent_preset(self, path: str):
        recents = self.settings.get('recent_presets', [])
        if path in recents:
            recents.remove(path)
        recents.insert(0, path)
        self.settings['recent_presets'] = recents[:10]
        self.save_app_config()

    def get(self, key: str, default=None):
        return self.settings.get(key, default)

    # --- Obsługa Presetu (Profilu) ---

    @staticmethod
    def load_preset(path: str) -> Dict[str, Any]:
        if not os.path.exists(path):
            return {}
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {}

    @staticmethod
    def save_preset(path: str, data: Dict[str, Any]):
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            print(f"Błąd zapisu presetu {path}: {e}")

    @staticmethod
    def load_text_lines(path: str) -> List[str]:
        """Wczytuje linie z pliku tekstowego (napisy/imiona)."""
        if not path or not os.path.exists(path):
            return []
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return [line.strip() for line in f if line.strip()]
        except Exception:
            return []