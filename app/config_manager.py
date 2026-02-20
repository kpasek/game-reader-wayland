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
    """Single flattened dataclass representing an Area including per-area settings."""
    id: int = 0
    type: str = "manual"
    rect: Dict[str, int] = field(default_factory=lambda: {"left": 0, "top": 0, "width": 0, "height": 0})
    hotkey: str = ""
    name: str = ""
    enabled: bool = False
    colors: List[str] = field(default_factory=list)

    # Flattened per-area settings
    text_thickening: int = 0
    subtitle_mode: str = "Full Lines"
    brightness_threshold: int = 200
    contrast: float = 0.0
    use_colors: bool = True
    color_tolerance: int = 10
    setting_mode: str = ''
    show_debug: bool = False

    def _to_dict(self) -> Dict[str, Any]:
        """Returns a full dictionary representation of the AreaConfig for persistence."""
        return {
            "id": int(self.id),
            "type": str(self.type),
            "rect": dict(self.rect),
            "hotkey": str(self.hotkey or ''),
            "name": str(self.name or ''),
            "enabled": bool(self.enabled),
            "colors": list(self.colors or []),
            "text_thickening": int(self.text_thickening),
            "subtitle_mode": str(self.subtitle_mode),
            "brightness_threshold": int(self.brightness_threshold),
            "contrast": float(self.contrast or 0.0),
            "use_colors": bool(self.use_colors),
            "color_tolerance": int(self.color_tolerance),
            "setting_mode": str(self.setting_mode or ''),
            "show_debug": bool(self.show_debug)
        }

    @classmethod
    def _from_dict(cls, d: Any):
        if d is None:
            return cls()
        if isinstance(d, cls):
            return d
            
        if not isinstance(d, dict):
            return cls()

        kw: Dict[str, Any] = {}
        kw['id'] = int(d.get('id', 0))
        kw['type'] = str(d.get('type', 'manual'))
        kw['rect'] = dict(d.get('rect', {'left': 0, 'top': 0, 'width': 0, 'height': 0}))
        kw['hotkey'] = str(d.get('hotkey', '')) if d.get('hotkey') is not None else ''
        kw['name'] = str(d.get('name', '')) if d.get('name') is not None else ''
        kw['enabled'] = bool(d.get('enabled', False))
        
        # Unify colors/subtitle_colors into 'colors'
        kw['colors'] = list(d.get('colors', d.get('subtitle_colors', [])) or [])

        # Per-area settings may be nested under 'settings' or present at top-level
        s = d.get('settings', {}) if isinstance(d, dict) else {}
        def _pick(name, default):
            if isinstance(d, dict) and name in d and d.get(name) is not None:
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
        
        # If 'colors' still empty, check 'subtitle_colors' in settings
        if not kw['colors']:
            kw['colors'] = list(_pick('subtitle_colors', []) or [])
            
        kw['setting_mode'] = str(_pick('setting_mode', ''))
        kw['show_debug'] = bool(_pick('show_debug', False))

        return cls(**kw)


@dataclass
class PresetConfig:
    audio_speed: float = 1.15
    audio_volume: float = 1.0
    audio_dir: str = "audio"
    text_file_path: str = "subtitles.txt"
    subtitle_mode: str = "Full Lines"
    text_color_mode: str = "Light"
    ocr_scale_factor: float = 0.5
    capture_interval: float = 0.5
    audio_ext: str = ".mp3"
    auto_remove_names: bool = True
    save_logs: bool = False
    min_line_length: int = 2
    match_score_short: int = 90
    match_score_long: int = 75
    match_len_diff_ratio: float = 0.30
    partial_mode_min_len: int = 20
    audio_speed_inc: float = 1.20
    similarity: float = 5.0
    regex_mode_name: str = ""
    regex_pattern: str = ""
    
    # Global defaults for new areas
    text_thickening: int = 0
    brightness_threshold: int = 200
    contrast: float = 0.0
    use_colors: bool = True
    color_tolerance: int = 10
    subtitle_colors: List[str] = field(default_factory=list)
    show_debug: bool = False
    
    areas: List[AreaConfig] = field(default_factory=list)

    @classmethod
    def _from_dict(cls, d: Dict[str, Any]) -> 'PresetConfig':
        kw = {}
        for f in cls.__dataclass_fields__:
            if f == 'areas':
                # Convert list of dicts to list of AreaConfig
                raw = d.get('areas', d.get('monitor', []))
                kw['areas'] = [AreaConfig._from_dict(a) if isinstance(a, dict) else a for a in raw if a]
            elif f == 'subtitle_colors':
                # Handle both naming conventions
                kw['subtitle_colors'] = list(d.get('subtitle_colors', d.get('colors', [])) or [])
            elif f in d:
                kw[f] = d[f]
        return cls(**kw)

    def _to_dict(self) -> Dict[str, Any]:
        res = {}
        for f in self.__dataclass_fields__:
            val = getattr(self, f)
            if f == 'areas':
                res['areas'] = [a._to_dict() if hasattr(a, '_to_dict') else a for a in val]
            else:
                res[f] = val
        return res



class ConfigManager:
    """Zarządza ładowaniem i zapisywaniem głównej konfiguracji aplikacji oraz presetów."""

    def __init__(self, preset_path: Optional[str] = None):
        # Minimal constructor: store preset path and optionally display resolution
        self.preset_cache: Optional[PresetConfig] = None
        self.preset_path = preset_path
        self.display_resolution: Optional[Tuple[int, int]] = None
        self.settings = DEFAULT_CONFIG.copy()
        self.load_app_config()

    # --------------------- Typed accessors (properties) ---------------------
    # These provide attribute-style access instead of using raw dict keys.
    def _get_preset_obj(self) -> PresetConfig:
        """Helper returning the currently loaded preset object."""
        if self.preset_cache is not None:
            return self.preset_cache
        p = self.load_preset(self.preset_path) if self.preset_path else self.load_preset()
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
    def last_resolution_key(self) -> str:
        return self.settings.get('last_resolution_key', DEFAULT_CONFIG.get('last_resolution_key', '1920x1080'))

    @last_resolution_key.setter
    def last_resolution_key(self, value: str):
        self.settings['last_resolution_key'] = value
        self.save_app_config()

    @property
    def last_regex_mode(self) -> str:
        return self.settings.get('last_regex_mode', "Standard (Imię: Dialog)")

    @last_regex_mode.setter
    def last_regex_mode(self, value: str):
        self.settings['last_regex_mode'] = value
        self.save_app_config()

    @property
    def last_custom_regex(self) -> str:
        return self.settings.get('last_custom_regex', "")

    @last_custom_regex.setter
    def last_custom_regex(self, value: str):
        self.settings['last_custom_regex'] = value
        self.save_app_config()

    @property
    def recent_presets_list(self) -> List[str]:
        """Returns valid paths from recent_presets."""
        import os
        return [p for p in self.settings.get('recent_presets', []) if os.path.exists(p)]

    @property
    def capture_interval(self) -> float:
        return self._get_preset_obj().capture_interval

    @capture_interval.setter
    def capture_interval(self, value: float):
        obj = self._get_preset_obj()
        obj.capture_interval = float(value)
        if self.preset_path:
            self.save_preset(self.preset_path, obj)

    @property
    def partial_mode_min_len(self) -> int:
        return self._get_preset_obj().partial_mode_min_len

    @partial_mode_min_len.setter
    def partial_mode_min_len(self, value: int):
        obj = self._get_preset_obj()
        obj.partial_mode_min_len = int(value)
        if self.preset_path:
            self.save_preset(self.preset_path, obj)

    @property
    def match_len_diff_ratio(self) -> float:
        return self._get_preset_obj().match_len_diff_ratio

    @match_len_diff_ratio.setter
    def match_len_diff_ratio(self, value: float):
        obj = self._get_preset_obj()
        obj.match_len_diff_ratio = float(value)
        if self.preset_path:
            self.save_preset(self.preset_path, obj)

    @property
    def match_score_short(self) -> int:
        return self._get_preset_obj().match_score_short

    @match_score_short.setter
    def match_score_short(self, value: int):
        obj = self._get_preset_obj()
        obj.match_score_short = int(value)
        if self.preset_path:
            self.save_preset(self.preset_path, obj)

    @property
    def match_score_long(self) -> int:
        return self._get_preset_obj().match_score_long

    @match_score_long.setter
    def match_score_long(self, value: int):
        obj = self._get_preset_obj()
        obj.match_score_long = int(value)
        if self.preset_path:
            self.save_preset(self.preset_path, obj)

    @property
    def audio_speed_inc(self) -> float:
        return self._get_preset_obj().audio_speed_inc

    @audio_speed_inc.setter
    def audio_speed_inc(self, value: float):
        obj = self._get_preset_obj()
        obj.audio_speed_inc = float(value)
        if self.preset_path:
            self.save_preset(self.preset_path, obj)

    @property
    def audio_speed(self) -> float:
        return self._get_preset_obj().audio_speed

    @audio_speed.setter
    def audio_speed(self, value: float):
        obj = self._get_preset_obj()
        obj.audio_speed = float(value)
        if self.preset_path:
            self.save_preset(self.preset_path, obj)

    @property
    def audio_volume(self) -> float:
        return self._get_preset_obj().audio_volume

    @audio_volume.setter
    def audio_volume(self, value: float):
        obj = self._get_preset_obj()
        obj.audio_volume = float(value)
        if self.preset_path:
            self.save_preset(self.preset_path, obj)

    @property
    def similarity(self) -> float:
        return self._get_preset_obj().similarity

    @similarity.setter
    def similarity(self, value: float):
        obj = self._get_preset_obj()
        obj.similarity = float(value)
        if self.preset_path:
            self.save_preset(self.preset_path, obj)

    @property
    def ocr_scale_factor(self) -> float:
        return self._get_preset_obj().ocr_scale_factor

    @ocr_scale_factor.setter
    def ocr_scale_factor(self, value: float):
        obj = self._get_preset_obj()
        obj.ocr_scale_factor = float(value)
        if self.preset_path:
            self.save_preset(self.preset_path, obj)

    @property
    def save_logs(self) -> bool:
        return self._get_preset_obj().save_logs

    @save_logs.setter
    def save_logs(self, value: bool):
        obj = self._get_preset_obj()
        obj.save_logs = bool(value)
        if self.preset_path:
            self.save_preset(self.preset_path, obj)

    @property
    def min_line_length(self) -> int:
        return self._get_preset_obj().min_line_length

    @min_line_length.setter
    def min_line_length(self, value: int):
        obj = self._get_preset_obj()
        obj.min_line_length = int(value)
        if self.preset_path:
            self.save_preset(self.preset_path, obj)

    @property
    def text_file_path(self) -> str:
        return self._get_preset_obj().text_file_path

    @text_file_path.setter
    def text_file_path(self, value: str):
        obj = self._get_preset_obj()
        obj.text_file_path = str(value)
        if self.preset_path:
            self.save_preset(self.preset_path, obj)

    @property
    def audio_dir(self) -> str:
        return self._get_preset_obj().audio_dir

    @audio_dir.setter
    def audio_dir(self, value: str):
        obj = self._get_preset_obj()
        obj.audio_dir = str(value)
        if self.preset_path:
            self.save_preset(self.preset_path, obj)

    @property
    def audio_ext(self) -> str:
        return self._get_preset_obj().audio_ext

    @audio_ext.setter
    def audio_ext(self, value: str):
        obj = self._get_preset_obj()
        obj.audio_ext = str(value)
        if self.preset_path:
            self.save_preset(self.preset_path, obj)

    @property
    def areas(self) -> List[AreaConfig]:
        """Returns areas scaled to physical resolution."""
        return self.get_areas()

    @areas.setter
    def areas(self, value: List[AreaConfig]):
        """Accepts areas in physical coordinates, scales them to 4K and saves."""
        obj = self._get_preset_obj()
        import copy as _copy
        new_areas = _copy.deepcopy(value)
        
        if self.display_resolution:
            dw, dh = self.display_resolution
            for area in new_areas:
                area.rect = scale_utils.scale_rect_to_4k(area.rect, dw, dh)
        
        obj.areas = new_areas
        if self.preset_path:
            self.save_preset(self.preset_path, obj)

    @property
    def auto_remove_names(self) -> bool:
        return self._get_preset_obj().auto_remove_names

    @auto_remove_names.setter
    def auto_remove_names(self, value: bool):
        obj = self._get_preset_obj()
        obj.auto_remove_names = bool(value)
        if self.preset_path:
            self.save_preset(self.preset_path, obj)

    @property
    def show_debug(self) -> bool:
        return self._get_preset_obj().show_debug

    @show_debug.setter
    def show_debug(self, value: bool):
        obj = self._get_preset_obj()
        obj.show_debug = bool(value)
        if self.preset_path:
            self.save_preset(self.preset_path, obj)

    @property
    def text_color_mode(self) -> str:
        return self._get_preset_obj().text_color_mode

    @text_color_mode.setter
    def text_color_mode(self, value: str):
        obj = self._get_preset_obj()
        obj.text_color_mode = str(value)
        if self.preset_path:
            self.save_preset(self.preset_path, obj)

    @property
    def subtitle_mode(self) -> str:
        return self._get_preset_obj().subtitle_mode

    @subtitle_mode.setter
    def subtitle_mode(self, value: str):
        obj = self._get_preset_obj()
        obj.subtitle_mode = str(value)
        if self.preset_path:
            self.save_preset(self.preset_path, obj)

    @property
    def brightness_threshold(self) -> int:
        return self._get_preset_obj().brightness_threshold

    @brightness_threshold.setter
    def brightness_threshold(self, value: int):
        obj = self._get_preset_obj()
        obj.brightness_threshold = int(value)
        if self.preset_path:
            self.save_preset(self.preset_path, obj)

    @property
    def contrast(self) -> float:
        return self._get_preset_obj().contrast

    @contrast.setter
    def contrast(self, value: float):
        obj = self._get_preset_obj()
        obj.contrast = float(value)
        if self.preset_path:
            self.save_preset(self.preset_path, obj)

    @property
    def color_tolerance(self) -> int:
        return self._get_preset_obj().color_tolerance

    @color_tolerance.setter
    def color_tolerance(self, value: int):
        obj = self._get_preset_obj()
        obj.color_tolerance = int(value)
        if self.preset_path:
            self.save_preset(self.preset_path, obj)

    @property
    def text_thickening(self) -> int:
        return self._get_preset_obj().text_thickening

    @text_thickening.setter
    def text_thickening(self, value: int):
        obj = self._get_preset_obj()
        obj.text_thickening = int(value)
        if self.preset_path:
            self.save_preset(self.preset_path, obj)

    @property
    def text_color_mode(self) -> str:
        return self._get_preset_obj().text_color_mode

    @text_color_mode.setter
    def text_color_mode(self, value: str):
        obj = self._get_preset_obj()
        obj.text_color_mode = str(value)
        if self.preset_path:
            self.save_preset(self.preset_path, obj)

    @property
    def auto_remove_names(self) -> bool:
        return self._get_preset_obj().auto_remove_names

    @auto_remove_names.setter
    def auto_remove_names(self, value: bool):
        obj = self._get_preset_obj()
        obj.auto_remove_names = bool(value)
        if self.preset_path:
            self.save_preset(self.preset_path, obj)
            
    @property
    def regex_mode_name(self) -> str:
        return self._get_preset_obj().regex_mode_name

    @regex_mode_name.setter
    def regex_mode_name(self, value: str):
        obj = self._get_preset_obj()
        obj.regex_mode_name = str(value)
        if self.preset_path:
            self.save_preset(self.preset_path, obj)

    @property
    def regex_pattern(self) -> str:
        return self._get_preset_obj().regex_pattern

    @regex_pattern.setter
    def regex_pattern(self, value: str):
        obj = self._get_preset_obj()
        obj.regex_pattern = str(value)
        if self.preset_path:
            self.save_preset(self.preset_path, obj)

    @property
    def text_thickening(self) -> int:
        return self._get_preset_obj().text_thickening

    @text_thickening.setter
    def text_thickening(self, value: int):
        obj = self._get_preset_obj()
        obj.text_thickening = int(value)
        if self.preset_path:
            self.save_preset(self.preset_path, obj)

    @property
    def brightness_threshold(self) -> int:
        return self._get_preset_obj().brightness_threshold

    @brightness_threshold.setter
    def brightness_threshold(self, value: int):
        obj = self._get_preset_obj()
        obj.brightness_threshold = int(value)
        if self.preset_path:
            self.save_preset(self.preset_path, obj)

    @property
    def contrast(self) -> float:
        return self._get_preset_obj().contrast

    @contrast.setter
    def contrast(self, value: float):
        obj = self._get_preset_obj()
        obj.contrast = float(value)
        if self.preset_path:
            self.save_preset(self.preset_path, obj)

    @property
    def color_tolerance(self) -> int:
        return self._get_preset_obj().color_tolerance

    @color_tolerance.setter
    def color_tolerance(self, value: int):
        obj = self._get_preset_obj()
        obj.color_tolerance = int(value)
        if self.preset_path:
            self.save_preset(self.preset_path, obj)

    @property
    def show_debug(self) -> bool:
        return self._get_preset_obj().show_debug

    @show_debug.setter
    def show_debug(self, value: bool):
        obj = self._get_preset_obj()
        obj.show_debug = bool(value)
        if self.preset_path:
            self.save_preset(self.preset_path, obj)

    @property
    def subtitle_colors(self) -> List[str]:
        return self._get_preset_obj().subtitle_colors

    @subtitle_colors.setter
    def subtitle_colors(self, value: List[str]):
        obj = self._get_preset_obj()
        obj.subtitle_colors = list(value)
        if self.preset_path:
            self.save_preset(self.preset_path, obj)


    @property
    def areas(self) -> List[AreaConfig]:
        """Return the list of areas (as `AreaConfig`) scaled to the manager's `display_resolution`."""
        return self.get_areas()

    @areas.setter
    def areas(self, value: List[AreaConfig]):
        """Sets areas and saves the preset.
        Scales the provided area rects FROM display resolution TO 4K canonical.
        """
        obj = self._get_preset_obj()
        import copy as _copy
        canonical_areas = _copy.deepcopy(list(value))
        
        # Scale back to 4K before storing in the canonical memory cache
        if self.display_resolution:
            sw, sh = self.display_resolution
            for area in canonical_areas:
                area.rect = scale_utils.scale_rect_to_4k(area.rect, sw, sh)
        
        obj.areas = canonical_areas
        if self.preset_path:
            self.save_preset(self.preset_path, obj)


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
            current_obj = self.load_preset(target_preset_path)

            # Nadpisz obszary - ustawiamy jako pierwszy i jedyny obszar
            current_obj.areas = [AreaConfig(
                id=1,
                type="continuous",
                rect=new_monitor,
                hotkey="",
                colors=[]
            )]

            # Opcjonalnie: Importuj inne ustawienia jeśli pasują, np. minimalna długość linii
            if "min_line_len" in win_data:
                current_obj.min_line_length = win_data.get("min_line_len")

            self.save_preset(target_preset_path, current_obj)
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

    def load_preset(self, path: Optional[str] = None) -> PresetConfig:
        """Loads preset and returns a PresetConfig object. Rects are left in canonical 4K."""
        if path and path != self.preset_path:
            self.preset_cache = None
            self.preset_path = path

        if self.preset_cache is not None:
            return self.preset_cache
            
        if not path:
            path = self.preset_path
        else:
            self.preset_path = path
            
        if not path or not os.path.exists(path):
            return PresetConfig()
            
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # Fill missing keys from defaults
            for k, v in DEFAULT_PRESET_CONTENT.items():
                if k not in data:
                    data[k] = v

            # Migracja starej konfiguracji (monitor -> areas)
            if not data.get('areas') and data.get('monitor'):
                self._migrate_legacy_areas(data)

            # Absolute paths for runtime
            base_dir = os.path.dirname(os.path.abspath(path))
            for key in ['audio_dir', 'text_file_path']:
                if key in data and isinstance(data[key], str):
                    data[key] = self._to_absolute(base_dir, data[key])

            obj = PresetConfig._from_dict(data)
            self.preset_cache = obj
            return obj
        except Exception as e:
            print(f"Error loading preset: {e}")
            return PresetConfig()

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
                "colors": colors
            })
        
        # Area 3 (W starym kodzie index 2 był "Area 3" - manualny)
        if len(monitors) > 2 and monitors[2]:
            new_areas.append({
                "id": 2,
                "type": "manual",
                "rect": monitors[2],
                "hotkey": self.settings.get('hotkey_area3', '<f3>'),
                "colors": []
            })
            
        data['areas'] = new_areas

    # --- New helpers for scaling areas ---
    def get_preset_for_resolution(self, path: Optional[str], dest_resolution: Tuple[int, int]) -> Dict[str, Any]:
        return self.get_preset_for_display(path, dest_resolution)

    def get_preset_for_display(self, path: Optional[str] = None, dest_resolution: Optional[Tuple[int, int]] = None) -> Dict[str, Any]:
        """Return a preset dict where `areas` rects are scaled from canonical 4K to
        the provided `dest_resolution` or the manager's `display_resolution`.
        """
        obj = self.load_preset(path)
        import copy as _copy
        res_obj = _copy.deepcopy(obj)
        
        target_res = dest_resolution or self.display_resolution
        if target_res:
            dw, dh = target_res
            for area in res_obj.areas:
                area.rect = scale_utils.scale_rect_to_physical(area.rect, dw, dh)
        
        return res_obj._to_dict()

    # High-level helpers for area-level access
    def get_areas(self) -> List[AreaConfig]:
        """Return a copy of areas scaled to current display_resolution."""
        obj = self._get_preset_obj()
        import copy as _copy
        areas_copy = _copy.deepcopy(obj.areas)
        
        if self.display_resolution:
            dw, dh = self.display_resolution
            for area in areas_copy:
                area.rect = scale_utils.scale_rect_to_physical(area.rect, dw, dh)
        
        return areas_copy

    def get_area(self, index: int) -> Optional[AreaConfig]:
        areas = self.get_areas()
        if 0 <= index < len(areas):
            return areas[index]
        return None

    def set_areas_from_display(self, areas: List[Any], src_resolution: Optional[Tuple[int, int]] = None):
        if src_resolution:
            self.display_resolution = src_resolution
        self.areas = areas

    def set_areas(self, areas: List[AreaConfig]):
        """Update areas in current preset and save.
        Using the property setter ensures correct 4K canonical scaling.
        """
        self.areas = areas


    def save_preset(self, path: Optional[str] = None, obj: Optional[PresetConfig] = None):
        """Saves PresetConfig to disk. Coordinate scaling (4K) is handled by property getters/setters."""
        if obj is None:
            obj = self._get_preset_obj()
        if not path:
            path = self.preset_path
        if not path:
            return

        try:
            import copy as _copy
            # Work on a copy for path normalization
            save_obj = _copy.deepcopy(obj)
            
            # 1. Path normalization (Absolute -> Relative)
            base_dir = os.path.dirname(os.path.abspath(path))
            if os.path.isabs(str(save_obj.audio_dir)):
                save_obj.audio_dir = self._to_relative(base_dir, save_obj.audio_dir)
            if os.path.isabs(str(save_obj.text_file_path)):
                save_obj.text_file_path = self._to_relative(base_dir, save_obj.text_file_path)

            # 2. Serialization
            write_data = save_obj._to_dict()

            # 3. Write to disk
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(write_data, f, indent=4, ensure_ascii=False)
            
            self.preset_cache = obj
        except Exception as e:
            print(f"Error saving preset: {e}")


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