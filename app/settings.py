import sys
from typing import Any, Dict, TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from lektor import LektorApp

try:
    import tkinter as tk
    from tkinter import ttk
except ImportError:
    sys.exit(1)


class SettingsDialog(tk.Toplevel):
    """
    Okno dialogowe do globalnych ustawień aplikacji oraz zaawansowanych ustawień presetu.
    """

    def __init__(self, parent: tk.Misc, settings: Dict[str, Any], app_instance: 'LektorApp'):
        super().__init__(parent)
        self.transient(parent)
        self.title("Ustawienia aplikacji")
        self.settings: Dict[str, Any] = settings
        self.app: 'LektorApp' = app_instance

        # Zmienne UI (Globalne)
        self.var_brightness_threshold = tk.IntVar(value=settings.get('brightness_threshold', 150))
        self.var_hk_start = tk.StringVar(value=settings.get('hotkey_start_stop', '<f2>'))
        self.var_hk_area3 = tk.StringVar(value=settings.get('hotkey_area3', '<f3>'))

        self._ensure_app_vars()

        self._build_ui()
        self.geometry("700x900")
        self.grab_set()

    def _ensure_app_vars(self):
        """Pomocnicza funkcja do upewnienia się, że zmienne istnieją w obiekcie aplikacji."""
        # Nowe parametry
        if not hasattr(self.app, 'var_ocr_density'): self.app.var_ocr_density = tk.DoubleVar()
        if not hasattr(self.app, 'var_audio_speed'): self.app.var_audio_speed = tk.DoubleVar()
        if not hasattr(self.app, 'var_match_score_short'): self.app.var_match_score_short = tk.IntVar()
        if not hasattr(self.app, 'var_match_score_long'): self.app.var_match_score_long = tk.IntVar()
        if not hasattr(self.app, 'var_match_len_diff'): self.app.var_match_len_diff = tk.DoubleVar()
        if not hasattr(self.app, 'var_partial_min_len'): self.app.var_partial_min_len = tk.IntVar()
        if not hasattr(self.app, 'var_similarity'): self.app.var_similarity = tk.IntVar()

        # Inicjalizuj wartości z `ConfigManager` (preferuj properties);
        # fallback na `self.settings` gdy `config_mgr` nie jest dostępny.
        if hasattr(self.app, 'config_mgr') and self.app.config_mgr:
            cm = self.app.config_mgr
            self.app.var_match_score_short.set(int(cm.match_score_short))
            self.app.var_match_score_long.set(int(cm.match_score_long))
            self.app.var_match_len_diff.set(float(cm.match_len_diff_ratio))
            self.app.var_partial_min_len.set(int(cm.partial_mode_min_len))
            # similarity jest zapisywane jako liczba (np. 5.0) — traktujemy jako int procentowy
            self.app.var_similarity.set(int(cm.similarity))
        else:
            self.app.var_match_score_short.set(int(self.settings.get('match_score_short', 90)))
            self.app.var_match_score_long.set(int(self.settings.get('match_score_long', 75)))
            self.app.var_match_len_diff.set(float(self.settings.get('match_len_diff_ratio', 0.25)))
            self.app.var_partial_min_len.set(int(self.settings.get('partial_mode_min_len', 25)))
            self.app.var_similarity.set(int(self.settings.get('similarity', 5)))


    def _build_ui(self):
        tabs = ttk.Notebook(self)
        tabs.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        tab_main = ttk.Frame(tabs)
        tab_hk = ttk.Frame(tabs)

        tabs.add(tab_main, text="Ustawienia")
        tabs.add(tab_hk, text="Skróty klawiszowe")
        self._fill_main_tab(tab_main)
        self._fill_hk_tab(tab_hk)

        btn_f = ttk.Frame(self)
        btn_f.pack(side=tk.BOTTOM, fill=tk.X, pady=10, padx=10)
        ttk.Button(btn_f, text="Zapisz", command=self.save).pack(side=tk.RIGHT)
        ttk.Button(btn_f, text="Anuluj", command=self.destroy).pack(side=tk.RIGHT, padx=5)

    def _setup_scroll_frame(self, parent, fill_function):
        canvas = tk.Canvas(parent, highlightthickness=0)
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)

        scrollable_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        # Binduj tylko gdy mysz jest nad płótnem
        canvas.bind("<Enter>", lambda e: canvas.bind_all("<MouseWheel>", _on_mousewheel))
        canvas.bind("<Leave>", lambda e: canvas.unbind_all("<MouseWheel>"))

        fill_function(scrollable_frame)


    def _fill_main_tab(self, pnl):
        # 1. Konfiguracja Obrazu (Filtry)
        grp_img = ttk.LabelFrame(pnl, text="Filtry Obrazu", padding=10)
        grp_img.pack(fill=tk.X, pady=10, padx=10)

        # 2. Parametry OCR (bez skali)
        grp_ocr = ttk.LabelFrame(pnl, text="Parametry OCR", padding=10)
        grp_ocr.pack(fill=tk.X, pady=10, padx=10)

        self._add_slider(grp_ocr, "Częstotliwość skanowania (s):", self.app.var_capture_interval, 0.3, 1.0, "capture_interval", fmt="{:.2f}s")
        self._add_slider(grp_ocr, "Minimalne podobieństwo zrzutów (%):", self.app.var_similarity, 1, 15,
                         "similarity", fmt="{:.0f}%", resolution=1)

        ttk.Checkbutton(grp_ocr, text="DEBUG: Pokaż obszar wykrytych napisów", variable=self.app.var_show_debug,
                        command=lambda: self.app._save_preset_val("show_debug", self.app.var_show_debug.get())).pack(
            anchor=tk.W, pady=2)

        # 3. Optymalizacja
        grp_opt = ttk.LabelFrame(pnl, text="Optymalizacja Tekstu", padding=10)
        grp_opt.pack(fill=tk.X, pady=10, padx=10)

        self._add_slider(grp_opt, "Minimalna długość dla partial (zn):", self.app.var_partial_min_len, 5, 50,
                         "partial_mode_min_len", fmt="{:.0f}", resolution=1)

        self._add_slider(grp_opt, "Max różnica długości (ratio):", self.app.var_match_len_diff, 0.0, 0.5,
                         "match_len_diff_ratio", fmt="{:.2f}", resolution=0.05)

        self._add_slider(grp_opt, "Min score (krótkie <=6 zn):", self.app.var_match_score_short, 50, 100,
                         "match_score_short", fmt="{:.0f}", resolution=1)
        self._add_slider(grp_opt, "Min score (długie):", self.app.var_match_score_long, 50, 100,
                         "match_score_long", fmt="{:.0f}", resolution=1)

        f_color = ttk.Frame(grp_opt)
        f_color.pack(fill=tk.X, pady=5)
        ttk.Label(f_color, text="Kolor napisów:").pack(side=tk.LEFT)
        cb_color = ttk.Combobox(f_color, textvariable=self.app.var_text_color, values=["Light", "Dark", "Mixed"],
                                state="readonly", width=15)
        cb_color.pack(side=tk.LEFT, padx=5)
        cb_color.bind("<<ComboboxSelected>>",
                      lambda e: self.app._save_preset_val("text_color_mode", self.app.var_text_color.get()))
        ttk.Label(f_color, text="(Light = Jasne napisy)", font=("Arial", 8, "italic"), foreground="gray").pack(
            side=tk.LEFT, padx=5)

        # 4. Audio, Filtracja i Logi (z dawnego _fill_dialogs_tab)
        grp_audio = ttk.LabelFrame(pnl, text="Odtwarzanie Audio (Kolejkowanie)", padding=10)
        grp_audio.pack(fill=tk.X, pady=10, padx=10)
        self._add_slider(grp_audio, "Przyspieszenie (Kolejka > 0):", self.app.var_audio_speed, 1.0, 1.7,
                         "audio_speed_inc", fmt="{:.2f}")

        grp_flt = ttk.LabelFrame(pnl, text="Filtracja i Inne", padding=10)
        grp_flt.pack(fill=tk.X, pady=10, padx=10)
        f_r = ttk.Frame(grp_flt)
        f_r.pack(fill=tk.X)
        ttk.Label(f_r, text="Regex:").pack(side=tk.LEFT)
        cb_regex = ttk.Combobox(f_r, textvariable=self.app.var_regex_mode, values=list(self.app.regex_map.keys()),
                                state="readonly", width=25)
        cb_regex.pack(side=tk.LEFT, padx=5)
        cb_regex.bind("<<ComboboxSelected>>", self.app.on_regex_changed)
        ent_regex = ttk.Entry(f_r, textvariable=self.app.var_custom_regex)
        ent_regex.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        mode = self.app.var_regex_mode.get()
        ent_regex.config(state="normal" if mode == "Własny (Regex)" else "disabled")
        self.app.ent_regex = ent_regex  # Hack referencyjny
        ent_regex.bind("<FocusOut>", lambda e: self.app.config_mgr.update_setting('last_custom_regex',
                                                                                  self.app.var_custom_regex.get()))
        ttk.Checkbutton(grp_flt, text="Usuwaj imiona (Smart)", variable=self.app.var_auto_names,
                        command=lambda: self.app._save_preset_val("auto_remove_names",
                                                                  self.app.var_auto_names.get())).pack(anchor=tk.W,
                                                                                                       pady=2)
        ttk.Checkbutton(grp_flt, text="Zapisuj logi do pliku", variable=self.app.var_save_logs,
                        command=lambda: self.app._save_preset_val("save_logs", self.app.var_save_logs.get())).pack(
            anchor=tk.W, pady=2)

    def _fill_dialogs_tab(self, pnl):
        # 1. Konfiguracja Dopasowania (Matcher) - REMOVED (Per-area now)
        # 2. Audio Speedup
        grp_audio = ttk.LabelFrame(pnl, text="Odtwarzanie Audio (Kolejkowanie)", padding=10)
        grp_audio.pack(fill=tk.X, pady=10, padx=10)

        self._add_slider(grp_audio, "Przyspieszenie (Kolejka > 0):", self.app.var_audio_speed, 1.0, 1.7,
                         "audio_speed_inc", fmt="{:.2f}")

        # 3. Filtracja i Logi
        grp_flt = ttk.LabelFrame(pnl, text="Filtracja i Inne", padding=10)
        grp_flt.pack(fill=tk.X, pady=10, padx=10)

        f_r = ttk.Frame(grp_flt)
        f_r.pack(fill=tk.X)
        ttk.Label(f_r, text="Regex:").pack(side=tk.LEFT)
        cb_regex = ttk.Combobox(f_r, textvariable=self.app.var_regex_mode, values=list(self.app.regex_map.keys()),
                                state="readonly", width=25)
        cb_regex.pack(side=tk.LEFT, padx=5)
        cb_regex.bind("<<ComboboxSelected>>", self.app.on_regex_changed)

        ent_regex = ttk.Entry(f_r, textvariable=self.app.var_custom_regex)
        ent_regex.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        mode = self.app.var_regex_mode.get()
        ent_regex.config(state="normal" if mode == "Własny (Regex)" else "disabled")
        self.app.ent_regex = ent_regex  # Hack referencyjny
        ent_regex.bind("<FocusOut>", lambda e: self.app.config_mgr.update_setting('last_custom_regex',
                                                                                  self.app.var_custom_regex.get()))

        ttk.Checkbutton(grp_flt, text="Usuwaj imiona (Smart)", variable=self.app.var_auto_names,
                        command=lambda: self.app._save_preset_val("auto_remove_names",
                                                                  self.app.var_auto_names.get())).pack(anchor=tk.W,
                                                                                                       pady=2)
        ttk.Checkbutton(grp_flt, text="Zapisuj logi do pliku", variable=self.app.var_save_logs,
                        command=lambda: self.app._save_preset_val("save_logs", self.app.var_save_logs.get())).pack(
            anchor=tk.W, pady=2)

    def _fill_hk_tab(self, pnl):
        lf_hk = ttk.LabelFrame(pnl, text="Definicja skrótów (format pynput)", padding=10)
        lf_hk.pack(fill=tk.X, pady=10, padx=10)
        ttk.Label(lf_hk, text="Start / Stop:").pack(anchor=tk.W)
        ttk.Entry(lf_hk, textvariable=self.var_hk_start).pack(fill=tk.X, pady=(0, 10))
        ttk.Label(lf_hk, text="Przykłady: <ctrl>+<f5>, <alt>+x, <f9>", foreground="gray").pack(anchor=tk.W)

    def _add_slider(self, parent, label, variable, from_, to, config_key, fmt="{:.2f}", resolution=None):
        f = ttk.Frame(parent)
        f.pack(fill=tk.X, pady=5)
        ttk.Label(f, text=label).pack(side=tk.LEFT)

        val_lbl = ttk.Label(f, text=fmt.format(variable.get()), width=6)

        # Jeśli resolution nie podane, zgadnij na podstawie typu zmiennej
        if resolution is None:
            resolution = 1 if isinstance(variable, tk.IntVar) else 0.1

        scale = ttk.Scale(f, from_=from_, to=to, variable=variable,
                          command=lambda v: val_lbl.config(text=fmt.format(float(v))))

        def on_release(event):
            val = variable.get()
            if isinstance(variable, tk.IntVar):
                val = int(round(val))
            else:
                val = float(val)
                # Drobne zaokrąglenie floatów
                if resolution >= 0.01:
                    val = round(val, 3)

            variable.set(val)
            val_lbl.config(text=fmt.format(val))
            self.app._save_preset_val(config_key, val)

        scale.bind("<ButtonRelease-1>", on_release)

        scale.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        val_lbl.pack(side=tk.LEFT)

    def save(self):
        # Zapisz ustawienia globalne
        self.settings['hotkey_start_stop'] = self.var_hk_start.get()
        self.settings['hotkey_area3'] = self.var_hk_area3.get()
        self.destroy()