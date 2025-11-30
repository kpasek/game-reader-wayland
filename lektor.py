# !/usr/bin/env python3
import sys
import os
import queue
import threading
import subprocess
import time
import argparse
import platform
from typing import Optional, Dict

try:
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox, scrolledtext, font
except ImportError:
    print("Błąd: Brak biblioteki tkinter.", file=sys.stderr)
    sys.exit(1)

# --- FIX WINDOWS 11 DPI SCALING ---
if platform.system() == "Windows":
    try:
        import ctypes

        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

# --- PYNPUT HOTKEYS ---
try:
    from pynput import keyboard

    HAS_PYNPUT = True
except ImportError:
    HAS_PYNPUT = False

from app.config_manager import ConfigManager
from app.reader import ReaderThread
from app.player import PlayerThread
from app.log import LogWindow
from app.settings import SettingsDialog
from app.area_selector import AreaSelector
from app.capture import capture_fullscreen

# Global events/queues
stop_event = threading.Event()
audio_queue = queue.Queue()
log_queue = queue.Queue()

APP_VERSION = "v0.8.3"
STANDARD_WIDTH = 3840
STANDARD_HEIGHT = 2160


class HelpWindow(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Pomoc i Instrukcja")
        self.geometry("600x550")
        # (Treść pomocy bez zmian...)
        default_font = font.nametofont("TkDefaultFont")
        base_font_family = default_font.actual()["family"]
        txt = scrolledtext.ScrolledText(self, wrap=tk.WORD, padx=15, pady=15, font=(base_font_family, 10))
        txt.pack(fill=tk.BOTH, expand=True)
        txt.tag_config('h1', font=(base_font_family, 12, 'bold'), spacing1=15, spacing3=5, foreground="#222222")
        txt.tag_config('bold', font=(base_font_family, 10, 'bold'))
        txt.tag_config('normal', spacing3=2)
        content = [
            ("JAK TO DZIAŁA?\n", 'h1'),
            ("Aplikacja Lektor działa w dwóch wątkach: jeden wykonuje zrzuty ekranu, drugi przetwarza tekst (OCR).\n",
             'normal'),
            ("OPTYMALIZACJA KRÓTKICH TEKSTÓW\n", 'h1'),
            ("Jeśli tekst jest krótki (poniżej progu), aplikacja spróbuje automatycznie znaleźć jego dokładne położenie, przyciąć obraz i odczytać ponownie z większą dokładnością.\n",
             'normal'),
            ("Wyrównanie tekstu:", "bold"),
            (" Pomaga określić, gdzie spodziewać się napisów (Lewo/Środek/Prawo).\n", 'normal'),
        ]
        for text, tag in content:
            txt.insert(tk.END, text, tag)
        txt.config(state=tk.DISABLED)


class LektorApp:
    def __init__(self, root: tk.Tk, autostart_preset: Optional[str], game_cmd: list):
        self.root = root
        self.root.title(f"Lektor {APP_VERSION}")
        self.root.geometry("750x850")  # Zwiększona wysokość dla nowych opcji

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
        self.var_ocr_scale = tk.DoubleVar(value=1.0)
        self.var_empty_threshold = tk.DoubleVar(value=0.15)
        self.var_capture_interval = tk.DoubleVar(value=0.5)
        self.var_auto_names = tk.BooleanVar(value=True)

        # Nowe opcje optymalizacji
        self.var_rerun_threshold = tk.IntVar(value=50)
        self.var_text_alignment = tk.StringVar(value="Center")
        self.var_save_logs = tk.BooleanVar(value=False)

        # Regex
        self.var_regex_mode = tk.StringVar()
        self.var_custom_regex = tk.StringVar()

        # Audio
        self.var_resolution = tk.StringVar()
        self.var_speed = tk.DoubleVar(value=1.0)
        self.var_volume = tk.DoubleVar(value=1.0)

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
        self.lbl_scale.config(text=f"{new_scale:.2f}")

    def on_manual_scale_change(self, event=None):
        val = round(self.var_ocr_scale.get(), 2)
        self.lbl_scale.config(text=f"{val:.2f}")
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
        hk_area3 = self.config_mgr.get('hotkey_area3', '<ctrl>+<f6>')
        if hasattr(self, 'hotkey_listener') and self.hotkey_listener:
            self.hotkey_listener.stop()
        hotkeys = {hk_start: self._on_hotkey_start_stop, hk_area3: self._on_hotkey_area3}
        try:
            self.hotkey_listener = keyboard.GlobalHotKeys(hotkeys)
            self.hotkey_listener.start()
        except:
            pass

    def _restart_hotkeys(self):
        if HAS_PYNPUT: self._start_hotkey_listener()

    def _on_hotkey_start_stop(self):
        self.root.after(0, self._toggle_start_stop_hotkey)

    def _on_hotkey_area3(self):
        self.root.after(0, self._trigger_area3_hotkey)

    def _toggle_start_stop_hotkey(self):
        if self.is_running:
            self.stop_reading()
        else:
            self.start_reading()

    def _trigger_area3_hotkey(self):
        if self.is_running and self.reader_thread: self.reader_thread.trigger_area_3()

    def _init_gui(self):
        menubar = tk.Menu(self.root)
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Ustawienia aplikacji", command=self.open_settings)
        file_menu.add_separator()
        file_menu.add_command(label="Wyjdź", command=self.on_close)
        menubar.add_cascade(label="Plik", menu=file_menu)

        preset_menu = tk.Menu(menubar, tearoff=0)
        preset_menu.add_command(label="Wybierz katalog...", command=self.browse_lector_folder)
        area_menu = tk.Menu(preset_menu, tearoff=0)
        for i in range(3):
            sub = tk.Menu(area_menu, tearoff=0)
            suf = " (CZASOWY)" if i == 2 else ""
            sub.add_command(label=f"Definiuj Obszar {i + 1}{suf}", command=lambda x=i: self.set_area(x))
            sub.add_command(label=f"Wyczyść Obszar {i + 1}", command=lambda x=i: self.clear_area(x))
            area_menu.add_cascade(label=f"Obszar {i + 1}{suf}", menu=sub)
        preset_menu.add_cascade(label="Obszary ekranu", menu=area_menu)
        preset_menu.add_separator()
        preset_menu.add_command(label="Zmień folder audio", command=lambda: self.change_path('audio_dir'))
        preset_menu.add_command(label="Zmień plik napisów", command=lambda: self.change_path('text_file_path'))
        preset_menu.add_command(label="Zmień plik imion", command=lambda: self.change_path('names_file_path'))
        menubar.add_cascade(label="Lektor", menu=preset_menu)

        tools_menu = tk.Menu(menubar, tearoff=0)
        tools_menu.add_command(label="Podgląd logów", command=self.show_logs)
        menubar.add_cascade(label="Narzędzia", menu=tools_menu)

        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="Instrukcja", command=self.show_help)
        menubar.add_cascade(label="Pomoc", menu=help_menu)
        self.root.config(menu=menubar)

        panel = ttk.Frame(self.root, padding=10)
        panel.pack(fill=tk.BOTH, expand=True)

        ttk.Label(panel, text="Aktywny lektor (Katalog):").pack(anchor=tk.W)
        self.cb_preset = ttk.Combobox(panel, textvariable=self.var_preset_display, state="readonly", width=60)
        self.cb_preset.pack(fill=tk.X, pady=5)
        self.cb_preset.bind("<<ComboboxSelected>>", self.on_preset_selected_from_combo)

        # --- CONFIG GROUP ---
        grp_cfg = ttk.LabelFrame(panel, text="Konfiguracja Lektora", padding=10)
        grp_cfg.pack(fill=tk.X, pady=10)

        # Row 1: Mode
        f_mode = ttk.Frame(grp_cfg)
        f_mode.pack(fill=tk.X, pady=5)
        ttk.Label(f_mode, text="Tryb dopasowania:").pack(side=tk.LEFT)
        cb_mode = ttk.Combobox(f_mode, textvariable=self.var_subtitle_mode, values=["Full Lines", "Partial Lines"],
                               state="readonly")
        cb_mode.pack(side=tk.LEFT, padx=(5, 20))
        cb_mode.bind("<<ComboboxSelected>>",
                     lambda e: self._save_preset_val("subtitle_mode", self.var_subtitle_mode.get()))

        # Row 2: Skala OCR (Slider)
        f_scale = ttk.Frame(grp_cfg)
        f_scale.pack(fill=tk.X, pady=5)
        ttk.Label(f_scale, text="Skala OCR:").pack(side=tk.LEFT)
        s_scale = ttk.Scale(f_scale, from_=0.1, to=1.0, variable=self.var_ocr_scale,
                            command=lambda v: self.lbl_scale.config(text=f"{float(v):.2f}"))
        s_scale.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        s_scale.bind("<ButtonRelease-1>", self.on_manual_scale_change)
        self.lbl_scale = ttk.Label(f_scale, text="1.00", width=5)
        self.lbl_scale.pack(side=tk.LEFT)

        # Row 3: Empty Threshold (Slider)
        f_empty = ttk.Frame(grp_cfg)
        f_empty.pack(fill=tk.X, pady=5)
        ttk.Label(f_empty, text="Czułość pustego:").pack(side=tk.LEFT)
        s_empty = ttk.Scale(f_empty, from_=0.0, to=0.6, variable=self.var_empty_threshold,
                            command=lambda v: self.lbl_empty.config(text=f"{float(v):.2f}"))
        s_empty.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        s_empty.bind("<ButtonRelease-1>",
                     lambda e: self._save_preset_val("empty_image_threshold", round(self.var_empty_threshold.get(), 2)))
        self.lbl_empty = ttk.Label(f_empty, text="0.15")
        self.lbl_empty.pack(side=tk.LEFT)

        # Row 4: Interval
        f_int = ttk.Frame(grp_cfg)
        f_int.pack(fill=tk.X, pady=5)
        ttk.Label(f_int, text="Skanowanie (s):").pack(side=tk.LEFT)
        s_int = ttk.Scale(f_int, from_=0.3, to=1.0, variable=self.var_capture_interval,
                          command=lambda v: self.lbl_int.config(text=f"{float(v):.2f}s"))
        s_int.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        s_int.bind("<ButtonRelease-1>",
                   lambda e: self._save_preset_val("capture_interval", round(self.var_capture_interval.get(), 2)))
        self.lbl_int = ttk.Label(f_int, text="0.50s")
        self.lbl_int.pack(side=tk.LEFT)

        # --- OPTYMALIZACJA ---
        grp_opt = ttk.LabelFrame(panel, text="Optymalizacja i Poprawki", padding=10)
        grp_opt.pack(fill=tk.X, pady=10)

        # Rerun Threshold
        f_rerun = ttk.Frame(grp_opt)
        f_rerun.pack(fill=tk.X, pady=5)
        ttk.Label(f_rerun, text="Popraw krótkie (< znaki):").pack(side=tk.LEFT)
        s_rerun = ttk.Scale(f_rerun, from_=0, to=150, variable=self.var_rerun_threshold,
                            command=lambda v: self.lbl_rerun.config(text=f"{int(float(v))}"))
        s_rerun.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        s_rerun.bind("<ButtonRelease-1>",
                     lambda e: self._save_preset_val("rerun_threshold", self.var_rerun_threshold.get()))
        self.lbl_rerun = ttk.Label(f_rerun, text="50", width=5)
        self.lbl_rerun.pack(side=tk.LEFT)

        # Alignment
        f_align = ttk.Frame(grp_opt)
        f_align.pack(fill=tk.X, pady=5)
        ttk.Label(f_align, text="Wyrównanie tekstu:").pack(side=tk.LEFT)
        cb_align = ttk.Combobox(f_align, textvariable=self.var_text_alignment, values=["Left", "Center", "Right"],
                                state="readonly", width=15)
        cb_align.pack(side=tk.LEFT, padx=5)
        cb_align.bind("<<ComboboxSelected>>",
                      lambda e: self._save_preset_val("text_alignment", self.var_text_alignment.get()))

        # --- FILTRY ---
        grp_reg = ttk.LabelFrame(panel, text="Filtracja tekstu", padding=5)
        grp_reg.pack(fill=tk.X, pady=10)
        f_r = ttk.Frame(grp_reg)
        f_r.pack(fill=tk.X)
        ttk.Label(f_r, text="Regex:").pack(side=tk.LEFT)
        self.cb_regex = ttk.Combobox(f_r, textvariable=self.var_regex_mode, values=list(self.regex_map.keys()),
                                     state="readonly", width=25)
        self.cb_regex.pack(side=tk.LEFT, padx=5)
        self.cb_regex.bind("<<ComboboxSelected>>", self.on_regex_changed)
        self.ent_regex = ttk.Entry(f_r, textvariable=self.var_custom_regex, state="disabled")
        self.ent_regex.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        self.ent_regex.bind("<FocusOut>",
                            lambda e: self.config_mgr.update_setting('last_custom_regex', self.var_custom_regex.get()))
        ttk.Checkbutton(grp_reg, text="Usuwaj imiona (Smart)", variable=self.var_auto_names,
                        command=lambda: self._save_preset_val("auto_remove_names", self.var_auto_names.get())).pack(
            anchor=tk.W)

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
        ttk.Button(f_res, text="Auto Detect", command=self.auto_detect_resolution).pack(side=tk.LEFT, padx=5)

        # --- AUDIO ---
        grp_aud = ttk.LabelFrame(panel, text="Kontrola Audio", padding=10)
        grp_aud.pack(fill=tk.X, pady=10)

        ttk.Label(grp_aud, text="Prędkość:").grid(row=0, column=0)
        s_spd = ttk.Scale(grp_aud, from_=0.9, to=1.3, variable=self.var_speed,
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
        grp_aud.columnconfigure(1, weight=1)

        # --- STEROWANIE ---
        hk_start = self.config_mgr.get('hotkey_start_stop', 'Ctrl+F5')
        frm_btn = ttk.Frame(panel)
        frm_btn.pack(side=tk.BOTTOM, fill=tk.X, pady=10)

        # Logi Checkbox
        ttk.Checkbutton(frm_btn, text="Zapisuj logi do pliku", variable=self.var_save_logs,
                        command=lambda: self._save_preset_val("save_logs", self.var_save_logs.get())).pack(side=tk.TOP,
                                                                                                           anchor=tk.W,
                                                                                                           pady=(0, 5))

        self.btn_start = ttk.Button(frm_btn, text=f"START ({hk_start})", command=self.start_reading)
        self.btn_start.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        self.btn_stop = ttk.Button(frm_btn, text=f"STOP ({hk_start})", command=self.stop_reading, state="disabled")
        self.btn_stop.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)

        ttk.Label(self.root, text=f"Wersja: {APP_VERSION}", font=("Arial", 8)).pack(side=tk.BOTTOM, anchor=tk.E, padx=5)

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

        self.var_speed.set(data.get("audio_speed", 1.0))
        self.lbl_spd.config(text=f"{self.var_speed.get():.2f}x")

        self.var_volume.set(data.get("audio_volume", 1.0))
        self.lbl_vol.config(text=f"{self.var_volume.get():.2f}")

        self.var_auto_names.set(data.get("auto_remove_names", True))
        self.var_subtitle_mode.set(data.get("subtitle_mode", "Full Lines"))

        self.var_ocr_scale.set(data.get("ocr_scale_factor", 1.0))
        self.lbl_scale.config(text=f"{self.var_ocr_scale.get():.2f}")

        self.var_empty_threshold.set(data.get("empty_image_threshold", 0.15))
        self.lbl_empty.config(text=f"{self.var_empty_threshold.get():.2f}")

        self.var_capture_interval.set(data.get("capture_interval", 0.5))
        self.lbl_int.config(text=f"{self.var_capture_interval.get():.2f}s")

        # Nowe opcje
        self.var_rerun_threshold.set(data.get("rerun_threshold", 50))
        self.lbl_rerun.config(text=f"{self.var_rerun_threshold.get()}")
        self.var_text_alignment.set(data.get("text_alignment", "Center"))
        self.var_save_logs.set(data.get("save_logs", False))

        if "regex_mode_name" in data:
            self.var_regex_mode.set(data["regex_mode_name"])
            if data["regex_mode_name"] == "Własny (Regex)": self.var_custom_regex.set(data.get("regex_pattern", ""))
            self.on_regex_changed()

    def on_regex_changed(self, event=None):
        mode = self.var_regex_mode.get()
        self.ent_regex.config(state="normal" if mode == "Własny (Regex)" else "disabled")
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
            messagebox.showinfo("Sukces", "Zaktualizowano ścieżkę.")

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
        SettingsDialog(self.root, self.config_mgr.settings)
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
        self.reader_thread = ReaderThread(path, pattern, self.config_mgr.settings, stop_event, audio_queue,
                                          target_resolution=target_res, log_queue=log_queue,
                                          auto_remove_names=self.var_auto_names.get())
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

    def on_close(self):
        self.is_running = False
        if self.reader_thread and self.reader_thread.is_alive(): self.stop_reading()
        if self.game_process: self.game_process.terminate()
        if hasattr(self, 'hotkey_listener') and self.hotkey_listener: self.hotkey_listener.stop()
        self.root.destroy()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--preset', type=str)
    parser.add_argument('game_command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    cmd = args.game_command
    if cmd and cmd[0] == '--': cmd.pop(0)
    root = tk.Tk()
    LektorApp(root, args.preset, cmd)
    root.mainloop()


if __name__ == "__main__":
    main()