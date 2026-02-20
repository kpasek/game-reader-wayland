import json
import os
from typing import Dict, Any, List, Optional
from pathlib import Path
from typing import Tuple
from dataclasses import dataclass, field
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
    "save_logs": False,
    "min_line_length": 2,
    "match_score_short": 90,
    "match_score_long": 75,
    "match_len_diff_ratio": 0.30,
    "partial_mode_min_len": 20,
    "audio_speed_inc": 1.20,
    "areas": []
}


import shutil
import datetime


@dataclass
class AreaConfig:
    """Single flattened dataclass representing an Area including per-area settings.

    This replaces the previous split between `AreaSettings` and `AreaConfig`.
    Attributes that used to live in `AreaSettings` are now top-level fields
    on the area object. For persistence we still produce/consume the familiar
    dict structure (with a nested `settings` key) but runtime code should
    prefer direct attribute access (e.g. `area.text_thickening`).
    """
    id: int = 0
    type: str = "manual"
    rect: Dict[str, int] = field(default_factory=lambda: {"left": 0, "top": 0, "width": 0, "height": 0})
    hotkey: str = ""
    name: str = ""
    enabled: bool = False
    colors: List[str] = field(default_factory=list)

    # Flattened per-area settings (previously in AreaSettings)
    text_thickening: int = 0
    subtitle_mode: str = "Full Lines"
    brightness_threshold: int = 200
    contrast: float = 0.0
    use_colors: bool = True
    color_tolerance: int = 10
    subtitle_colors: List[str] = field(default_factory=list)
    setting_mode: str = ''
    show_debug: bool = False
    scale_overrides: Dict[str, float] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: Optional[Dict[str, Any]]):
        if not d:
            return cls()
        kw: Dict[str, Any] = {}
        kw['id'] = int(d.get('id', 0))
        kw['type'] = str(d.get('type', 'manual'))
        kw['rect'] = dict(d.get('rect', {'left': 0, 'top': 0, 'width': 0, 'height': 0}))
        kw['hotkey'] = str(d.get('hotkey', '')) if d.get('hotkey') is not None else ''
        kw['name'] = str(d.get('name', '')) if d.get('name') is not None else ''
        kw['enabled'] = bool(d.get('enabled', False))
        # colors historically stored under 'colors' or 'subtitle_colors'
        kw['colors'] = list(d.get('colors', d.get('subtitle_colors', [])) or [])

        # Per-area settings may be nested under 'settings' or present at top-level
        s = d.get('settings', {}) if isinstance(d, dict) else {}
        # If some callers saved settings at top-level for convenience, prefer them
        def _pick(name, default):
            if name in d and d.get(name) is not None:
                return d.get(name)
            if isinstance(s, dict) and name in s:
                return s.get(name)
            return default

        kw['text_thickening'] = int(_pick('text_thickening', 0))
        kw['subtitle_mode'] = str(_pick('subtitle_mode', 'Full Lines'))
        kw['brightness_threshold'] = int(_pick('brightness_threshold', 200))
        kw['contrast'] = float(_pick('contrast', 0.0) or 0.0)
        kw['use_colors'] = bool(_pick('use_colors', True))
        kw['color_tolerance'] = int(_pick('color_tolerance', 10))
        subcols = _pick('subtitle_colors', d.get('subtitle_colors', []) or [])
        kw['subtitle_colors'] = list(subcols or [])
        kw['setting_mode'] = str(_pick('setting_mode', ''))
        kw['show_debug'] = bool(_pick('show_debug', False))
        kw['scale_overrides'] = dict(_pick('scale_overrides', {})) if isinstance(_pick('scale_overrides', {}), dict) else {}

        return cls(**kw)

    def to_dict(self) -> Dict[str, Any]:
        # Persist area as a flat dict: per-area settings live at the same
        # level as other area keys (no nested 'settings' key).
        out = {
            'id': self.id,
            'type': self.type,
            'rect': dict(self.rect) if isinstance(self.rect, dict) else self.rect,
            'hotkey': self.hotkey,
            'name': self.name,
            'enabled': self.enabled,
            'colors': list(self.colors or []),
            'text_thickening': int(self.text_thickening),
            'subtitle_mode': str(self.subtitle_mode),
            'brightness_threshold': int(self.brightness_threshold),
            'contrast': float(self.contrast or 0.0),
            'use_colors': bool(self.use_colors),
            'color_tolerance': int(self.color_tolerance),
            'subtitle_colors': list(self.subtitle_colors or []),
            'setting_mode': str(self.setting_mode),
            'show_debug': bool(self.show_debug),
            'scale_overrides': dict(self.scale_overrides or {})
        }
        return out

    @property
    def settings(self) -> Dict[str, Any]:
        # Backwards helper for callers that still expect `.settings`.
        # Returns only the per-area settings as a plain dict.
        td = self.to_dict()
        keys = ['text_thickening', 'subtitle_mode', 'brightness_threshold', 'contrast', 'use_colors', 'color_tolerance', 'subtitle_colors', 'setting_mode', 'show_debug', 'scale_overrides']
        return {k: td.get(k) for k in keys}


class ConfigManager:
    """Zarządza ładowaniem i zapisywaniem głównej konfiguracji aplikacji oraz presetów."""

    def __init__(self, preset_path: Optional[str] = None):
        # Minimal constructor: store preset path and optionally display resolution
        self.preset_cache = None
        self.preset_path = preset_path
        self.display_resolution: Optional[Tuple[int, int]] = None
        self.settings = DEFAULT_CONFIG.copy()
        self.load_app_config()

    # --------------------- Typed accessors (properties) ---------------------
    # These provide attribute-style access instead of using raw dict keys.
    def _current_preset(self) -> Dict[str, Any]:
        """Helper returning the currently loaded preset dict (may be empty)."""
        p = self.load_preset(self.preset_path) if self.preset_path else self.load_preset()
        if p is None:
            return {}
        return p

    # App-level settings
    @property
    def hotkey_start_stop(self) -> str:
        return self.settings.get('hotkey_start_stop', DEFAULT_CONFIG.get('hotkey_start_stop'))

    @hotkey_start_stop.setter
    def hotkey_start_stop(self, value: str):
        self.settings['hotkey_start_stop'] = value
        self.save_app_config()

    @property
    def capture_interval(self) -> float:
        return float(self._current_preset().get('capture_interval', DEFAULT_PRESET_CONTENT.get('capture_interval', 0.5)))

    @capture_interval.setter
    def capture_interval(self, value: float):
        data = self._current_preset()
        data['capture_interval'] = float(value)
        if self.preset_path:
            self.save_preset(self.preset_path, data)

    @property
    def similarity(self) -> float:
        # similarity historically used as percent (e.g. 5)
        return float(self._current_preset().get('similarity', self.settings.get('similarity', 5)))

    @similarity.setter
    def similarity(self, value: float):
        data = self._current_preset()
        data['similarity'] = float(value)
        if self.preset_path:
            self.save_preset(self.preset_path, data)

    @property
    def partial_mode_min_len(self) -> int:
        return int(self._current_preset().get('partial_mode_min_len', DEFAULT_PRESET_CONTENT.get('partial_mode_min_len', 25)))

    @partial_mode_min_len.setter
    def partial_mode_min_len(self, value: int):
        data = self._current_preset()
        data['partial_mode_min_len'] = int(value)
        if self.preset_path:
            self.save_preset(self.preset_path, data)

    @property
    def match_len_diff_ratio(self) -> float:
        return float(self._current_preset().get('match_len_diff_ratio', DEFAULT_PRESET_CONTENT.get('match_len_diff_ratio', 0.25)))

    @match_len_diff_ratio.setter
    def match_len_diff_ratio(self, value: float):
        data = self._current_preset()
        data['match_len_diff_ratio'] = float(value)
        if self.preset_path:
            self.save_preset(self.preset_path, data)

    @property
    def match_score_short(self) -> int:
        return int(self._current_preset().get('match_score_short', DEFAULT_PRESET_CONTENT.get('match_score_short', 90)))

    @match_score_short.setter
    def match_score_short(self, value: int):
        data = self._current_preset()
        data['match_score_short'] = int(value)
        if self.preset_path:
            self.save_preset(self.preset_path, data)

    @property
    def match_score_long(self) -> int:
        return int(self._current_preset().get('match_score_long', DEFAULT_PRESET_CONTENT.get('match_score_long', 75)))

    @match_score_long.setter
    def match_score_long(self, value: int):
        data = self._current_preset()
        data['match_score_long'] = int(value)
        if self.preset_path:
            self.save_preset(self.preset_path, data)

    @property
    def audio_speed_inc(self) -> float:
        return float(self._current_preset().get('audio_speed_inc', DEFAULT_PRESET_CONTENT.get('audio_speed_inc', 1.2)))

    @audio_speed_inc.setter
    def audio_speed_inc(self, value: float):
        data = self._current_preset()
        data['audio_speed_inc'] = float(value)
        if self.preset_path:
            self.save_preset(self.preset_path, data)

    # Additional preset properties used across the app
    @property
    def ocr_scale_factor(self) -> float:
        return float(self._current_preset().get('ocr_scale_factor', DEFAULT_PRESET_CONTENT.get('ocr_scale_factor', 0.5)))

    @ocr_scale_factor.setter
    def ocr_scale_factor(self, value: float):
        data = self._current_preset()
        data['ocr_scale_factor'] = float(value)
        if self.preset_path:
            self.save_preset(self.preset_path, data)

    @property
    def save_logs(self) -> bool:
        return bool(self._current_preset().get('save_logs', DEFAULT_PRESET_CONTENT.get('save_logs', False)))

    @save_logs.setter
    def save_logs(self, value: bool):
        data = self._current_preset()
        data['save_logs'] = bool(value)
        if self.preset_path:
            self.save_preset(self.preset_path, data)

    @property
    def min_line_length(self) -> int:
        return int(self._current_preset().get('min_line_length', DEFAULT_PRESET_CONTENT.get('min_line_length', 3)))

    @min_line_length.setter
    def min_line_length(self, value: int):
        data = self._current_preset()
        data['min_line_length'] = int(value)
        if self.preset_path:
            self.save_preset(self.preset_path, data)

    @property
    def text_file_path(self) -> str:
        return str(self._current_preset().get('text_file_path', DEFAULT_PRESET_CONTENT.get('text_file_path', 'subtitles.txt')))

    @text_file_path.setter
    def text_file_path(self, value: str):
        data = self._current_preset()
        data['text_file_path'] = str(value)
        if self.preset_path:
            self.save_preset(self.preset_path, data)

    @property
    def audio_dir(self) -> str:
        return str(self._current_preset().get('audio_dir', DEFAULT_PRESET_CONTENT.get('audio_dir', 'audio')))

    @audio_dir.setter
    def audio_dir(self, value: str):
        data = self._current_preset()
        data['audio_dir'] = str(value)
        if self.preset_path:
            self.save_preset(self.preset_path, data)

    @property
    def audio_ext(self) -> str:
        return str(self._current_preset().get('audio_ext', DEFAULT_PRESET_CONTENT.get('audio_ext', '.mp3')))

    @audio_ext.setter
    def audio_ext(self, value: str):
        data = self._current_preset()
        data['audio_ext'] = str(value)
        if self.preset_path:
            self.save_preset(self.preset_path, data)

    @property
    def text_color_mode(self) -> str:
        return str(self._current_preset().get('text_color_mode', DEFAULT_PRESET_CONTENT.get('text_color_mode', 'Light')))

    @text_color_mode.setter
    def text_color_mode(self, value: str):
        data = self._current_preset()
        data['text_color_mode'] = str(value)
        if self.preset_path:
            self.save_preset(self.preset_path, data)

    @property
    def brightness_threshold(self) -> int:
        return int(self._current_preset().get('brightness_threshold', self.settings.get('brightness_threshold', 200)))

    @brightness_threshold.setter
    def brightness_threshold(self, value: int):
        data = self._current_preset()
        data['brightness_threshold'] = int(value)
        if self.preset_path:
            self.save_preset(self.preset_path, data)

    @property
    def color_tolerance(self) -> int:
        return int(self._current_preset().get('color_tolerance', DEFAULT_PRESET_CONTENT.get('color_tolerance', 10)))

    @color_tolerance.setter
    def color_tolerance(self, value: int):
        data = self._current_preset()
        data['color_tolerance'] = int(value)
        if self.preset_path:
            self.save_preset(self.preset_path, data)

    @property
    def text_thickening(self) -> int:
        return int(self._current_preset().get('text_thickening', DEFAULT_PRESET_CONTENT.get('text_thickening', 0)))

    @text_thickening.setter
    def text_thickening(self, value: int):
        data = self._current_preset()
        data['text_thickening'] = int(value)
        if self.preset_path:
            self.save_preset(self.preset_path, data)

    @property
    def subtitle_colors(self) -> List[str]:
        return list(self._current_preset().get('subtitle_colors', DEFAULT_PRESET_CONTENT.get('subtitle_colors', [])))

    @subtitle_colors.setter
    def subtitle_colors(self, value: List[str]):
        data = self._current_preset()
        data['subtitle_colors'] = list(value) if value is not None else []
        if self.preset_path:
            self.save_preset(self.preset_path, data)

    @property
    def auto_remove_names(self) -> bool:
        return bool(self._current_preset().get('auto_remove_names', DEFAULT_PRESET_CONTENT.get('auto_remove_names', True)))

    @auto_remove_names.setter
    def auto_remove_names(self, value: bool):
        data = self._current_preset()
        data['auto_remove_names'] = bool(value)
        if self.preset_path:
            self.save_preset(self.preset_path, data)
            
    @property
    def show_debug(self) -> bool:
        return bool(self._current_preset().get('show_debug', DEFAULT_PRESET_CONTENT.get('show_debug', False)))

    @show_debug.setter
    def show_debug(self, value: bool):
        data = self._current_preset()
        data['show_debug'] = bool(value)
        if self.preset_path:
            self.save_preset(self.preset_path, data)


    def backup_preset(self, path: str) -> Optional[str]:
        """Tworzy kopię zapasową pliku preset z timestampem."""
        if not path or not os.path.exists(path):
            return None
        
        try:
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = f"{path}.{timestamp}.bak"
            shutil.copy2(path, backup_path)
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

    # Note: `update_setting` removed; use `config_mgr.settings[...] = val` and `config_mgr.save_app_config()`.

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
        # Deprecated compatibility wrapper — prefer using `get_preset_for_display`
        return self.get_preset_for_display(path, dest_resolution)

    def get_preset_for_display(self, path: Optional[str] = None, dest_resolution: Optional[Tuple[int, int]] = None) -> Dict[str, Any]:
        """Return a preset dict where `areas` rects are scaled from canonical 4K to
        the provided `dest_resolution` or the manager's `display_resolution`.

        This does NOT modify the stored preset on disk; it returns a deep copy with
        scaled rects suitable for immediate use by UI and processing code.
        """
        data = self.load_preset(path)
        if not data:
            return {}
        import copy as _copy
        out = _copy.deepcopy(data)
        try:
            if dest_resolution is None:
                dest_resolution = self.display_resolution
            if dest_resolution is None:
                # No scaling requested — return raw copy
                return out
            dest_w, dest_h = dest_resolution
            areas = out.get('areas', [])
            for a in areas:
                if not a or 'rect' not in a:
                    continue
                try:
                    a['rect'] = scale_utils.scale_rect_to_physical(a['rect'], dest_w, dest_h)
                except Exception:
                    # keep original rect on failure
                    pass
            out['areas'] = areas
        except Exception:
            pass
        return out

    # High-level helpers for area-level access
    def get_areas(self) -> List['AreaConfig']:
        """Return the list of areas (as `AreaConfig`) scaled to the manager's `display_resolution`.

        This centralizes scaling so callers don't implement scaling logic. The
        returned objects are typed `AreaConfig` instances and safe to use in
        processing and UI code.
        """
        p = self.get_preset_for_display()
        if not p:
            return []
        raw = p.get('areas', []) or []
        out: List[AreaConfig] = []
        try:
            for a in raw:
                try:
                    out.append(AreaConfig.from_dict(a if isinstance(a, dict) else {}))
                except Exception:
                    # fallback: create empty AreaConfig for malformed entries
                    out.append(AreaConfig())
        except Exception:
            return []
        return out

    def get_area_setting(self, area_or_id, key: str, default=None):
        """Return a single per-area setting value from the authoritative areas list.

        `area_or_id` may be an `AreaConfig` instance, an integer id, or a dict
        representation (as stored in presets). This always reads from
        `self.get_areas()` so ConfigManager remains the source of truth.
        """
        try:
            areas = self.get_areas() or []
            target_id = None
            if isinstance(area_or_id, int):
                target_id = area_or_id
            else:
                try:
                    if isinstance(area_or_id, AreaConfig):
                        target_id = int(area_or_id.id)
                    else:
                        # assume mapping-like
                        target_id = int(area_or_id.get('id'))
                except Exception:
                    target_id = None

            for a in areas:
                if target_id is not None and a.id == target_id:
                    return getattr(a, key, default)
            # Fallback: if area_or_id is an AreaConfig-like instance use it
            if hasattr(area_or_id, key):
                return getattr(area_or_id, key)
        except Exception:
            pass
        return default

    def get_area_settings(self, area_or_id) -> Dict[str, Any]:
        """Return dict of known per-area settings read via ConfigManager.

        Always reads values through `get_area_setting` so callers access
        settings only via the manager.
        """
        keys = ['text_thickening', 'subtitle_mode', 'brightness_threshold', 'contrast', 'use_colors', 'color_tolerance', 'subtitle_colors', 'setting_mode', 'show_debug', 'scale_overrides']
        out: Dict[str, Any] = {}
        for k in keys:
            v = self.get_area_setting(area_or_id, k, None)
            if v is not None:
                out[k] = v
        return out

    def get_area(self, index: int):
        """Return an `AreaConfig` by zero-based list index.

        This method treats the argument strictly as a list index into the
        array returned by `get_areas()`. If the index is out of range or the
        argument is not an int, `None` is returned. Callers that already
        have an `AreaConfig` instance should pass the index of that area.
        """
        try:
            areas = self.get_areas() or []
            if not isinstance(index, int):
                return None
            if 0 <= index < len(areas):
                return areas[index]
        except Exception:
            pass
        return None

    def set_areas_from_display(self, areas: List[Dict[str, Any]], src_resolution: Optional[Tuple[int, int]] = None):
        """Accept areas expressed in display coordinates and persist them (scaling to canonical 4K).

        Requires `self.preset_path` to be set and a source resolution either provided
        or available via `self.display_resolution`.
        """
        if not self.preset_path:
            raise ValueError("ConfigManager has no preset_path configured")
        if src_resolution is None:
            if self.display_resolution is None:
                raise ValueError("No source resolution provided and ConfigManager.display_resolution is not set")
            src_resolution = self.display_resolution
        # Accept either raw dicts or AreaConfig instances
        serializable_areas = []
        for a in areas or []:
            if isinstance(a, AreaConfig):
                serializable_areas.append(a.to_dict())
            else:
                serializable_areas.append(a)
        data = {'areas': serializable_areas}
        self.save_preset_from_screen(self.preset_path, data, src_resolution)

    def set_areas(self, areas: List[Dict[str, Any]]):
        """Persist areas provided in current display coordinates.

        This is a thin wrapper that uses `self.display_resolution` as the
        source resolution and delegates to `set_areas_from_display`.
        """
        if self.display_resolution is None:
            raise ValueError("ConfigManager.display_resolution is not set")
        return self.set_areas_from_display(areas, src_resolution=self.display_resolution)

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
                    # If object exposes `to_dict`, prefer that for serialization
                    # Prefer `.to_dict()` for custom types (AreaSettings etc.).
                    try:
                        fn = obj.to_dict
                        if callable(fn):
                            return sanitize(fn(), memo)
                    except Exception:
                        pass
                    try:
                        return obj.item()
                    except Exception:
                        pass
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

    def load_text_lines(self, path: Optional[str] = None) -> List[str]:
        """Load text lines from `path` or from the current preset's `text_file_path`.

        Usage:
        - `load_text_lines(path)` reads the provided file path.
        - `load_text_lines()` reads the preset's `text_file_path`.
        """
        try:
            if path is None:
                path = self.text_file_path
            if not path or not os.path.exists(path):
                return []
            with open(path, 'r', encoding='utf-8') as f:
                return [line.strip() for line in f]
        except Exception:
            return []