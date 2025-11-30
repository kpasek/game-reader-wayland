import json
import os
from typing import Dict, Any, List, Optional

APP_CONFIG_FILE = 'app_config.json'

DEFAULT_CONFIG = {
    'recent_presets': [],
    'last_regex': r"",
    'ocr_grayscale': False,
    'ocr_contrast': False,
    'last_resolution_key': 'Niestandardowa',
    'hotkey_start_stop': '<ctrl>+<f5>',
    'hotkey_area3': '<ctrl>+<f6>'
}

DEFAULT_PRESET_CONTENT = {
    "audio_dir": "audio",
    "text_file_path": "subtitles.txt",
    "names_file_path": "names.txt",
    "monitor": [],
    "resolution": "1920x1080",
    "subtitle_mode": "Full Lines",
    "ocr_scale_factor": 1.0,
    "capture_interval": 0.5,
    "audio_speed": 1.15,
    "audio_volume": 1.0,
    "auto_remove_names": True,
    "rerun_threshold": 50,
    "text_alignment": "Center",
    "save_logs": False
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
        path = os.path.abspath(path)
        recents = self.settings.get('recent_presets', [])
        if path in recents:
            recents.remove(path)
        recents.insert(0, path)
        self.settings['recent_presets'] = recents[:10]
        self.save_app_config()

    def get(self, key: str, default=None):
        return self.settings.get(key, default)

    # --- Obsługa Presetu (Profilu) ---

    def ensure_preset_exists(self, directory: str) -> str:
        """Tworzy lektor.json w katalogu, jeśli nie istnieje."""
        path = os.path.join(directory, "lektor.json")
        if not os.path.exists(path):
            try:
                with open(path, 'w', encoding='utf-8') as f:
                    json.dump(DEFAULT_PRESET_CONTENT, f, indent=4)
            except Exception as e:
                print(f"Błąd tworzenia lektor.json: {e}")
        return path

    @staticmethod
    def _to_absolute(base_dir: str, path: str) -> str:
        if not path: return ""
        if os.path.isabs(path): return path
        return os.path.normpath(os.path.join(base_dir, path))

    @staticmethod
    def _to_relative(base_dir: str, path: str) -> str:
        if not path: return ""
        try:
            return os.path.relpath(path, base_dir)
        except ValueError:
            return path

    @classmethod
    def load_preset(cls, path: str) -> Dict[str, Any]:
        if not os.path.exists(path):
            return {}
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            base_dir = os.path.dirname(os.path.abspath(path))
            for key in ['audio_dir', 'text_file_path', 'names_file_path']:
                if key in data and isinstance(data[key], str):
                    data[key] = cls._to_absolute(base_dir, data[key])

            return data
        except Exception:
            return {}

    @classmethod
    def save_preset(cls, path: str, data: Dict[str, Any]):
        try:
            save_data = data.copy()
            base_dir = os.path.dirname(os.path.abspath(path))

            for key in ['audio_dir', 'text_file_path', 'names_file_path']:
                if key in save_data and isinstance(save_data[key], str):
                    save_data[key] = cls._to_relative(base_dir, save_data[key])

            with open(path, 'w', encoding='utf-8') as f:
                json.dump(save_data, f, indent=4)
        except Exception as e:
            print(f"Błąd zapisu presetu {path}: {e}")

    @staticmethod
    def load_text_lines(path: str) -> List[str]:
        if not path or not os.path.exists(path):
            return []
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return [line.strip() for line in f if line.strip()]
        except Exception:
            return []