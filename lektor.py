#!/usr/bin/env python3
import sys
import os
import queue
import threading
import subprocess
import time
import argparse
import platform
from typing import Optional

try:
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox, font
except ImportError:
    print("Błąd: Brak biblioteki tkinter.", file=sys.stderr)
    sys.exit(1)

if platform.system() == "Windows":
    try:
        import ctypes

        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

try:
    from pynput import keyboard

    HAS_PYNPUT = True
except ImportError:
    HAS_PYNPUT = False
    
STANDARD_WIDTH = 3840
STANDARD_HEIGHT = 2160

from app.config_manager import ConfigManager
from app.reader import ReaderThread
from app.player import PlayerThread
from app.log import LogWindow
from app.settings import SettingsDialog
from app.area_selector import AreaSelector, ColorSelector
from app.area_manager import AreaManagerWindow, OptimizationCaptureWindow
from app.capture import capture_fullscreen
from app.help import HelpWindow
from app.optimizer import SettingsOptimizer
from app.geometry_utils import calculate_merged_area

# Global events/queues
stop_event = threading.Event()
audio_queue = queue.Queue()
log_queue = queue.Queue()
debug_queue = queue.Queue()

APP_VERSION = "v1.3.0"


class LektorApp:
    def __init__(self, root: tk.Tk, autostart_preset: Optional[str], game_cmd: list):
        self.root = root
        self.root.title(f"Lektor {APP_VERSION}")
        self.root.geometry("730x430")

        self.config_mgr = ConfigManager()
        self.game_cmd = game_cmd
        self.game_process = None

        self.reader_thread = None
        self.player_thread = None
        self.log_window = None
        self.help_window = None
        self.is_running = False
        self.hotkey_listener = None

        # Zmienne UI
        self.var_preset_display = tk.StringVar()
        self.full_preset_paths = []
        self.var_preset_full_path = tk.StringVar()

        # Opcje Lektora
        self.var_subtitle_mode = tk.StringVar(value="Full Lines")
        self.var_text_color = tk.StringVar(value="Light")
        self.var_ocr_scale = tk.DoubleVar(value=1.0)
        self.var_brightness_threshold = tk.IntVar(value=200)
        self.var_similarity = tk.DoubleVar(value=5.0)
        self.var_contrast = tk.DoubleVar(value=5.0)
        self.var_tolerance = tk.IntVar(value=10)
        self.var_text_thickening = tk.IntVar(value=0)
        self.var_empty_threshold = tk.DoubleVar(value=0.15)
        self.var_capture_interval = tk.DoubleVar(value=0.5)
        self.var_auto_names = tk.BooleanVar(value=True)

        # Opcje optymalizacji
        self.var_min_line_len = tk.IntVar(value=0)
        self.var_text_alignment = tk.StringVar(value="None")
        self.var_save_logs = tk.BooleanVar(value=False)
        self.var_show_debug = tk.BooleanVar(value=False)

        self.var_ocr_density = tk.DoubleVar(value=0.015)
        self.var_match_score_short = tk.IntVar(value=90)
        self.var_match_score_long = tk.IntVar(value=75)
        self.var_match_len_diff = tk.DoubleVar(value=0.25)
        self.var_partial_min_len = tk.IntVar(value=25)
        self.var_audio_speed = tk.DoubleVar(value=1.20)

        # Regex
        self.var_regex_mode = tk.StringVar()
        self.var_custom_regex = tk.StringVar()

        # Audio
        self.var_resolution = tk.StringVar()
        self.var_speed = tk.DoubleVar(value=1.2)
        self.var_volume = tk.DoubleVar(value=1.0)
        self.var_audio_ext = tk.StringVar(value=".ogg")

        self.regex_map = {
            "Brak": r"",
            "Standard (Imię: Dialog)": r"^(?i)({NAMES})\s*[:：\-; ]*",
            "Nawiasy ([Imię] Dialog)": r"^\[({NAMES})\]",
            "Imię na początku": r"^({NAMES})\s+",
            "Własny (Regex)": "CUSTOM"
        }

        self.resolutions = [
            "1920x1080", "2560x1440", "3840x2160",
            "1280x800", "2560x1600", "Niestandardowa"
        ]

        self._init_gui()
        self._load_initial_state(autostart_preset)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self._check_debug_queue()

        if HAS_PYNPUT:
            self._start_hotkey_listener()

    # --- LOGIKA SKALI OCR ---
    def _calc_auto_scale(self, width, height):
        if height <= 800: return 0.8
        if height >= 2160: return 0.3
        ratio = (height - 800) / (2160 - 800)
        scale = 0.8 + ratio * (0.3 - 0.8)
        return round(scale * 20) / 20.0

    def _update_scale_for_resolution(self, res_str, force_auto=False):
        try:
            w, h = map(int, res_str.split('x'))
        except:
            return

        path = self.var_preset_full_path.get()
        overrides = {}
        if path and os.path.exists(path):
            data = self.config_mgr.load_preset(path)
            overrides = data.get('scale_overrides', {})

        if not force_auto and res_str in overrides:
            new_scale = overrides[res_str]
        else:
            new_scale = self._calc_auto_scale(w, h)

        self.var_ocr_scale.set(new_scale)

    def on_manual_scale_change(self, event=None):
        val = round(self.var_ocr_scale.get(), 2)
        path = self.var_preset_full_path.get()
        res_str = self.var_resolution.get()
        if path and os.path.exists(path) and "x" in res_str:
            data = self.config_mgr.load_preset(path)
            overrides = data.get('scale_overrides', {})
            overrides[res_str] = val
            data['scale_overrides'] = overrides
            data['ocr_scale_factor'] = val
            self.config_mgr.save_preset(path, data)

    # -----------------------

    def _start_hotkey_listener(self):
        hk_start = self.config_mgr.get('hotkey_start_stop', '<ctrl>+<f5>')
        
        if hasattr(self, 'hotkey_listener') and self.hotkey_listener:
            try:
                self.hotkey_listener.stop()
            except: pass

        hotkeys = {
            hk_start: self._on_hotkey_start_stop,
        }
        
        # Load areas from current preset
        path = self.var_preset_full_path.get()
        if path and os.path.exists(path):
             data = self.config_mgr.load_preset(path)
             if data and 'areas' in data:
                 for area in data['areas']:
                     hk = area.get('hotkey')
                     aid = area.get('id')
                     atype = area.get('type', 'manual')
                     if hk:
                         # Capture aid in lambda default arg
                         hotkeys[hk] = lambda aid=aid, t=atype: self._on_hotkey_area_action(aid, t)

        try:
            self.hotkey_listener = keyboard.GlobalHotKeys(hotkeys)
            self.hotkey_listener.start()
        except Exception as e:
            print(f"Ostrzeżenie: Nie udało się zarejestrować skrótów globalnych: {e}")

    def _restart_hotkeys(self):
        if HAS_PYNPUT: self._start_hotkey_listener()

    def _on_hotkey_start_stop(self):
        self.root.after(0, self._toggle_start_stop_hotkey)

    def _on_hotkey_area_action(self, area_id, area_type):
        self.root.after(0, lambda: self._trigger_reader_area(area_id, area_type))

    def _toggle_start_stop_hotkey(self):
        if self.is_running:
            self.stop_reading()
        else:
            self.start_reading()

    def _trigger_reader_area(self, area_id, area_type='manual'):
        if self.is_running and self.reader_thread: 
            if area_type == 'continuous':
                self.reader_thread.toggle_continuous_area(area_id)
            else:
                self.reader_thread.trigger_area(area_id)

    def _init_gui(self):
        menubar = tk.Menu(self.root)

        preset_menu = tk.Menu(menubar, tearoff=0)
        preset_menu.add_command(label="Wybierz katalog...", command=self.browse_lector_folder)
        preset_menu.add_separator()
        preset_menu.add_command(label="Zmień folder audio", command=lambda: self.change_path('audio_dir'))
        preset_menu.add_command(label="Zmień plik napisów", command=lambda: self.change_path('text_file_path'))
        preset_menu.add_command(label="Importuj preset (Game Reader)", command=self.import_preset_dialog)
        preset_menu.add_separator()
        preset_menu.add_command(label="Wykryj optymalne ustawienia", command=self.detect_optimal_settings)
        menubar.add_cascade(label="Lektor", menu=preset_menu)

        # Removed main area menu as requested
        # main_area_menu = tk.Menu(menubar, tearoff=0)
        # main_area_menu.add_command(label="Zarządzaj Obszarami...", command=self.open_area_manager)
        # main_area_menu.add_separator()
        # main_area_menu.add_command(label="Ustaw główny obszar (1)", command=self.set_area_1_direct)
        # menubar.add_cascade(label="Obszary", menu=main_area_menu)

        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="Podgląd logów", command=self.show_logs)
        help_menu.add_command(label="Instrukcja", command=self.show_help)
        menubar.add_cascade(label="Pomoc", menu=help_menu)
        self.root.config(menu=menubar)

        panel = ttk.Frame(self.root, padding=10)
        panel.pack(fill=tk.BOTH, expand=True)

        ttk.Label(panel, text="Aktywny lektor (Katalog):").pack(anchor=tk.W)
        self.cb_preset = ttk.Combobox(panel, textvariable=self.var_preset_display, state="readonly", width=60)
        self.cb_preset.pack(fill=tk.X, pady=5)
        self.cb_preset.bind("<<ComboboxSelected>>", self.on_preset_selected_from_combo)

        # --- ROZDZIELCZOŚĆ ---
        f_res = ttk.Frame(panel)
        f_res.pack(fill=tk.X, pady=5)
        ttk.Label(f_res, text="Rozdzielczość:").pack(side=tk.LEFT)
        self.cb_res = ttk.Combobox(f_res, textvariable=self.var_resolution, values=self.resolutions)
        self.cb_res.pack(side=tk.LEFT, padx=5)
        self.cb_res.bind("<<ComboboxSelected>>", lambda e: [
            self.config_mgr.update_setting('last_resolution_key', self.var_resolution.get()),
            self._update_scale_for_resolution(self.var_resolution.get())
        ])
        ttk.Button(f_res, text="Dopasuj rozdz.", command=self.auto_detect_resolution).pack(side=tk.LEFT, padx=5)
        self.btn_settings = ttk.Button(f_res, text="⚙ Ustawienia", command=self.open_settings)
        self.btn_settings.pack(side=tk.LEFT, padx=5)

        # Actions Panel (Replaces Colors Panel)
        grp_act = ttk.LabelFrame(panel, text="Akcje", padding=10)
        grp_act.pack(fill=tk.X, pady=5)
        
        # Big Buttons for main actions
        btn_areas = tk.Button(grp_act, text="Zarządzaj Obszarami", command=self.open_area_manager, bg="#e0e0e0", relief="raised", height=2)
        btn_areas.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)

        btn_detect = tk.Button(grp_act, text="Wykryj Ustawienia", command=self.detect_optimal_settings, bg="#d0f0ff", relief="raised", height=2)
        btn_detect.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)

        # Removed old subtitle colors section
        # grp_sub = ttk.LabelFrame(panel, text="Kolory napisów", padding=10) ...

        # --- AUDIO ---
        grp_aud = ttk.LabelFrame(panel, text="Kontrola Audio", padding=10)
        grp_aud.pack(fill=tk.X, pady=10)

        ttk.Label(grp_aud, text="Prędkość:").grid(row=0, column=0)
        s_spd = ttk.Scale(grp_aud, from_=0.9, to=1.5, variable=self.var_speed,
                          command=lambda v: self.lbl_spd.config(text=f"{float(v):.2f}x"))
        s_spd.grid(row=0, column=1, sticky="ew", padx=10)
        s_spd.bind("<ButtonRelease-1>", lambda e: self._save_preset_val("audio_speed", round(self.var_speed.get(), 2)))
        self.lbl_spd = ttk.Label(grp_aud, text="1.00x", width=5)
        self.lbl_spd.grid(row=0, column=2)

        ttk.Label(grp_aud, text="Głośność:").grid(row=1, column=0)
        s_vol = ttk.Scale(grp_aud, from_=0.0, to=1.5, variable=self.var_volume,
                          command=lambda v: self.lbl_vol.config(text=f"{float(v):.2f}"))
        s_vol.grid(row=1, column=1, sticky="ew", padx=10)
        s_vol.bind("<ButtonRelease-1>",
                   lambda e: self._save_preset_val("audio_volume", round(self.var_volume.get(), 2)))
        self.lbl_vol = ttk.Label(grp_aud, text="1.00", width=5)
        self.lbl_vol.grid(row=1, column=2)

        ttk.Label(grp_aud, text="Format:").grid(row=2, column=0)
        ttk.Label(grp_aud, textvariable=self.var_audio_ext, font=("Arial", 8, "bold")).grid(row=2, column=1, sticky="w",
                                                                                            padx=10)
        grp_aud.columnconfigure(1, weight=1)

        # --- STEROWANIE ---
        hk_start = self.config_mgr.get('hotkey_start_stop', 'F2')
        frm_btn = ttk.Frame(panel)
        frm_btn.pack(side=tk.BOTTOM, fill=tk.X, pady=10)

        self.btn_start = ttk.Button(frm_btn, text=f"START ({hk_start})", command=self.start_reading)
        self.btn_start.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        self.btn_stop = ttk.Button(frm_btn, text=f"STOP ({hk_start})", command=self.stop_reading, state="disabled")
        self.btn_stop.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)

        ttk.Label(self.root, text=f"Wersja: {APP_VERSION}", font=("Arial", 8)) \
            .pack(side=tk.BOTTOM, anchor=tk.E, padx=5)

        self.root.after(200, self.refresh_color_canvas)

    def auto_detect_resolution(self):
        w = self.root.winfo_screenwidth()
        h = self.root.winfo_screenheight()
        res_str = f"{w}x{h}"
        self.var_resolution.set(res_str)
        self.config_mgr.update_setting('last_resolution_key', res_str)
        self._update_scale_for_resolution(res_str)

    def _load_initial_state(self, autostart_path):
        self._update_preset_list()
        initial_path = autostart_path if autostart_path else (
            self.full_preset_paths[0] if self.full_preset_paths else None)
        if initial_path and os.path.exists(initial_path):
            self.var_preset_full_path.set(initial_path)
            try:
                self.var_preset_display.set(os.path.basename(os.path.dirname(initial_path)))
            except:
                pass
            self.on_preset_loaded()
            if autostart_path: self.root.after(500, self.start_reading)

        self.var_regex_mode.set(self.config_mgr.get('last_regex_mode', "Standard (Imię: Dialog)"))
        self.var_custom_regex.set(self.config_mgr.get('last_custom_regex', ""))
        self.auto_detect_resolution()
        self.on_regex_changed()

    def _update_preset_list(self):
        recents = [p for p in self.config_mgr.get('recent_presets', []) if os.path.exists(p)]
        self.full_preset_paths = recents
        self.cb_preset['values'] = [os.path.basename(os.path.dirname(p)) or p for p in recents]

    def on_preset_selected_from_combo(self, event=None):
        idx = self.cb_preset.current()
        if idx >= 0 and idx < len(self.full_preset_paths):
            self.var_preset_full_path.set(self.full_preset_paths[idx])
            self.on_preset_loaded()

    def on_preset_loaded(self):
        path = self.var_preset_full_path.get()
        if not path or not os.path.exists(path): return
        data = self.config_mgr.load_preset(path)

        base_dir = os.path.dirname(path)
        modified = False

        if not data.get("text_file_path"):
            try:
                for f in sorted(os.listdir(base_dir)):
                    if f.lower().endswith(".txt"):
                        data["text_file_path"] = os.path.join(base_dir, f)
                        modified = True
                        break
            except Exception:
                pass

        if not data.get("audio_dir"):
            try:
                for f in sorted(os.listdir(base_dir)):
                    full_p = os.path.join(base_dir, f)
                    if os.path.isdir(full_p):
                        data["audio_dir"] = full_p
                        modified = True
                        break
            except Exception:
                pass

        if modified:
            self.config_mgr.save_preset(path, data)

        self.var_speed.set(data.get("audio_speed", 1.0))
        self.lbl_spd.config(text=f"{self.var_speed.get():.2f}x")

        self.var_volume.set(data.get("audio_volume", 1.0))
        self.lbl_vol.config(text=f"{self.var_volume.get():.2f}")

        # Automatyczna detekcja formatu audio
        detected_ext = self._detect_audio_format(data.get("audio_dir", ""))
        current_ext = data.get("audio_ext", ".ogg")

        if detected_ext and detected_ext != current_ext:
            data['audio_ext'] = detected_ext
            self.config_mgr.save_preset(path, data)
            current_ext = detected_ext

        self.var_audio_ext.set(current_ext)

        self.var_auto_names.set(data.get("auto_remove_names", True))
        self.var_subtitle_mode.set(data.get("subtitle_mode", "Full Lines"))

        self.var_ocr_scale.set(data.get("ocr_scale_factor", 1.0))
        self.var_capture_interval.set(data.get("capture_interval", 0.5))
        self.var_min_line_len.set(data.get("min_line_length", 0))

        self.var_text_color.set(data.get("text_color_mode", "Light"))
        self.var_text_alignment.set(data.get("text_alignment", "None"))
        self.var_save_logs.set(data.get("save_logs", False))
        self.var_show_debug.set(data.get("show_debug", False))
        self.var_brightness_threshold.set(data.get("brightness_threshold", 200))
        self.var_similarity.set(data.get("similarity", 5.0))
        self.var_contrast.set(data.get("contrast", 0))
        self.var_tolerance.set(data.get("color_tolerance", 10))
        self.var_text_thickening.set(data.get("text_thickening", 10))

        self.var_match_score_short.set(data.get("match_score_short", 90))
        self.var_match_score_long.set(data.get("match_score_long", 75))
        self.var_match_len_diff.set(data.get("match_len_diff_ratio", 0.25))
        self.var_partial_min_len.set(data.get("partial_mode_min_len", 25))
        self.var_audio_speed.set(data.get("audio_speed_inc", 1.20))

        if "regex_mode_name" in data:
            self.var_regex_mode.set(data["regex_mode_name"])
            if data["regex_mode_name"] == "Własny (Regex)": self.var_custom_regex.set(data.get("regex_pattern", ""))
            self.on_regex_changed()

        self.refresh_color_canvas()

    def on_regex_changed(self, event=None):
        mode = self.var_regex_mode.get()

        if hasattr(self, 'ent_regex') and self.ent_regex:
            try:
                self.ent_regex.config(state="normal" if mode == "Własny (Regex)" else "disabled")
            except Exception:
                # Widget mógł zostać zniszczony po zamknięciu okna ustawień
                self.ent_regex = None

        self.config_mgr.update_setting('last_regex_mode', mode)
        if mode != "Własny (Regex)":
            self._save_preset_val("regex_pattern", self.regex_map.get(mode, ""))
            self._save_preset_val("regex_mode_name", mode)

    def _save_preset_val(self, key, val):
        path = self.var_preset_full_path.get()
        if path and os.path.exists(path):
            data = self.config_mgr.load_preset(path)
            data[key] = val
            self.config_mgr.save_preset(path, data)

    def browse_lector_folder(self):
        d = filedialog.askdirectory(title="Wybierz katalog z lektorem")
        if not d: return
        p = self.config_mgr.ensure_preset_exists(d)
        self.config_mgr.add_recent_preset(p)
        self._update_preset_list()
        self.var_preset_full_path.set(p)
        self.var_preset_display.set(os.path.basename(d))
        self.on_preset_loaded()

    def change_path(self, key):
        if not self.var_preset_full_path.get(): return messagebox.showerror("Błąd", "Wybierz profil.")
        base = os.path.dirname(self.var_preset_full_path.get())
        if key == 'audio_dir':
            new = filedialog.askdirectory(initialdir=base)
        else:
            new = filedialog.askopenfilename(initialdir=base, filetypes=[("Text", "*.txt")])
        if new:
            self._save_preset_val(key, new)

    def _scale_rect(self, rect, sx, sy):
        return {'left': int(rect['left'] * sx), 'top': int(rect['top'] * sy), 'width': int(rect['width'] * sx),
                'height': int(rect['height'] * sy)}

    def set_area(self, idx):
        path = self.var_preset_full_path.get()
        if not path: return messagebox.showerror("Błąd", "Wybierz profil.")
        self.root.withdraw()
        time.sleep(0.3)
        img = capture_fullscreen()
        if not img:
            self.root.deiconify()
            return
        sw, sh = img.size
        data = self.config_mgr.load_preset(path)
        mons = data.get('monitor', [])
        if isinstance(mons, dict): mons = [mons]
        while len(mons) < 3: mons.append(None)

        try:
            pw, ph = map(int, data.get('resolution', "1920x1080").split('x'))
        except:
            pw, ph = 1920, 1080

        disp_mons = [self._scale_rect(m, sw / pw, sh / ph) if m else None for m in mons]
        sel = AreaSelector(self.root, img, existing_regions=disp_mons)
        self.root.deiconify()

        if sel.geometry:
            disp_mons[idx] = sel.geometry
            final_mons = [self._scale_rect(m, STANDARD_WIDTH / sw, STANDARD_HEIGHT / sh) if m else None for m in
                          disp_mons]
            data['monitor'] = final_mons
            data['resolution'] = f"{STANDARD_WIDTH}x{STANDARD_HEIGHT}"
            self.config_mgr.save_preset(path, data)

    def clear_area(self, idx):
        path = self.var_preset_full_path.get()
        if not path: return
        data = self.config_mgr.load_preset(path)
        mons = data.get('monitor', [])
        if isinstance(mons, dict): mons = [mons]
        if idx < len(mons):
            mons[idx] = None
            data['monitor'] = [m for m in mons if m]
            self.config_mgr.save_preset(path, data)

    def open_settings(self):
        SettingsDialog(self.root, self.config_mgr.settings, self)
        self.config_mgr.save_app_config()
        self._restart_hotkeys()
        hk = self.config_mgr.get('hotkey_start_stop', '<ctrl>+<f5>')
        self.btn_start.config(text=f"START ({hk})")
        self.btn_stop.config(text=f"STOP ({hk})")

    def show_logs(self):
        if not self.log_window or not self.log_window.winfo_exists():
            self.log_window = LogWindow(self.root, log_queue)
        else:
            self.log_window.lift()

    def show_help(self):
        if not self.help_window or not self.help_window.winfo_exists():
            self.help_window = HelpWindow(self.root)
        else:
            self.help_window.lift()

    def start_reading(self):
        path = self.var_preset_full_path.get()
        if not path or not os.path.exists(path): return messagebox.showerror("Błąd", "Brak profilu.")
        self.config_mgr.add_recent_preset(path)
        self._update_preset_list()

        mode = self.var_regex_mode.get()
        pattern = self.var_custom_regex.get() if mode == "Własny (Regex)" else self.regex_map.get(mode, "")

        res_str = self.var_resolution.get()
        target_res = tuple(map(int, res_str.split('x'))) if "x" in res_str else None

        stop_event.clear()
        with audio_queue.mutex:
            audio_queue.queue.clear()

        self.player_thread = PlayerThread(stop_event, audio_queue,
                                          base_speed_callback=lambda: self.var_speed.get(),
                                          volume_callback=lambda: self.var_volume.get())
        self.reader_thread = ReaderThread(config_manager=self.config_mgr, stop_event=stop_event, audio_queue=audio_queue,
                                          target_resolution=target_res, log_queue=log_queue, debug_queue=debug_queue
                                          )
        self.player_thread.start()
        self.reader_thread.start()
        self.is_running = True
        self._toggle_ui(True)

        if self.game_cmd and not self.game_process:
            try:
                self.game_process = subprocess.Popen(self.game_cmd)
            except Exception as e:
                messagebox.showerror("Błąd", f"Nie udało się uruchomić gry: {e}")

    def stop_reading(self):
        self.is_running = False
        stop_event.set()
        if self.reader_thread: self.reader_thread.join(1.0)
        self._toggle_ui(False)

    def _toggle_ui(self, running):
        s = "disabled" if running else "normal"
        self.btn_start.config(state=s)
        self.btn_stop.config(state="normal" if running else "disabled")
        self.cb_preset.config(state=s)
        self.cb_res.config(state=s)

    def _detect_audio_format(self, audio_dir_path: str) -> Optional[str]:
        if not audio_dir_path or not os.path.exists(audio_dir_path):
            return None

        valid_exts = {".ogg", ".mp3", ".wav"}
        try:
            for f in os.listdir(audio_dir_path):
                base, ext = os.path.splitext(f)
                if ext.lower() in valid_exts:
                    return ext.lower()
        except Exception:
            pass
        return None

    def on_close(self):
        self.is_running = False
        if self.reader_thread and self.reader_thread.is_alive(): self.stop_reading()
        if self.game_process: self.game_process.terminate()
        if hasattr(self, 'hotkey_listener') and self.hotkey_listener: self.hotkey_listener.stop()
        self.root.destroy()

    def _check_debug_queue(self):
        """Sprawdza, czy są nowe ramki do narysowania."""
        try:
            while True:
                msg_type, data = debug_queue.get_nowait()
                if msg_type == 'overlay':
                    x, y, w, h = data
                    self._show_debug_overlay(x, y, w, h)
        except queue.Empty:
            pass
        finally:
            self.root.after(50, self._check_debug_queue)

    def _show_debug_overlay(self, x, y, w, h):
        """
        Rysuje ramkę składającą się z 4 osobnych okien (pasków).
        Jest to konieczne na Linux/Wayland, gdzie 'transparentcolor' nie działa.
        """
        if not self.var_show_debug.get():
            return

        thickness = 3
        color = 'red'
        duration = 200  # Czas wyświetlania (ms)

        # Zabezpieczenie przed ujemnymi/zerowymi wymiarami
        w = max(thickness * 2, w)
        h = max(thickness * 2, h)

        windows = []

        def create_strip(geometry_str):
            """Tworzy pojedynczy pasek ramki."""
            top = tk.Toplevel(self.root)
            top.overrideredirect(True)  # Brak belek systemowych
            top.geometry(geometry_str)
            top.configure(bg=color)
            try:
                top.attributes('-topmost', True)
            except Exception:
                pass
            return top

        # 1. Pasek górny
        windows.append(create_strip(f"{w}x{thickness}+{x}+{y}"))

        # 2. Pasek dolny
        windows.append(create_strip(f"{w}x{thickness}+{x}+{y + h - thickness}"))

        # 3. Pasek lewy (bez rogów, żeby nie nakładać się na górny/dolny)
        h_inner = h - (2 * thickness)
        if h_inner > 0:
            windows.append(create_strip(f"{thickness}x{h_inner}+{x}+{y + thickness}"))

        # 4. Pasek prawy
        if h_inner > 0:
            windows.append(create_strip(f"{thickness}x{h_inner}+{x + w - thickness}+{y + thickness}"))

        # Funkcja zamykająca wszystkie paski naraz
        def close_overlay():
            for win in windows:
                try:
                    win.destroy()
                except Exception:
                    pass

        # Zamknij po określonym czasie
        # Używamy self.root.after, aby odwołać się do głównej pętli,
        # bo 'windows[0]' może już nie istnieć w momencie wywołania.
        self.root.after(duration, close_overlay)

    def import_preset_dialog(self):
        current_path = self.var_preset_full_path.get()
        if not current_path or not os.path.exists(current_path):
            messagebox.showerror("Błąd", "Najpierw wybierz lub utwórz aktywny preset Lektora.")
            return

        file_path = filedialog.askopenfilename(
            title="Wybierz plik ustawień (Game Reader)",
            filetypes=[("Pliki JSON", "*.json"), ("Wszystkie pliki", "*.*")]
        )
        if not file_path:
            return

        if self.config_mgr.import_gr_preset(file_path, current_path):
            messagebox.showinfo("Sukces", "Zaimportowano obszar i przeskalowano do 4K.")
            # Odśwież UI wczytując ponownie preset
            self.on_preset_selected_from_combo()
        else:
            messagebox.showerror("Błąd", "Nie udało się zaimportować ustawień. Sprawdź plik.")

    def refresh_color_canvas(self):
        """Rysuje listę kolorów na nowym Canvasie."""
        if not hasattr(self, 'color_canvas'): return

        self.color_canvas.delete("all")

        path = self.var_preset_full_path.get()
        if not path or not os.path.exists(path):
            return

        data = self.config_mgr.load_preset(path)
        areas = data.get("areas", [])
        # Fallback to old colors if areas not migrated yet? Migration happens on load.
        # But let's be safe and check areas[0]
        colors = []
        if areas:
            # Find Area 1
            a1 = next((a for a in areas if a.get('id') == 1), None)
            if a1: colors = a1.get('colors', [])
        else:
            colors = data.get("subtitle_colors", [])

        x_offset = 2
        y_pos = 2
        size = 20

        if not colors:
            self.color_canvas.create_text(5, 12, text="(brak filtrów - domyślny tryb)", anchor=tk.W, fill="gray")
            return

        for i, color in enumerate(colors):
            try:
                tag_name = f"color_{i}"
                self.color_canvas.create_rectangle(
                    x_offset, y_pos, x_offset + size, y_pos + size,
                    fill=color, outline="#555555", tags=(tag_name, "clickable")
                )
                x_offset += size + 5
            except:
                pass

    def add_subtitle_color(self):
        """Obsługa wyboru koloru pipetą (tylko dla Obszaru 1)."""
        self.root.withdraw()
        # Daj czas na zniknięcie
        self.root.update()
        time.sleep(0.3)

        try:
            full_img = capture_fullscreen()
            if not full_img:
                self.root.deiconify()
                return

            selector = ColorSelector(self.root, full_img)
            self.root.wait_window(selector)

            if selector.selected_color:
                path = self.var_preset_full_path.get()
                if path and os.path.exists(path):
                    data = self.config_mgr.load_preset(path)

                    if 'areas' not in data:
                        # Should have been migrated, but just in case
                        self.config_mgr._migrate_legacy_areas(data)
                    
                    areas = data.get('areas', [])
                    a1 = next((a for a in areas if a.get('id') == 1), None)
                    
                    if a1:
                        if selector.selected_color not in a1['colors']:
                            a1['colors'].append(selector.selected_color)
                            self.config_mgr.save_preset(path, data)
                            print(f"Dodano kolor do Obszaru 1: {selector.selected_color}")
                            self.refresh_color_canvas()
                    else:
                        print("Błąd: Nie znaleziono Obszaru 1")

        except Exception as e:
            messagebox.showerror("Błąd", str(e))
        finally:
            self.root.deiconify()

    def on_color_click(self, event):
        item_id = self.color_canvas.find_closest(event.x, event.y)
        tags = self.color_canvas.gettags(item_id)
        for tag in tags:
            if tag.startswith("color_"):
                try:
                    idx = int(tag.split("_")[1])
                    self.delete_subtitle_color(idx)
                    return
                except ValueError:
                    pass

    def add_white_subtitle_color(self):
        path = self.var_preset_full_path.get()
        if not path or not os.path.exists(path): return 
        
        data = self.config_mgr.load_preset(path)
        if 'areas' not in data: self.config_mgr._migrate_legacy_areas(data)
        
        areas = data.get('areas', [])
        a1 = next((a for a in areas if a.get('id') == 1), None)
        
        if a1:
            if '#ffffff' not in a1['colors']:
                a1['colors'].append('#ffffff')
                self.config_mgr.save_preset(path, data)
                self.refresh_color_canvas()

    def delete_subtitle_color(self, idx):
        path = self.var_preset_full_path.get()
        if not path or not os.path.exists(path): return

        data = self.config_mgr.load_preset(path)
        areas = data.get("areas", [])
        a1 = next((a for a in areas if a.get('id') == 1), None)

        if a1:
            colors = a1.get("colors", [])
            if idx < len(colors):
                color_to_remove = colors[idx]
                if messagebox.askyesno("Usuwanie koloru", f"Czy usunąć kolor {color_to_remove} z Obszaru 1?"):
                    del colors[idx]
                    self.config_mgr.save_preset(path, data)
                    self.refresh_color_canvas()

    # --- ZARZĄDZANIE OBSZARAMI ---

    def open_area_manager(self):
        path = self.var_preset_full_path.get()
        if not path:
             messagebox.showerror("Błąd", "Brak aktywnego profilu.")
             return
             
        data = self.config_mgr.load_preset(path)
        if 'areas' not in data: self.config_mgr._migrate_legacy_areas(data)
        
        # Load subtitles for testing inside manager
        txt_path = data.get('text_file_path')
        subs = []
        if txt_path and os.path.exists(txt_path):
             subs = self.config_mgr.load_text_lines(txt_path)
        
        # Open Manager
        AreaManagerWindow(self.root, data['areas'], self._save_areas_callback, subs)

    def _save_areas_callback(self, new_areas):
        path = self.var_preset_full_path.get()
        if path:
            data = self.config_mgr.load_preset(path)
            data['areas'] = new_areas
            self.config_mgr.save_preset(path, data)
            self._restart_hotkeys()
            self.refresh_color_canvas() # Update in case Area 1 colors changed in manager
            
            # Restart reader to apply changes (geometry, enabled state, etc.)
            if self.is_running:
                print("Obszary zmienione, restartuję czytanie...")
                self.stop_reading()
                # Give it a moment using `after` isn't ideal for straight restart logic, 
                # but direct restart is simpler.
                # However, stop_reading signals flag. Thread needs to die.
                # We can use a short delay to restart.
                self.root.after(200, self.start_reading)

    def set_area_1_direct(self):
        """Ustawia obszar 1 bezpośrednio z głównego okna."""
        self.root.withdraw()
        self.root.update()
        time.sleep(0.3)
        
        try:
            img = capture_fullscreen()
            if not img:
                self.root.deiconify()
                return

            # Load existing rects for visualization
            path = self.var_preset_full_path.get()
            existing = []
            if path:
                data = self.config_mgr.load_preset(path)
                if 'areas' not in data: self.config_mgr._migrate_legacy_areas(data)
                existing = data.get('areas', [])

            sel = AreaSelector(self.root, img, existing_regions=existing)
            # AreaSelector is modal and waits inside its __init__, so no external wait needed.
            
            if sel.geometry and path:
                 data = self.config_mgr.load_preset(path)
                 areas = data.get('areas', [])
                 a1 = next((a for a in areas if a.get('id') == 1), None)
                 
                 if not a1:
                     # Create if missing
                     a1 = {"id": 1, "type": "continuous", "rect": sel.geometry, "hotkey": "", "colors": []}
                     areas.insert(0, a1)
                 else:
                     a1['rect'] = sel.geometry
                 
                 data['areas'] = areas
                 self.config_mgr.save_preset(path, data)
                 
        except Exception as e:
            messagebox.showerror("Błąd", f"Wybór obszaru: {e}")
        finally:
            self.root.deiconify()

    def detect_optimal_settings(self):
        """
        Uruchamia proces automatycznego wykrywania ustawień (Threaded).
        """
        path = self.var_preset_full_path.get()
        if not path or not os.path.exists(path):
            messagebox.showinfo("Info", "Najpierw wybierz lub stwórz preset.")
            return

        # Check subtitles first
        data = self.config_mgr.load_preset(path)
        if 'areas' not in data: self.config_mgr._migrate_legacy_areas(data)
        
        txt_path = data.get('text_file_path')
        if not txt_path or not os.path.exists(txt_path):
             messagebox.showerror("Błąd", "Nie znaleziono pliku napisów w ustawieniach presetu.")
             return
                
        subtitle_lines = self.config_mgr.load_text_lines(txt_path)
        if not subtitle_lines:
             messagebox.showerror("Błąd", "Plik napisów jest pusty.")
             return

        # Open Setup Dialog
        self._show_optimization_setup(data, subtitle_lines, path)

    def _show_optimization_setup(self, preset_data, subtitle_lines, preset_path):
        def on_wizard_finish(frames_data):
            # frames_data: list of {'image': PIL, 'rect': (x,y,w,h) or None}
            valid_images = [f['image'] for f in frames_data]
            valid_rects = [f['rect'] for f in frames_data if f['rect']]

            if not valid_rects:
                 messagebox.showerror("Błąd", "Nie zdefiniowano żadnego obszaru (Wycinka).")
                 return

            # Combine rects logic (Union + 5%)
            fw, fh = valid_images[0].size
            # Use utility with margin factor 0.05
            fx, fy, real_w, real_h = calculate_merged_area(valid_rects, fw, fh, 0.05)
            
            target_rect = (fx, fy, real_w, real_h)
            mode = preset_data.get('subtitle_mode', 'Full Lines')
            
            self._start_optimization_process(valid_images, target_rect, subtitle_lines, preset_path, preset_data, mode)

        # Open shared Wizard
        OptimizationCaptureWindow(self.root, on_wizard_finish)

    def _start_optimization_process(self, images, rough_area, subtitle_lines, path, data, mode="Full Lines"):
            # 4. Uruchomienie algorytmu w wątku (z UI oczekiwania)
            wait_win = tk.Toplevel(self.root)
            wait_win.title("Przetwarzanie...")
            wait_win.geometry("400x150")
            wait_win.resizable(False, False)
            
            lbl = ttk.Label(wait_win, text="Trwa analiza obrazu i szukanie optymalnych ustawień.\nMoże to potrwać dłuższą chwilę...", justify="center")
            lbl.pack(pady=20)
            
            pbar = ttk.Progressbar(wait_win, mode='indeterminate')
            pbar.pack(fill=tk.X, padx=30, pady=10)
            pbar.start(15)

            # Thread context
            thread_context = {"result": None, "error": None}

            def worker():
                try:
                    optimizer = SettingsOptimizer(self.config_mgr)
                    # optimizer.optimize supports list of images now
                    res = optimizer.optimize(images, rough_area, subtitle_lines, mode)
                    thread_context["result"] = res
                except Exception as e:
                    thread_context["error"] = e

            t = threading.Thread(target=worker, daemon=True)
            t.start()
            
            def check_thread():
                if t.is_alive():
                    self.root.after(100, check_thread)
                else:
                    wait_win.destroy()
                    self.root.deiconify()
                    self._on_optimization_finished(thread_context, path, data, subtitle_lines)

            check_thread()

    def _unused_legacy_detect_method(self):
        # Placeholder to replace original method body cleanly
        pass

    def _on_optimization_finished(self, context, preset_path, preset_data, subtitle_lines):
        if context["error"]:
            messagebox.showerror("Błąd", f"Błąd podczas optymalizacji: {context['error']}")
            return

        result = context["result"]
        if not result:
             messagebox.showerror("Błąd", "Brak wyników z optymalizatora.")
             return

        score = result.get('score', 0)
        
        if score < 50:
            display_score = min(score, 100)
            messagebox.showwarning("Wynik", f"Nie znaleziono dobrych ustawień (Score: {display_score:.1f}%).\nSpróbuj zmienić obszar lub klatkę z gry. Najlepsze co mamy to: {display_score:.1f}%")
            return

        best_settings = result.get('settings', {})
        optimized_area = result.get('optimized_area')
        
        # Select result dialog
        current_areas = preset_data.get('areas', [])
        dialog_res = self._show_custom_result_dialog(score, best_settings, optimized_area, current_areas, subtitle_lines)
        
        if dialog_res and dialog_res["confirmed"]:
            # 5. Kopia zapasowa
            bkp = self.config_mgr.backup_preset(preset_path)
            if bkp:
                print(f"Kopia zapasowa: {bkp}")
            
            # 6. Zapis
            preset_data.update(best_settings)
            
            if optimized_area:
                 ox, oy, ow, oh = optimized_area
                 new_rect = {'left': ox, 'top': oy, 'width': ow, 'height': oh}
                 
                 target_id = dialog_res["target_id"]
                 
                 if target_id is None:
                     # Create new
                     existing_ids = [a.get('id', 0) for a in current_areas]
                     new_id = (max(existing_ids) if existing_ids else 0) + 1
                     current_areas.append({
                         "id": new_id, 
                         "type": "continuous", 
                         "rect": new_rect, 
                         "hotkey": "", 
                         "settings": best_settings
                     })
                 else:
                     # Update existing
                     for area in current_areas:
                         if area.get('id') == target_id:
                             # Update rect if provided
                             if optimized_area:
                                 area['rect'] = {
                                     'left': int(optimized_area[0]),
                                     'top': int(optimized_area[1]),
                                     'width': int(optimized_area[2]),
                                     'height': int(optimized_area[3])
                                 }
                             
                             # Update or create settings dict
                             if 'settings' not in area:
                                 area['settings'] = {}
                             area['settings'].update(best_settings)
                             
                             # Remove legacy top-level colors if present to avoid confusion
                             if 'colors' in area:
                                 del area['colors']
                             break
                 
                 preset_data['areas'] = current_areas
            elif dialog_res["target_id"] is not None:
                # Update settings only (no area change)
                 target_id = dialog_res["target_id"]
                 for area in current_areas:
                     if area.get('id') == target_id:
                         if 'settings' not in area:
                             area['settings'] = {}
                         area['settings'].update(best_settings)
                         if 'colors' in area: del area['colors']
                         break
                 preset_data['areas'] = current_areas

            self.config_mgr.save_preset(preset_path, preset_data)
            
            # Przeładowanie GUI
            self.on_preset_selected_from_combo(None)
            messagebox.showinfo("Gotowe", "Ustawienia zostały zaktualizowane.")

    def _show_custom_result_dialog(self, score, settings, optimized_area, existing_areas, subtitle_lines=None):
        dialog = tk.Toplevel(self.root)
        dialog.title(f"Wynik Optymalizacji")
        dialog.geometry("450x700")
        
        content = tk.Frame(dialog, padx=20, pady=20)
        content.pack(fill="both", expand=True)

        tk.Label(content, text="Znaleziono optymalne ustawienia", font=("Arial", 12, "bold")).pack(pady=(0, 15))
        
        def add_row_custom(label, widget_creator_func):
            f = tk.Frame(content)
            f.pack(fill="x", pady=3)
            tk.Label(f, text=label, width=22, anchor="w", fg="#555").pack(side="left", anchor="n")
            w = widget_creator_func(f)
            w.pack(side="left", fill='x', expand=True, anchor="w")

        def add_text_row(label, value):
            add_row_custom(label, lambda p: tk.Label(p, text=str(value), anchor="w", font=("Arial", 10, "bold"), wraplength=200, justify="left"))

        display_score = min(score, 100)
        add_text_row("Wynik (Score):", f"{display_score:.1f}%")
        
        # Area info
        if optimized_area:
            ox, oy, ow, oh = optimized_area
            area_str = f"X: {ox}, Y: {oy}, Wymiary: {ow}x{oh}"
            add_text_row("Wykryty obszar:", area_str)

        add_text_row("Jasność (Threshold):", settings.get('brightness_threshold', '-'))
        add_text_row("Kontrast:", settings.get('contrast', '-'))
        add_text_row("Skala OCR:", settings.get('ocr_scale_factor', '-'))
        add_text_row("Tryb koloru:", settings.get('text_color_mode', '-'))
        
        # Colors with swatches
        cols = settings.get('subtitle_colors', [])
        
        def create_color_widget(parent):
            if not cols:
                 return tk.Label(parent, text="Brak (Grayscale)", font=("Arial", 10, "bold"), anchor="w")
            
            f_cols = tk.Frame(parent)
            for c in cols:
                row = tk.Frame(f_cols)
                row.pack(fill="x", pady=1)
                tk.Label(row, relief="solid", borderwidth=1, bg=c, width=3, height=1).pack(side="left", padx=(0, 5))
                tk.Label(row, text=c, font=("Arial", 10, "bold")).pack(side="left")
            return f_cols

        add_row_custom("Kolory:", create_color_widget)
        add_text_row("Tolerancja:", settings.get('color_tolerance', '-'))

        # Area Selection
        tk.Label(content, text="\nZastosuj ustawienia do:", font=("Arial", 11, "bold")).pack(pady=(15, 5), anchor="w")
        
        area_options = ["Utwórz nowy obszar"]
        area_map = {} 
        
        for a in existing_areas:
            aid = a.get('id')
            aname = f"Obszar {aid}"
            if a.get('type'):
                aname += f" ({a.get('type')})"
            area_options.append(aname)
            area_map[aname] = aid
            
        # Default to Area #1 if available
        default_val = area_options[0]
        for name, aid in area_map.items():
            if aid == 1:
                default_val = name
                break
                
        selected_option = tk.StringVar(value=default_val)
        cb = ttk.Combobox(content, textvariable=selected_option, values=area_options, state="readonly", font=("Arial", 10))
        cb.pack(fill="x", pady=5)
        
        tk.Label(content, text="\nCzy chcesz zapisać te ustawienia?", font=("Arial", 11)).pack(pady=20)
        
        btn_frame = tk.Frame(dialog, pady=5)
        btn_frame.pack(fill="x", side="bottom", pady=10)
        
        result = {"confirmed": False, "target_id": None}
        
        def on_yes():
            result["confirmed"] = True
            val = selected_option.get()
            if val == "Utwórz nowy obszar":
                result["target_id"] = None
            else:
                result["target_id"] = area_map.get(val)
            dialog.destroy()
            
        def on_no():
            dialog.destroy()
            
        tk.Button(btn_frame, text="Zastosuj", command=on_yes, width=15, height=2, bg="#e0ffe0").pack(side="left", padx=5, expand=True)
        tk.Button(btn_frame, text="Anuluj", command=on_no, width=10, height=2).pack(side="right", padx=5, expand=True)
        
        def on_test():
             if not subtitle_lines:
                 messagebox.showerror("Błąd", "Brak danych tekstowych do weryfikacji.")
                 return
                 
             dialog.withdraw()
             self.root.withdraw()
             time.sleep(0.3)
             
             try:
                 img = capture_fullscreen()
                 if not img:
                      messagebox.showerror("Błąd", "Nie udało się wykonać zrzutu ekranu.")
                      dialog.deiconify()
                      self.root.deiconify()
                      return
                 
                 # Show Progress
                 p_win = tk.Toplevel(self.root)
                 p_win.title("Weryfikacja...")
                 tk.Label(p_win, text="Sprawdzanie aktualnych ustawień...").pack(padx=20, pady=20)
                 p_win.update()
                 
                 from app.matcher import precompute_subtitles
                 pre_db = precompute_subtitles(subtitle_lines)
                 
                 ox, oy, ow, oh = optimized_area
                 img_w, img_h = img.size
                 cx = max(0, ox); cy = max(0, oy)
                 cw = min(ow, img_w - cx); ch = min(oh, img_h - cy)
                 
                 crop = img.crop((cx, cy, cx+cw, cy+ch))
                 
                 optimizer = SettingsOptimizer()
                 cur_score, _ = optimizer._evaluate_settings(crop, settings, pre_db, settings.get('subtitle_mode', 'Full Lines'))
                 
                 p_win.destroy()
                 
                 msg = f"Wynik na nowym zrzucie: {cur_score:.1f}"
                 better_res = None
                 
                 if cur_score < 101:
                      if messagebox.askyesno("Wynik", f"{msg}\n\nCzy chcesz spróbować znaleźć LEPSZE ustawienia dla tego zrzutu?"):
                           # Optimize
                           w2 = tk.Toplevel(self.root)
                           tk.Label(w2, text="Szukam lepszych ustawień...").pack(padx=20, pady=20)
                           w2.update()
                           
                           res = optimizer.optimize(img, (ox, oy, ow, oh), subtitle_lines, settings.get('subtitle_mode', 'Full Lines'))
                           w2.destroy()
                           
                           if res and res.get('score', 0) > cur_score:
                                better_res = res
                                msg += f"\n\nZnaleziono lepsze: {res['score']:.1f}"
                           else:
                                msg += "\n\nNie znaleziono lepszych."
                 else:
                      msg += "\n\nIdealne dopasowanie (Exact Match)."
                      
                 if better_res:
                      if messagebox.askyesno("Lepszy wynik", msg + "\n\nCzy chcesz użyć NOWYCH ustawień?"):
                           dialog.destroy()
                           self.root.deiconify()
                           # Recursive reopen with new settings
                           self._show_custom_result_dialog(better_res['score'], better_res['settings'], better_res['optimized_area'], existing_areas, subtitle_lines)
                           return
                 else:
                      messagebox.showinfo("Info", msg)
                 
                 dialog.deiconify()
                 self.root.deiconify()

             except Exception as e:
                 messagebox.showerror("Błąd", str(e))
                 try: p_win.destroy() 
                 except: pass
                 dialog.deiconify()
                 self.root.deiconify()
                 
        tk.Button(btn_frame, text="Testuj ustawienia", command=on_test).pack(side="left", padx=5)
        
        dialog.transient(self.root)
        dialog.wait_visibility()
        dialog.grab_set()
        self.root.wait_window(dialog)
        
        return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--preset', type=str)
    parser.add_argument('game_command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    cmd = args.game_command
    if cmd and cmd[0] == '--': cmd.pop(0)
    root = tk.Tk(className='Lektor')
    LektorApp(root, args.preset, cmd)
    root.mainloop()


if __name__ == "__main__":
    main()