import json
import os
from typing import Dict, Any, List, Optional
from pathlib import Path
from typing import Tuple
from app import scale_utils

APP_CONFIG_FILE = Path.home() / '.config' / 'app_config.json'

DEFAULT_CONFIG = {
    'recent_presets': [],
    'last_regex': r"",
    'last_resolution_key': '1920x1080',
    'hotkey_start_stop': '<f2>',
    'hotkey_area3': '<f3>',
}

DEFAULT_PRESET_CONTENT = {
    "audio_dir": "audio",
    "text_file_path": "subtitles.txt",
    "monitor": [],
    # Domyślny tryb dopasowania napisów (musi być zgodny z MATCH_MODE_FULL z matcher.py)
    "subtitle_mode": "Full Lines",
    "text_color_mode": "Light",
    "ocr_scale_factor": 0.5,
    "capture_interval": 0.5,
    "audio_speed": 1.15,
    "audio_volume": 1.0,
    "audio_ext": ".mp3",
    "auto_remove_names": True,
    "text_alignment": "Center",
    "save_logs": False,
    "min_line_length": 3,
    "match_score_short": 90,
    "match_score_long": 75,
    "match_len_diff_ratio": 0.30,
    "partial_mode_min_len": 25,
    "audio_speed_inc": 1.20,
    "text_thickening": 0,
    "subtitle_colors": [],
    "color_tolerance": 10,
    "areas": []
}


import shutil
import datetime

class ConfigManager:
    """Zarządza ładowaniem i zapisywaniem głównej konfiguracji aplikacji oraz presetów."""

    def __init__(self, preset_path: Optional[str] = None):
        self.preset_cache = None
        self.preset_path = preset_path
        self.settings = DEFAULT_CONFIG.copy()
        self.load_app_config()

    def backup_preset(self, path: str) -> Optional[str]:
        """Tworzy kopię zapasową pliku preset z timestampem."""
        if not path or not os.path.exists(path):
            return None
        
        try:
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = f"{path}.{timestamp}.bak"
            shutil.copy2(path, backup_path)
            print(f"Utworzono kopię zapasową ustawień: {backup_path}")
            return backup_path
        except Exception as e:
            print(f"Błąd tworzenia kopii zapasowej: {e}")
            return None

    def import_gr_preset(self, import_path: str, target_preset_path: str) -> bool:
        """
        Importuje ustawienia (głównie obszar) z pliku konfiguracyjnego wersji Windows.
        Przeskalowuje obszar z rozdzielczości źródłowej na 4K (3840x2160).
        """
        if not os.path.exists(import_path) or not target_preset_path:
            return False

        try:
            with open(import_path, 'r', encoding='utf-8') as f:
                win_data = json.load(f)

            # 1. Pobierz rozdzielczość źródłową (np. "2560x1440")
            res_str = win_data.get("resolution", "1920x1080")
            if "x" not in res_str:
                res_str = "1920x1080"

            src_w, src_h = map(int, res_str.lower().split('x'))

            # 2. Ustal rozdzielczość docelową (Lektor Wayland używa 4K jako bazy)
            tgt_w, tgt_h = 3840, 2160

            scale_x = tgt_w / src_w
            scale_y = tgt_h / src_h

            # 3. Pobierz i przelicz obszar monitora
            win_monitor = win_data.get("monitor", {})
            # Format Windows to zazwyczaj dict, Lektor Wayland to lista dictów
            if not win_monitor or not isinstance(win_monitor, dict):
                print("Brak poprawnego pola 'monitor' w pliku importu.")
                return False

            new_monitor = {
                "left": int(win_monitor.get("left", 0) * scale_x),
                "top": int(win_monitor.get("top", 0) * scale_y),
                "width": int(win_monitor.get("width", 0) * scale_x),
                "height": int(win_monitor.get("height", 0) * scale_y)
            }

            # 4. Aktualizuj obecny preset
            current_data = self.load_preset(target_preset_path)

            # Nadpisz obszary - ustawiamy jako pierwszy i jedyny obszar
            current_data["monitor"] = [new_monitor]

            # Opcjonalnie: Importuj inne ustawienia jeśli pasują, np. minimalna długość linii
            if "min_line_len" in win_data:
                current_data["min_line_length"] = win_data.get(
                    "min_line_len")  # Różnica w nazwie klucza (length vs len)

            self.save_preset(target_preset_path, current_data)
            return True

        except Exception as e:
            print(f"Błąd importu presetu Windows: {e}")
            return False

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

    def load_preset(self, path: Optional[str] = None) -> Dict[str, Any]:
        if path and path != self.preset_path:
            self.preset_cache = None
            self.preset_path = path

        if self.preset_cache is not None:
            return self.preset_cache
        if not path:
            path = self.preset_path
        else:
            self.preset_path = path
        if not os.path.exists(path):
            return {}
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # Normal load; no debug logs

            # Uzupełnianie brakujących kluczy domyślnymi
            for k, v in DEFAULT_PRESET_CONTENT.items():
                if k not in data:
                    data[k] = v

            # Migracja starej konfiguracji (monitor -> areas)
            if not data.get('areas') and data.get('monitor'):
                self._migrate_legacy_areas(data)

            base_dir = os.path.dirname(os.path.abspath(path))
            for key in ['audio_dir', 'text_file_path']:
                if key in data and isinstance(data[key], str):
                    data[key] = self._to_absolute(base_dir, data[key])
            self.preset_cache = data
            return data
        except Exception:
            return {}

    def _migrate_legacy_areas(self, data: Dict[str, Any]):
        """Konwertuje stare ustawienia 'monitor' i 'subtitle_colors' na nową strukturę 'areas'."""
        monitors = data.get('monitor', [])
        colors = data.get('subtitle_colors', [])
        
        new_areas = []

        # Area 1 (Zawsze Continuous)
        if len(monitors) > 0 and monitors[0]:
            new_areas.append({
                "id": 1,
                "type": "continuous",
                "rect": monitors[0],
                "hotkey": "",
                "colors": colors  # Przypisz globalne kolory do obszaru 1
            })
        
        # Area 3 (W starym kodzie index 2 był "Area 3" - manualny)
        # Zakładamy, że jeśli istniał, to był manualny (bo tak działał ReaderThread)
        if len(monitors) > 2 and monitors[2]:
            new_areas.append({
                "id": 2, # Zmieniamy ID na kolejne wolne
                "type": "manual",
                "rect": monitors[2],
                "hotkey": self.settings.get('hotkey_area3', '<f3>'), # Próbujemy pobrać stary hotkey
                "colors": []
            })
            
        data['areas'] = new_areas

    # --- New helpers for scaling areas ---
    def get_preset_for_resolution(self, path: Optional[str], dest_resolution: Tuple[int, int]) -> Dict[str, Any]:
        """Return preset dict where `areas` rects are scaled from canonical 4K to dest_resolution.

        This does NOT modify the stored preset on disk; it returns a copy with scaled rects suitable
        for immediate use by UI and processing code.
        """
        data = self.load_preset(path)
        if not data:
            return {}
        # Work on a deep-ish copy for safety
        import copy as _copy
        out = _copy.deepcopy(data)
        try:
            dest_w, dest_h = dest_resolution
            areas = out.get('areas', [])
            for a in areas:
                if not a or 'rect' not in a:
                    continue
                # Diagnostic log: show rect before scaling
                try:
                    print(f"[ConfigManager] get_preset_for_resolution: scaling area id={a.get('id')} rect_before={a.get('rect')} -> dest={dest_w}x{dest_h}")
                except Exception:
                    pass
                a['rect'] = scale_utils.scale_rect_to_physical(a['rect'], dest_w, dest_h)
                try:
                    print(f"[ConfigManager] get_preset_for_resolution: area id={a.get('id')} rect_after={a.get('rect')}")
                except Exception:
                    pass
            out['areas'] = areas
        except Exception:
            pass
        return out

    def normalize_areas_to_4k(self, areas: List[Dict[str, Any]], src_resolution: Tuple[int, int]) -> List[Dict[str, Any]]:
        """Convert a list of rect dicts given in src_resolution up to canonical 4K for storage."""
        src_w, src_h = src_resolution
        out = []
        try:
            for a in areas:
                if not a:
                    out.append(a)
                    continue
                # If `a` is an area dict containing 'rect', scale only the rect and keep other keys.
                if isinstance(a, dict) and 'rect' in a and isinstance(a.get('rect'), dict):
                    new_a = a.copy()
                    try:
                        new_a['rect'] = scale_utils.scale_rect_to_4k(a['rect'], src_w, src_h)
                    except Exception:
                        new_a['rect'] = a['rect']
                    out.append(new_a)
                else:
                    # If it's already a plain rect dict or unknown shape, attempt best-effort scale
                    try:
                        out.append(scale_utils.scale_rect_to_4k(a, src_w, src_h))
                    except Exception:
                        out.append(a)
            return out
        except Exception:
            return areas

    def save_preset_from_screen(self, path: str, data: Dict[str, Any], src_resolution: Tuple[int, int]):
        """Accept preset data where `areas` and `monitor` are in screen/physical coords
        (src_resolution). Convert them to canonical 4K and save using `save_preset`.
        This centralizes all scaling inside ConfigManager.
        """
        try:
            sd = data.copy()
            sw, sh = src_resolution
            # Normalize areas list
            if 'areas' in sd and isinstance(sd['areas'], list):
                try:
                    sd['areas'] = self.normalize_areas_to_4k(sd['areas'], (sw, sh))
                except Exception:
                    pass
            # Normalize monitor entries if present
            if 'monitor' in sd and isinstance(sd['monitor'], list):
                try:
                    sd['monitor'] = [scale_utils.scale_rect_to_4k(m, sw, sh) if m else None for m in sd['monitor']]
                except Exception:
                    pass
            # Delegate actual write to existing save_preset (expects canonical 4K)
            self.save_preset(path, sd)
        except Exception as e:
            print(f"Błąd save_preset_from_screen: {e}")

    def save_preset(self, path: Optional[str] = None, data: Dict[str, Any] = None):
        """Save preset to `path`. If `path` is None, uses `self.preset_path`.

        `data` is required. This function will update `self.preset_cache` on success.
        """
        try:
            if data is None:
                raise ValueError("save_preset requires `data` argument")
            if not path:
                path = self.preset_path
            if not path:
                raise ValueError("No path provided to save_preset and no cached preset_path available.")
            # Helper to recursively sanitize preventing recursion loops
            def sanitize(obj, memo=None):
                if memo is None:
                    memo = set()
                
                obj_id = id(obj)
                if obj_id in memo:
                    return f"<Circular Reference {type(obj).__name__}>"
                
                if isinstance(obj, dict):
                    memo.add(obj_id)
                    res = {k: sanitize(v, memo) for k, v in obj.items() if isinstance(k, str) and not k.startswith('_')}
                    memo.remove(obj_id)
                    return res
                elif isinstance(obj, list):
                    memo.add(obj_id)
                    res = [sanitize(x, memo) for x in obj]
                    memo.remove(obj_id)
                    return res
                elif isinstance(obj, (str, int, float, bool, type(None))):
                    return obj
                else:
                    # Try to convert custom types (int64 etc)
                    if hasattr(obj, 'item'): 
                         return obj.item()
                    return str(obj)

            save_data = sanitize(data)

            # (No preset-based resolution conversion — areas expected to be stored in canonical 4K)
            base_dir = os.path.dirname(os.path.abspath(path))

            for key in ['audio_dir', 'text_file_path']:
                if key in save_data and isinstance(save_data[key], str):
                    save_data[key] = self._to_relative(base_dir, save_data[key])

            with open(path, 'w', encoding='utf-8') as f:
                json.dump(save_data, f, indent=4)
            # Clear cache and reload so load_preset will normalize paths (e.g., text_file_path)
            self.preset_cache = None
            try:
                self.load_preset(path)
            except Exception:
                # If reload fails, leave preset_cache as None; caller can handle
                self.preset_cache = None
        except Exception as e:
            print(f"Błąd zapisu presetu {path}: {e}")

    @staticmethod
    def load_text_lines(path: str) -> List[str]:
        if not path or not os.path.exists(path):
            return []
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return [line.strip() for line in f]
        except Exception:
            return []