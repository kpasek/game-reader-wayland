#!/usr/bin/env python3
import sys
import os
import queue
import threading
from app.optimization_result import OptimizationResultWindow
from app.processing_window import ProcessingWindow
from app.optimization_wizard import OptimizationWizard
import subprocess
import time
import argparse
import platform
from typing import Optional

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox
except ImportError:
    print("Błąd: Brak biblioteki tkinter.", file=sys.stderr)
    sys.exit(1)
import customtkinter as ctk

# Initialize customtkinter appearance so CTk widgets and windows use the chosen theme.
# Default to system appearance; change to 'dark' or 'light' to force a mode.
try:
    ctk.set_appearance_mode("system")
    ctk.set_default_color_theme("blue")
except Exception:
    # Fail gracefully if customtkinter doesn't expose these (older versions/tests)
    pass

from app.ctk_widgets import CTkFrame, CTkLabel, make_button, make_combobox, make_slider


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

from app.config_manager import (
    ConfigManager,
    AreaConfig,
    STANDARD_WIDTH,
    STANDARD_HEIGHT,
)
from app.reader import ReaderThread
from app.player import PlayerThread
from app.log import LogWindow
from app.settings import SettingsDialog
from app.area_selector import AreaSelector, ColorSelector
from app.area_manager import AreaManagerWindow
from app.capture import capture_fullscreen, reset_pipewire_source, SCREENSHOT_BACKEND
from app.help import HelpWindow
from app.optimizer import SettingsOptimizer
from app.geometry_utils import calculate_merged_area

# Global events/queues
stop_event = threading.Event()
audio_queue = queue.Queue()
log_queue = queue.Queue()
debug_queue = queue.Queue()

APP_VERSION = "v1.10.0"


class LektorApp:
    def __init__(self, root: tk.Tk, autostart_preset: Optional[str], game_cmd: list):
        self.root = root
        self.root.title(f"Lektor {APP_VERSION}")
        self.root.geometry("730x500")

        self.config_mgr = ConfigManager()
        self.game_cmd = game_cmd
        self.game_process = None

        self.reader_thread = None
        self.player_thread = None
        self.log_window = None
        self.help_window = None
        self.is_running = False
        self.hotkey_listener = None
        self.area_mgr_win = None

        # Zmienne UI
        self.var_preset_display = tk.StringVar()
        self.full_preset_paths = []
        self.var_preset_full_path = tk.StringVar()
        self.preset_map = {}

        # Opcje Lektora

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
        # Ensure any change to var_resolution updates ConfigManager immediately
        self.var_resolution.trace_add(
            "write", lambda *a: self._on_resolution_selected()
        )
        self.var_speed = tk.DoubleVar(value=1.2)
        self.var_volume = tk.DoubleVar(value=1.0)
        self.var_audio_ext = tk.StringVar(value=".mp3")

        self.regex_map = {
            "Brak": r"",
            "Standard (Imię: Dialog)": r"^(?i)({NAMES})\s*[:：\-; ]*",
            "Nawiasy ([Imię] Dialog)": r"^\[({NAMES})\]",
            "Imię na początku": r"^({NAMES})\s+",
            "Własny (Regex)": "CUSTOM",
        }

        self.resolutions = [
            "1920x1080",
            "2560x1440",
            "3840x2160",
            "1280x800",
            "2560x1600",
            "Niestandardowa",
        ]

        self._init_gui()
        self._load_initial_state(autostart_preset)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self._check_debug_queue()

        if HAS_PYNPUT:
            self._start_hotkey_listener()

    # --- LOGIKA SKALI OCR ---
    def _on_resolution_selected(self, event=None):
        """Handler for resolution combobox selection: persist and update ConfigManager."""
        res_str = self.var_resolution.get()
        # Persist user choice
        self.config_mgr.last_resolution_key = res_str
        # Update ConfigManager display resolution
        if "x" in res_str:
            w, h = map(int, res_str.split("x"))
            self.config_mgr.display_resolution = (w, h)

    # -----------------------

    def _start_hotkey_listener(self):
        hk_start = self.config_mgr.hotkey_start_stop

        if hasattr(self, "hotkey_listener") and self.hotkey_listener:
            try:
                self.hotkey_listener.stop()
            except:
                pass

        hotkeys = {
            hk_start: self._on_hotkey_start_stop,
            "<f9>": self.change_source,
        }

        # Load areas from current preset
        path = self.var_preset_full_path.get()
        if path and os.path.exists(path):
            data = self.config_mgr.load_preset(path)
            if data and data.areas:
                for area in data.areas:
                    hk = area.hotkey
                    aid = area.id
                    atype = area.type
                    if hk:
                        # Capture aid in lambda default arg
                        hotkeys[hk] = lambda aid=aid, t=atype: (
                            self._on_hotkey_area_action(aid, t)
                        )

        try:
            self.hotkey_listener = keyboard.GlobalHotKeys(hotkeys)
            self.hotkey_listener.start()
        except Exception as e:
            print(f"Ostrzeżenie: Nie udało się zarejestrować skrótów globalnych: {e}")

    def _restart_hotkeys(self):
        if HAS_PYNPUT:
            self._start_hotkey_listener()

    def _on_hotkey_start_stop(self):
        self.root.after(0, self._toggle_start_stop_hotkey)

    def _on_hotkey_area_action(self, area_id, area_type):
        self.root.after(0, lambda: self._trigger_reader_area(area_id, area_type))

    def _toggle_start_stop_hotkey(self):
        if self.is_running:
            self.stop_reading()
        else:
            self.start_reading()

    def _trigger_reader_area(self, area_id, area_type="manual"):
        if self.is_running and self.reader_thread:
            if area_type == "continuous":
                self.reader_thread.toggle_continuous_area(area_id)
            else:
                self.reader_thread.trigger_area(area_id)

    def _init_gui(self):
        menubar = tk.Menu(self.root)

        preset_menu = tk.Menu(menubar, tearoff=0)
        preset_menu.add_command(
            label="Wybierz katalog...", command=self.browse_lector_folder
        )
        preset_menu.add_separator()
        preset_menu.add_command(
            label="Zmień folder audio", command=lambda: self.change_path("audio_dir")
        )
        preset_menu.add_command(
            label="Zmień plik napisów",
            command=lambda: self.change_path("text_file_path"),
        )
        preset_menu.add_command(
            label="Importuj preset (Game Reader)", command=self.import_preset_dialog
        )
        # Removed 'Wykryj optymalne ustawienia' as requested
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
        self.root.configure(menu=menubar)

        panel = CTkFrame(self.root, fg_color="transparent")
        panel.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)

        CTkLabel(panel, text="Aktywny lektor (Katalog):").pack(anchor=tk.W, pady=(0, 5))
        # Use factory for comboboxes (falls back to ttk.Combobox if CTk lacks one)
        self.cb_preset = make_combobox(
            panel,
            textvariable=self.var_preset_display,
            state="readonly",
            width=350,
            command=self._on_preset_selection_changed,
        )
        self.cb_preset.pack(fill=tk.X, pady=(0, 15))

        # --- ROZDZIELCZOŚĆ ---
        f_res = CTkFrame(panel, fg_color="transparent")
        f_res.pack(fill=tk.X, pady=(0, 15))
        CTkLabel(f_res, text="Rozdzielczość:").pack(side=tk.LEFT)
        self.cb_res = make_combobox(
            f_res, textvariable=self.var_resolution, values=self.resolutions
        )
        self.cb_res.pack(side=tk.LEFT, padx=5)
        self.cb_res.bind("<<ComboboxSelected>>", self._on_resolution_selected)
        make_button(
            f_res,
            text="Dopasuj rozdz.",
            command=self.auto_detect_resolution,
            fg_color="#2980b9",
            hover_color="#21618c",
            text_color="#ffffff",
        ).pack(side=tk.LEFT, padx=5)

        self.btn_change_source = make_button(
            f_res,
            text="Zmień okno (F9)",
            command=self.change_source,
            fg_color="#8e44ad",
            hover_color="#732d91",
            text_color="#ffffff",
        )
        self.btn_change_source.pack(side=tk.LEFT, padx=5)

        # Disable by default if not wayland
        if SCREENSHOT_BACKEND != "pipewire_wayland":
            self.btn_change_source.configure(state="disabled")

        # Actions Panel (Replaces Colors Panel)
        grp_act = CTkFrame(panel, fg_color="transparent")
        grp_act.pack(fill=tk.X, pady=(0, 15))
        # Big Buttons for main actions
        btn_detect = make_button(
            grp_act,
            text="Wykryj Ustawienia",
            command=self.detect_optimal_settings,
            fg_color="#1f6aa5",
            hover_color="#145f8a",
            text_color="#ffffff",
        )
        btn_detect.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)

        btn_areas = make_button(
            grp_act,
            text="Zarządzaj Obszarami",
            command=self.open_area_manager,
            fg_color="#6c757d",
            hover_color="#5a6268",
            text_color="#ffffff",
        )
        btn_areas.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)

        # Przycisk Ustawienia
        self.btn_settings = make_button(
            grp_act,
            text="⚙ Ustawienia",
            command=self.open_settings,
            fg_color="#7f8c8d",
            hover_color="#6c7a7b",
            text_color="#ffffff",
        )
        self.btn_settings.pack(side=tk.LEFT, padx=5)

        # Removed old subtitle colors section
        # grp_sub = ttk.LabelFrame(panel, text="Kolory napisów", padding=10) ...

        # --- AUDIO + SKALA OCR ---
        grp_aud = CTkFrame(panel, fg_color="transparent")
        grp_aud.pack(fill=tk.X, pady=(0, 20))

        CTkLabel(grp_aud, text="Prędkość:").grid(row=0, column=0)
        s_spd = make_slider(
            grp_aud,
            from_=0.9,
            to=1.5,
            variable=self.var_speed,
            command=lambda v: (
                self.lbl_spd.configure(text=f"{float(v):.2f}x")
                if hasattr(self, "lbl_spd")
                else None
            ),
        )
        s_spd.grid(row=0, column=1, sticky="ew", padx=10)
        try:
            s_spd.bind(
                "<ButtonRelease-1>",
                lambda e: setattr(
                    self.config_mgr, "audio_speed", round(self.var_speed.get(), 2)
                ),
            )
        except Exception:
            pass
        self.lbl_spd = CTkLabel(grp_aud, text="1.00x", width=5)
        self.lbl_spd.grid(row=0, column=2)

        CTkLabel(grp_aud, text="Głośność:").grid(row=1, column=0)
        s_vol = make_slider(
            grp_aud,
            from_=0.0,
            to=1.5,
            variable=self.var_volume,
            command=lambda v: self.lbl_vol.configure(text=f"{float(v):.2f}"),
        )
        s_vol.grid(row=1, column=1, sticky="ew", padx=10)
        try:
            s_vol.bind(
                "<ButtonRelease-1>",
                lambda e: setattr(
                    self.config_mgr, "audio_volume", round(self.var_volume.get(), 2)
                ),
            )
        except Exception:
            pass
        self.lbl_vol = CTkLabel(grp_aud, text="1.00", width=5)
        self.lbl_vol.grid(row=1, column=2)

        CTkLabel(grp_aud, text="Format:").grid(row=2, column=0)
        CTkLabel(
            grp_aud, textvariable=self.var_audio_ext, font=("Arial", 8, "bold")
        ).grid(row=2, column=1, sticky="w", padx=10)
        grp_aud.columnconfigure(1, weight=1)

        grp_aud.columnconfigure(1, weight=1)

        # --- STEROWANIE ---
        hk_start = self.config_mgr.hotkey_start_stop
        frm_btn = CTkFrame(panel, fg_color="transparent")
        frm_btn.pack(side=tk.BOTTOM, fill=tk.X, pady=(10, 0))

        self.btn_start = make_button(
            frm_btn,
            text=f"START ({hk_start})",
            command=self.start_reading,
            fg_color="#27ae60",
            hover_color="#1e8449",
            text_color="#ffffff",
        )
        self.btn_start.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        self.btn_stop = make_button(
            frm_btn,
            text=f"STOP ({hk_start})",
            command=self.stop_reading,
            state="disabled",
            fg_color="#c0392b",
            hover_color="#992d22",
            text_color="#ffffff",
        )
        self.btn_stop.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)

        CTkLabel(self.root, text=f"Wersja: {APP_VERSION}", font=("Arial", 8)).pack(
            side=tk.BOTTOM, anchor=tk.E, padx=5
        )

        self.root.after(200, self.refresh_color_canvas)

    def auto_detect_resolution(self):
        # We prefer capture_fullscreen dimensions because it matches the
        # physical pixel grid used by the reader and coordinate mapping.
        import app.capture

        img = None
        # Zapobiegaj wywołaniu portalu PipeWire przy starcie aplikacji (lazy loading)
        if (
            app.capture.SCREENSHOT_BACKEND == "pipewire_wayland"
            and app.capture._PIPEWIRE_CAPTURE is None
        ):
            pass
        else:
            img = capture_fullscreen()

        if img:
            w, h = img.size
        else:
            w = self.root.winfo_screenwidth()
            h = self.root.winfo_screenheight()

        res_str = f"{w}x{h}"
        self.var_resolution.set(res_str)
        # Persist and inform ConfigManager about current UI resolution
        self.config_mgr.last_resolution_key = res_str
        self.config_mgr.display_resolution = (w, h)

    def _load_initial_state(self, autostart_path):
        self._update_preset_list()
        initial_path = (
            autostart_path
            if autostart_path
            else (self.full_preset_paths[0] if self.full_preset_paths else None)
        )
        if initial_path and os.path.exists(initial_path):
            self.var_preset_full_path.set(initial_path)
            # Find display name in map and set it
            for d_name, p_path in self.preset_map.items():
                if p_path == initial_path:
                    self.var_preset_display.set(d_name)
                    break
            self.on_preset_loaded()
            if autostart_path:
                self.root.after(500, self.start_reading)

        self.var_regex_mode.set(self.config_mgr.last_regex_mode)
        self.var_custom_regex.set(self.config_mgr.last_custom_regex)
        self.auto_detect_resolution()
        self.on_regex_changed()

    def _update_preset_list(self):
        recents = self.config_mgr.recent_presets_list
        self.full_preset_paths = recents

        self.preset_map = {}
        display_names = []

        for path in recents:
            if not path:
                continue
            # Extract the directory name containing the preset
            dir_name = os.path.basename(os.path.dirname(path))
            if not dir_name:
                dir_name = "Unknown"

            display_name = dir_name
            counter = 1
            # Ensure unique display name by checking mapping
            while (
                display_name in self.preset_map
                and self.preset_map[display_name] != path
            ):
                parent_dir = os.path.basename(os.path.dirname(os.path.dirname(path)))
                if parent_dir:
                    display_name = f"{dir_name} ({parent_dir})"
                else:
                    display_name = f"{dir_name} ({counter})"

                if (
                    display_name in self.preset_map
                    and self.preset_map[display_name] != path
                ):
                    display_name = f"{dir_name} ({counter})"
                    counter += 1

            self.preset_map[display_name] = path
            if display_name not in display_names:
                display_names.append(display_name)

        self.cb_preset.configure(values=display_names)

        current_path = self.var_preset_full_path.get()
        if current_path:
            # Find display name for current full path and update combobox
            for d_name, p_path in self.preset_map.items():
                if p_path == current_path:
                    self.cb_preset.set(d_name)
                    break

    def _on_preset_selection_changed(self, choice):
        """Handler for preset combobox selection."""
        if choice and choice in self.preset_map:
            full_path = self.preset_map[choice]
            self.config_mgr.load_preset(full_path)
            self.var_preset_full_path.set(full_path)
            self.on_preset_loaded()

    def on_preset_loaded(self):
        path = self.var_preset_full_path.get()
        if not path or not os.path.exists(path):
            return

        # Mark as current in manager
        self.config_mgr.preset_path = path
        self.config_mgr.load_preset(path)

        base_dir = os.path.dirname(path)

        if not self.config_mgr.text_file_path:
            try:
                for f in sorted(os.listdir(base_dir)):
                    if f.lower().endswith(".txt"):
                        self.config_mgr.text_file_path = os.path.join(base_dir, f)
                        break
            except Exception:
                pass

        if not self.config_mgr.audio_dir:
            try:
                for f in sorted(os.listdir(base_dir)):
                    full_p = os.path.join(base_dir, f)
                    if os.path.isdir(full_p):
                        self.config_mgr.audio_dir = full_p
                        break
            except Exception:
                pass

        # Sync UI state from canonical properties via ConfigManager
        self.var_speed.set(self.config_mgr.audio_speed)
        self.lbl_spd.configure(text=f"{self.var_speed.get():.2f}x")

        self.var_volume.set(self.config_mgr.audio_volume)
        self.lbl_vol.configure(text=f"{self.var_volume.get():.2f}")

        # Automatyczna detekcja formatu audio
        detected_ext = self._detect_audio_format(self.config_mgr.audio_dir or "")
        if detected_ext and detected_ext != self.config_mgr.audio_ext:
            self.config_mgr.audio_ext = detected_ext

        self.var_audio_ext.set(self.config_mgr.audio_ext)
        self.var_auto_names.set(self.config_mgr.auto_remove_names)
        self.var_capture_interval.set(self.config_mgr.capture_interval)
        self.var_min_line_len.set(self.config_mgr.min_line_length)
        self.var_save_logs.set(self.config_mgr.save_logs)
        self.var_show_debug.set(self.config_mgr.show_debug)
        self.var_brightness_threshold.set(self.config_mgr.brightness_threshold)
        self.var_similarity.set(self.config_mgr.similarity)
        self.var_contrast.set(self.config_mgr.contrast)
        self.var_tolerance.set(self.config_mgr.color_tolerance)
        self.var_text_thickening.set(self.config_mgr.text_thickening)

        self.var_match_score_short.set(self.config_mgr.match_score_short)
        self.var_match_score_long.set(self.config_mgr.match_score_long)
        self.var_match_len_diff.set(self.config_mgr.match_len_diff_ratio)
        self.var_partial_min_len.set(self.config_mgr.partial_mode_min_len)
        self.var_audio_speed.set(self.config_mgr.audio_speed_inc)

        if self.config_mgr.regex_mode_name:
            self.var_regex_mode.set(self.config_mgr.regex_mode_name)
            if self.config_mgr.regex_mode_name == "Własny (Regex)":
                self.var_custom_regex.set(self.config_mgr.regex_pattern or "")
            self.on_regex_changed()

        # Refresh Area Manager if open
        if self.area_mgr_win and self.area_mgr_win.winfo_exists():
            self.area_mgr_win.refresh_data()

        self.refresh_color_canvas()

    def on_regex_changed(self, event=None):
        mode = self.var_regex_mode.get()

        if hasattr(self, "ent_regex") and self.ent_regex:
            try:
                self.ent_regex.configure(
                    state="normal" if mode == "Własny (Regex)" else "disabled"
                )
            except Exception:
                self.ent_regex = None

        self.config_mgr.last_regex_mode = mode
        if mode != "Własny (Regex)":
            self.config_mgr.regex_pattern = self.regex_map.get(mode, "")
            self.config_mgr.regex_mode_name = mode

    def browse_lector_folder(self):
        d = filedialog.askdirectory(title="Wybierz katalog z lektorem")
        if not d:
            return
        p = self.config_mgr.ensure_preset_exists(d)
        self.config_mgr.add_recent_preset(p)
        self.var_preset_full_path.set(p)
        self._update_preset_list()
        self.on_preset_loaded()

    def change_path(self, key):
        if not self.var_preset_full_path.get():
            return messagebox.showerror("Błąd", "Wybierz profil.")
        base = os.path.dirname(self.var_preset_full_path.get())
        if key == "audio_dir":
            new = filedialog.askdirectory(initialdir=base)
        else:
            new = filedialog.askopenfilename(
                initialdir=base, filetypes=[("Text", "*.txt")]
            )
        if new:
            setattr(self.config_mgr, key, new)

    def set_area(self, idx):
        path = self.var_preset_full_path.get()
        if not path:
            return messagebox.showerror("Błąd", "Wybierz profil.")
        self.root.withdraw()
        time.sleep(0.3)
        img = capture_fullscreen()
        if not img:
            self.root.deiconify()
            return
        sw, sh = img.size

        old_disp = self.config_mgr.display_resolution
        try:
            self.config_mgr.display_resolution = (sw, sh)
            areas = self.config_mgr.areas  # Scaled to screen resolution

            # Map index to IDs
            id_to_find = f"area_{idx}"

            # Extract rects for AreaSelector [slot 0, slot 1, slot 2]
            disp_mons = [None, None, None]
            for area in areas:
                if area.id == "area_0":
                    disp_mons[0] = area.rect
                elif area.id == "area_1":
                    disp_mons[1] = area.rect
                elif area.id == "area_2":
                    disp_mons[2] = area.rect

            sel = AreaSelector(self.root, img, existing_regions=disp_mons)
            self.root.deiconify()

            if sel.geometry:
                rect = sel.geometry
                found = False
                for area in areas:
                    if area.id == id_to_find:
                        area.rect = rect
                        found = True
                        break
                if not found:
                    areas.append(AreaConfig(rect=rect, id=id_to_find, type="subtitle"))

                # Persist via authoritative ConfigManager property
                self.config_mgr.areas = areas
        finally:
            self.config_mgr.display_resolution = old_disp

    def clear_area(self, idx):
        path = self.var_preset_full_path.get()
        if not path:
            return

        id_to_clear = f"area_{idx}"
        areas = self.config_mgr.areas
        new_areas = [a for a in areas if a.id != id_to_clear]
        self.config_mgr.areas = new_areas

    def open_settings(self):
        SettingsDialog(self.root, self.config_mgr.settings, self)
        self.config_mgr.save_app_config()
        self._restart_hotkeys()
        hk = self.config_mgr.hotkey_start_stop
        self.btn_start.configure(text=f"START ({hk})")
        self.btn_stop.configure(text=f"STOP ({hk})")

        # Odśwież dostępność przycisku Zmień Okno
        import app.capture

        if app.capture._determine_backend() == "pipewire_wayland":
            self.btn_change_source.configure(state="normal")
        else:
            self.btn_change_source.configure(state="disabled")

    def change_source(self):
        """Zmienia źródło okna/ekranu dla backendu PipeWire."""
        import app.capture

        if app.capture._determine_backend() != "pipewire_wayland":
            messagebox.showinfo(
                "Informacja",
                "Dynamiczna zmiana źródła jest obsługiwana tylko przez backend PipeWire (Wayland).",
            )
            return

        self.root.withdraw()
        time.sleep(0.3)

        # Zatrzymanie aktywnego czytania, aby zapobiec crashom przy wymianie portalu
        was_running = self.is_running
        if was_running:
            self.stop_reading()

        success = reset_pipewire_source()

        self.root.deiconify()

        if success:
            if was_running:
                self.start_reading()

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
        if not path or not os.path.exists(path):
            return messagebox.showerror("Błąd", "Brak profilu.")

        # Trigger explicit portal if pipewire is active and not initialized
        import app.capture

        if (
            app.capture.SCREENSHOT_BACKEND == "pipewire_wayland"
            and app.capture._PIPEWIRE_CAPTURE is None
        ):
            try:
                app.capture._get_pipewire_capture()
            except Exception as e:
                # Cancelled or failed silently
                return

        self.config_mgr.add_recent_preset(path)
        self._update_preset_list()

        # Wymuś ponowne wczytanie presetów z pliku (czyść cache)
        self.config_mgr.preset_cache = None

        mode = self.var_regex_mode.get()

        res_str = self.var_resolution.get()
        target_res = tuple(map(int, res_str.split("x"))) if "x" in res_str else None
        if target_res:
            self.config_mgr.display_resolution = target_res

        stop_event.clear()
        with audio_queue.mutex:
            audio_queue.queue.clear()

        self.player_thread = PlayerThread(
            stop_event,
            audio_queue,
            base_speed_callback=lambda: self.var_speed.get(),
            volume_callback=lambda: self.var_volume.get(),
        )
        self.reader_thread = ReaderThread(
            config_manager=self.config_mgr,
            stop_event=stop_event,
            audio_queue=audio_queue,
            target_resolution=target_res,
            player_thread=self.player_thread,
            log_queue=log_queue,
            debug_queue=debug_queue,
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
        if self.reader_thread:
            self.reader_thread.join(1.0)
        self._toggle_ui(False)

    def _toggle_ui(self, running):
        s = "disabled" if running else "normal"
        self.btn_start.configure(state=s)
        self.btn_stop.configure(state="normal" if running else "disabled")
        self.cb_preset.configure(state=s)
        self.cb_res.configure(state=s)

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
        if self.reader_thread and self.reader_thread.is_alive():
            self.stop_reading()
        if self.game_process:
            self.game_process.terminate()
        if hasattr(self, "hotkey_listener") and self.hotkey_listener:
            self.hotkey_listener.stop()
        self.root.destroy()

    def _check_debug_queue(self):
        """Sprawdza, czy są nowe ramki do narysowania."""
        try:
            while True:
                msg_type, data = debug_queue.get_nowait()
                if msg_type == "overlay":
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
        color = "red"
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
                top.attributes("-topmost", True)
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
            windows.append(
                create_strip(
                    f"{thickness}x{h_inner}+{x + w - thickness}+{y + thickness}"
                )
            )

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
            messagebox.showerror(
                "Błąd", "Najpierw wybierz lub utwórz aktywny preset Lektora."
            )
            return

        file_path = filedialog.askopenfilename(
            title="Wybierz plik ustawień (Game Reader)",
            filetypes=[("Pliki JSON", "*.json"), ("Wszystkie pliki", "*.*")],
        )
        if not file_path:
            return

        if self.config_mgr.import_gr_preset(file_path, current_path):
            messagebox.showinfo("Sukces", "Zaimportowano obszar i przeskalowano do 4K.")
            # Odśwież UI wczytując ponownie preset
            self.on_preset_loaded()
        else:
            messagebox.showerror(
                "Błąd", "Nie udało się zaimportować ustawień. Sprawdź plik."
            )

    def _is_main_area(self, area_id):
        return (
            area_id == 1
            or str(area_id).lower() == "area_0"
            or str(area_id).lower() == "area_1"
        )

    def refresh_color_canvas(self):
        """Rysuje listę kolorów na nowym Canvasie."""
        if not hasattr(self, "color_canvas"):
            return

        self.color_canvas.delete("all")

        # Use authoritative ConfigManager to get areas
        areas = self.config_mgr.get_areas()
        colors = []
        if areas:
            a1 = next((a for a in areas if self._is_main_area(a.id)), None)
            if a1:
                colors = a1.colors
        else:
            colors = self.config_mgr.colors

        x_offset = 2
        y_pos = 2
        size = 20

        if not colors:
            self.color_canvas.create_text(
                5, 12, text="(brak filtrów - domyślny tryb)", anchor=tk.W, fill="gray"
            )
            return
        for i, color in enumerate(colors):
            tag_name = f"color_{i}"
            try:
                self.color_canvas.create_rectangle(
                    x_offset,
                    y_pos,
                    x_offset + size,
                    y_pos + size,
                    fill=color,
                    outline="#555555",
                    tags=(tag_name, "clickable"),
                )
            except Exception:
                pass
            x_offset += size + 5

    def add_subtitle_color(self):
        """Obsługa wyboru koloru pipetą (tylko dla Obszaru 1)."""
        self.root.withdraw()
        self.root.update()
        time.sleep(0.3)
        try:
            full_img = capture_fullscreen()
            if not full_img:
                return

            selector = ColorSelector(self.root, full_img)
            self.root.wait_window(selector)

            sel_color = (
                selector.selected_color if hasattr(selector, "selected_color") else None
            )
            if not sel_color:
                return

            areas = self.config_mgr.get_areas()
            a1 = next((a for a in areas if a.id == 1), None)

            if not a1:
                from app.config_manager import AreaConfig

                a1 = AreaConfig(id=1, type="continuous", colors=[sel_color])
                areas.insert(0, a1)
            else:
                if sel_color not in a1.colors:
                    a1.colors.append(sel_color)

            self.config_mgr.set_areas(areas)
            self.refresh_color_canvas()
        except Exception as e:
            messagebox.showerror("Błąd", str(e))
        finally:
            self.root.deiconify()

    def add_white_subtitle_color(self):
        areas = self.config_mgr.get_areas()
        a1 = next((a for a in areas if a.id == 1), None)

        if a1:
            if "#ffffff" not in a1.colors:
                a1.colors.append("#ffffff")
                self.config_mgr.set_areas(areas)
                self.refresh_color_canvas()

    def delete_subtitle_color(self, idx):
        areas = self.config_mgr.get_areas()
        a1 = next((a for a in areas if a.id == 1), None)

        if a1:
            if idx < len(a1.colors):
                color_to_remove = a1.colors[idx]
                if messagebox.askyesno(
                    "Usuwanie koloru",
                    f"Czy usunąć kolor {color_to_remove} z Obszaru 1?",
                ):
                    del a1.colors[idx]
                    self.config_mgr.set_areas(areas)
                    self.refresh_color_canvas()

    # --- ZARZĄDZANIE OBSZARAMI ---

    def open_area_manager(self):
        path = self.var_preset_full_path.get()
        if not path:
            messagebox.showerror("Błąd", "Brak aktywnego profilu.")
            return

        preset = self.config_mgr.load_preset(path)

        # Load subtitles for testing inside manager
        txt_path = preset.text_file_path
        subs = []
        if txt_path and os.path.exists(txt_path):
            subs = self.config_mgr.load_text_lines(txt_path)

        # Open Manager: pass the LektorApp instance
        self.area_mgr_win = AreaManagerWindow(self.root, self, subs)

    def _get_screen_size(self):
        """
        Zwraca rozmiar ekranu bazując wyłącznie na `self.var_resolution`.
        Oczekiwany format: 'WIDTHxHEIGHT' (np. '2560x1440').
        W razie błędu zwraca fallback 4K.
        """
        try:
            res = self.var_resolution.get() if hasattr(self, "var_resolution") else None
            if isinstance(res, str) and "x" in res:
                parts = res.split("x")
                if len(parts) == 2:
                    w = int(parts[0])
                    h = int(parts[1])
                    return (w, h)
        except Exception:
            pass
        # Fallback 4K
        return (STANDARD_WIDTH, STANDARD_HEIGHT)

    def _save_areas_callback(self, new_areas):
        path = self.var_preset_full_path.get()
        if path:
            # new_areas is expected to be a list of dicts from AreaSelector or similar
            sw, sh = self._get_screen_size()
            areas_objs = []
            from app.config_manager import AreaConfig

            for na in new_areas:
                if isinstance(na, AreaConfig):
                    areas_objs.append(na)
                else:
                    areas_objs.append(
                        AreaConfig._from_dict(na if isinstance(na, dict) else {})
                    )

            old_disp = self.config_mgr.display_resolution
            try:
                self.config_mgr.display_resolution = (sw, sh)
                self.config_mgr.set_areas(areas_objs)
            finally:
                self.config_mgr.display_resolution = old_disp
            self._restart_hotkeys()
            self.refresh_color_canvas()
            # Restart reader
            if self.is_running:
                self.stop_reading()
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
                # config_mgr.get_areas() handles scaling 4K -> Display
                # AreaSelector expects screen coordinates
                sw, sh = self._get_screen_size()
                old_res = self.config_mgr.display_resolution
                try:
                    self.config_mgr.display_resolution = (sw, sh)
                    areas_to_show = self.config_mgr.get_areas()
                    # AreaSelector currently expects a list of dicts with 'rect' key
                    existing = [a._to_dict() for a in areas_to_show]
                finally:
                    self.config_mgr.display_resolution = old_res

            sel = AreaSelector(self.root, img, existing_regions=existing)

            if sel.geometry and path:
                sw, sh = self._get_screen_size()
                areas_objs = []
                old_res = self.config_mgr.display_resolution
                try:
                    self.config_mgr.display_resolution = (sw, sh)
                    areas_objs = self.config_mgr.get_areas()
                finally:
                    self.config_mgr.display_resolution = old_res

                a1_obj = next((a for a in areas_objs if a.id == 1), None)
                if a1_obj:
                    a1_obj.rect = sel.geometry
                else:
                    from app.config_manager import AreaConfig

                    a1_obj = AreaConfig(id=1, type="continuous", rect=sel.geometry)
                    areas_objs.insert(0, a1_obj)

                # Persist via ConfigManager
                self.config_mgr.set_areas_from_display(
                    areas_objs, src_resolution=(sw, sh)
                )

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
        preset = self.config_mgr.load_preset(path)

        txt_path = preset.text_file_path
        if not txt_path or not os.path.exists(txt_path):
            messagebox.showerror(
                "Błąd", "Nie znaleziono pliku napisów w ustawieniach presetu."
            )
            return

        subtitle_lines = self.config_mgr.load_text_lines(txt_path)
        if not subtitle_lines:
            messagebox.showerror("Błąd", "Plik napisów jest pusty.")
            return

        def on_wizard_finish(frames_data, mode, initial_color=None, advanced_settings=None):
            # frames_data: list of {'image': PIL, 'rect': (x,y,w,h) or None}
            valid_images = [f["image"] for f in frames_data]
            valid_rects = [f["rect"] for f in frames_data if f["rect"]]

            if not valid_rects:
                if not valid_images:
                    messagebox.showerror(
                        "Błąd", "Nie zdefiniowano żadnego obrazu do optymalizacji."
                    )
                    return
                fw, fh = valid_images[0].size
                valid_rects = [(0, 0, fw, fh)]

            fw, fh = valid_images[0].size
            fx, fy, real_w, real_h = calculate_merged_area(valid_rects, fw, fh)

            target_rect = (fx, fy, real_w, real_h)

            # Uruchomienie optymalizatora w wątku i pokazanie okna postępu
            prog = ProcessingWindow(self.root, "Trwa optymalizacja...")
            prog.set_status("Trwa dobieranie parametrów...\nTen proces może zająć kilka minut.\nProsimy nie zamykać tego okna.")

            thread_context = {
                "result": None,
                "error": None,
                "img_size": (fw, fh),
                "match_mode": mode,
            }

            def worker():
                try:
                    optimizer = SettingsOptimizer(self.config_mgr)

                    res = optimizer.optimize(
                        valid_images,
                        target_rect,
                        subtitle_lines,
                        mode,
                        initial_color=initial_color, **(advanced_settings or {}),
                        progress_callback=None, # Disabled for performance
                        stop_event=prog.stop_event,
                    )
                    thread_context["result"] = res
                except Exception as e:
                    import traceback

                    traceback.print_exc()
                    thread_context["error"] = str(e)
                finally:
                    # Signal completion via queue to trigger UI code on main thread
                    def final_callback():
                        try:
                            prog.destroy()
                        except:
                            pass
                        self.root.deiconify()
                        self._on_optimization_finished(thread_context, path)

                    prog.queue.put({"type": "complete", "callback": final_callback})

            t = threading.Thread(target=worker, daemon=True)
            t.start()

        # Otwórz wizard (ten callback kończy cały przepływ optymalizacji)
        OptimizationWizard(self.root, on_wizard_finish)

    # poprzednie funkcje _show_optimization_setup i _start_optimization_process zostały scalone

    def _on_optimization_finished(self, context, preset_path):
        if context["error"]:
            messagebox.showerror(
                "Błąd", f"Błąd podczas optymalizacji: {context['error']}"
            )
            return

        result = context["result"]
        if not result:
            messagebox.showerror("Błąd", "Brak wyników z optymalizatora.")
            return

        score = result.get("score", 0)

        if score < 50:
            display_score = min(score, 100)
            messagebox.showwarning(
                "Wynik",
                f"Nie znaleziono dobrych ustawień (Score: {display_score:.1f}%).\nSpróbuj zmienić obszar lub klatkę z gry. Najlepsze co mamy to: {display_score:.1f}%",
            )
            return

        best_settings = result.get("settings")  # This is a PresetConfig object
        optimized_area = result.get("optimized_area")
        img_size = context.get("img_size")

        # UI Callback definition
        def on_apply(dialog_res):
            if not dialog_res or not dialog_res.get("confirmed"):
                return

            self.config_mgr.backup_preset(preset_path)

            target_id = dialog_res.get("target_id")
            sw, sh = self._get_screen_size()

            # Get current areas as objects, scaled to screen
            old_res = self.config_mgr.display_resolution
            try:
                self.config_mgr.display_resolution = (sw, sh)
                current_areas = self.config_mgr.get_areas()
            finally:
                self.config_mgr.display_resolution = old_res

            # Rect calculation
            new_rect = None
            if optimized_area:
                ox, oy, ow, oh = optimized_area
                if img_size:
                    iw, ih = img_size
                    if iw > 0 and ih > 0:
                        sx = sw / iw
                        sy = sh / ih
                        ox, oy, ow, oh = ox * sx, oy * sy, ow * sx, oh * sy
                new_rect = {
                    "left": int(round(ox)),
                    "top": int(round(oy)),
                    "width": int(round(ow)),
                    "height": int(round(oh)),
                }

            # Find or create target area
            target_area = None
            if target_id is not None:
                target_area = next(
                    (a for a in current_areas if str(a.id) == str(target_id)), None
                )

            if not target_area and new_rect:
                from app.config_manager import AreaConfig
                import random

                # Generujemy unikalny string ID jak area_XXXXXXXX
                new_id = f"area_{random.randint(1000, 9999)}"
                target_area = AreaConfig(id=new_id, type="continuous")
                current_areas.append(target_area)

            if target_area:
                if new_rect:
                    target_area.rect = new_rect

                # Apply settings from best_settings (must be PresetConfig object)
                # Log values for debugging
                print(
                    f"APPLYING to Area #{target_area.id}: thick={best_settings.text_thickening}, brightness={best_settings.brightness_threshold}, mode={best_settings.subtitle_mode}"
                )
                target_area.text_thickening = int(best_settings.text_thickening)
                target_area.brightness_threshold = int(
                    best_settings.brightness_threshold
                )
                target_area.contrast = float(best_settings.contrast)
                target_area.color_tolerance = int(best_settings.color_tolerance)
                target_area.subtitle_mode = best_settings.subtitle_mode

                # Apply brightness mode if available
                if hasattr(best_settings, "brightness_mode"):
                    target_area.brightness_mode = best_settings.brightness_mode
                elif hasattr(best_settings, "text_color_mode"):
                    target_area.brightness_mode = best_settings.text_color_mode

                # Set optimized scale (currently always 1.0 from optimizer)
                if hasattr(best_settings, "ocr_scale_factor"):
                    target_area.ocr_scale_factor = float(best_settings.ocr_scale_factor)

                target_area.colors = list(best_settings.colors or [])

            # Save via ConfigManager
            old_res = self.config_mgr.display_resolution
            try:
                self.config_mgr.display_resolution = (sw, sh)
                # Use authoritative setter
                self.config_mgr.areas = current_areas
            finally:
                self.config_mgr.display_resolution = old_res

            self._restart_hotkeys()
            self.refresh_color_canvas()
            if self.is_running:
                self.stop_reading()
                self.root.after(200, self.start_reading)

            # Full sync reload
            self.on_preset_loaded()

        # Show result dialog
        OptimizationResultWindow(
            self.root,
            score,
            best_settings,
            optimized_area,
            self.config_mgr.get_areas(),
            on_apply,
        )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--preset", type=str)
    parser.add_argument("game_command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    cmd = args.game_command
    if cmd and cmd[0] == "--":
        cmd.pop(0)
    root = ctk.CTk(className="Lektor")
    LektorApp(root, args.preset, cmd)
    root.mainloop()


if __name__ == "__main__":
    main()
