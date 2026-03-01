import sys
from typing import Any, Dict, TYPE_CHECKING

if TYPE_CHECKING:
    from lektor import LektorApp

try:
    import tkinter as tk
except ImportError:
    sys.exit(1)

from app.ctk_widgets import CTkToplevel, make_frame, make_label, make_button, make_combobox, make_labelframe, make_notebook, make_notebook_tab, make_scale, make_entry, make_checkbutton, make_scrollbar


class SettingsDialog(CTkToplevel):
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
        self.var_brightness_threshold = tk.IntVar(value=app_instance.config_mgr.brightness_threshold)
        self.var_hk_start = tk.StringVar(value=settings.get('hotkey_start_stop', '<f10>'))
        self.var_hk_area3 = tk.StringVar(value=settings.get('hotkey_area3', '<f3>'))
        self.var_capture_backend = tk.StringVar(value=settings.get('capture_backend', 'Auto'))

        self._initialize_app_variables()

        self._build_ui()
        self.geometry("700x900")
        self.grab_set()

    def _initialize_app_variables(self):
        """Inicjalizuje wymagane zmienne aplikacji (`tk.Variable`).
        
        Ta metoda aktualizuje istniejące zmienne UI na obiekcie `self.app` 
        wartościami pobranymi z `ConfigManager`.
        """
        cm = self.app.config_mgr

        # Aktualizujemy istniejące zmienne zamiast tworzyć nowe, 
        # aby nie zerwać powiązań (bindings/traces) w głównym oknie.
        self.app.var_capture_interval.set(float(cm.capture_interval))
        self.app.var_audio_speed.set(float(cm.audio_speed_inc))

        self.app.var_match_score_short.set(int(cm.match_score_short))
        self.app.var_match_score_long.set(int(cm.match_score_long))
        self.app.var_match_len_diff.set(float(cm.match_len_diff_ratio))
        self.app.var_partial_min_len.set(int(cm.partial_mode_min_len))
        self.app.var_similarity.set(int(cm.similarity))
        self.app.var_show_debug.set(bool(cm.show_debug))
        
        self.app.var_regex_mode.set(str(cm.last_regex_mode))
        self.app.var_custom_regex.set(str(cm.last_custom_regex))
        
        self.app.var_auto_names.set(bool(cm.auto_remove_names))
        self.app.var_save_logs.set(bool(cm.save_logs))

        return None


    def _build_ui(self):
        tabs = make_notebook(self)
        tabs.pack(fill=tk.BOTH, expand=True, padx=15, pady=15)
        
        tab_main = make_notebook_tab(tabs, "Ustawienia")
        tab_hk = make_notebook_tab(tabs, "Skróty klawiszowe")
        self._fill_main_tab(tab_main)
        self._fill_hk_tab(tab_hk)

        btn_f = make_frame(self)
        btn_f.pack(side=tk.BOTTOM, fill=tk.X, pady=(15, 10), padx=10)
        make_button(btn_f, text="Zapisz", command=self.save, fg_color="#27ae60", hover_color="#1e8449", text_color="#ffffff").pack(side=tk.RIGHT, padx=(5, 0))
        make_button(btn_f, text="Anuluj", command=self.destroy, fg_color="#7f8c8d", hover_color="#6c7a7b", text_color="#ffffff").pack(side=tk.RIGHT, padx=5)

    def _setup_scroll_frame(self, parent, fill_function):
        canvas = tk.Canvas(parent, highlightthickness=0)
        scrollbar = make_scrollbar(parent, orient="vertical", command=canvas.yview)
        scrollable_frame = make_frame(canvas)

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
        grp_img = make_labelframe(pnl, text="Wideo i Obraz", padding=15)
        grp_img.pack(fill=tk.X, pady=(0, 15), padx=10)

        f_backend = make_frame(grp_img)
        f_backend.pack(fill=tk.X, pady=5)
        make_label(f_backend, text="Backend przechwytywania:").pack(side=tk.LEFT)
        backend_choices = ["Auto", "pipewire_wayland", "kde_spectacle", "mss", "pyscreenshot"]
        cb_backend = make_combobox(f_backend, textvariable=self.var_capture_backend, values=backend_choices, state="readonly", width=18)
        cb_backend.pack(side=tk.LEFT, padx=5)
        make_label(f_backend, text="(Wymaga restartu po zmianie)", font=("Arial", 8, "italic"), text_color="gray").pack(side=tk.LEFT, padx=5)

        # 2. Parametry OCR (bez skali)
        grp_ocr = make_labelframe(pnl, text="Parametry OCR", padding=15)
        grp_ocr.pack(fill=tk.X, pady=(0, 15), padx=10)

        self._add_slider(grp_ocr, "Częstotliwość skanowania (s):", self.app.var_capture_interval, 0.3, 1.0, "capture_interval", fmt="{:.2f}s")
        self._add_slider(grp_ocr, "Minimalne podobieństwo zrzutów (%):", self.app.var_similarity, 1, 15,
                         "similarity", fmt="{:.0f}%", resolution=1)

        make_checkbutton(grp_ocr, text="DEBUG: Pokaż obszar wykrytych napisów", variable=self.app.var_show_debug,
                        command=lambda: setattr(self.app.config_mgr, "show_debug", self.app.var_show_debug.get())).pack(
            anchor=tk.W, pady=2)

        # 3. Optymalizacja
        grp_opt = make_labelframe(pnl, text="Optymalizacja Tekstu", padding=15)
        grp_opt.pack(fill=tk.X, pady=(0, 15), padx=10)

        self._add_slider(grp_opt, "Minimalna długość dla partial (zn):", self.app.var_partial_min_len, 5, 50,
                         "partial_mode_min_len", fmt="{:.0f}", resolution=1)

        self._add_slider(grp_opt, "Max różnica długości (ratio):", self.app.var_match_len_diff, 0.0, 0.5,
                         "match_len_diff_ratio", fmt="{:.2f}", resolution=0.05)

        self._add_slider(grp_opt, "Min score (krótkie <=6 zn):", self.app.var_match_score_short, 50, 100,
                         "match_score_short", fmt="{:.0f}", resolution=1)
        self._add_slider(grp_opt, "Min score (długie):", self.app.var_match_score_long, 50, 100,
                         "match_score_long", fmt="{:.0f}", resolution=1)

        # 4. Audio, Filtracja i Logi (z dawnego _fill_dialogs_tab)
        grp_audio = make_labelframe(pnl, text="Odtwarzanie Audio (Kolejkowanie)", padding=15)
        grp_audio.pack(fill=tk.X, pady=(0, 15), padx=10)
        self._add_slider(grp_audio, "Przyspieszenie (Kolejka > 0):", self.app.var_audio_speed, 1.0, 1.7,
                         "audio_speed_inc", fmt="{:.2f}")

        grp_flt = make_labelframe(pnl, text="Filtracja i Inne", padding=10)
        grp_flt.pack(fill=tk.X, pady=10, padx=10)
        f_r = make_frame(grp_flt)
        f_r.pack(fill=tk.X)
        make_label(f_r, text="Regex:").pack(side=tk.LEFT)
        cb_regex = make_combobox(f_r, textvariable=self.app.var_regex_mode, values=list(self.app.regex_map.keys()),
                    state="readonly", width=25)
        cb_regex.pack(side=tk.LEFT, padx=5)
        cb_regex.bind("<<ComboboxSelected>>", self.app.on_regex_changed)
        ent_regex = make_entry(f_r, textvariable=self.app.var_custom_regex)
        ent_regex.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        mode = self.app.var_regex_mode.get()
        ent_regex.configure(state="normal" if mode == "Własny (Regex)" else "disabled")
        self.app.ent_regex = ent_regex  # Hack referencyjny
        def _save_last_custom_regex(e=None):
            self.app.config_mgr.settings['last_custom_regex'] = self.app.var_custom_regex.get()
            self.app.config_mgr.save_app_config()

        ent_regex.bind("<FocusOut>", _save_last_custom_regex)
        make_checkbutton(grp_flt, text="Usuwaj imiona (Smart)", variable=self.app.var_auto_names,
                        command=lambda: setattr(self.app.config_mgr, "auto_remove_names",
                                               self.app.var_auto_names.get())).pack(anchor=tk.W,
                                                                                    pady=2)
        make_checkbutton(grp_flt, text="Zapisuj logi do pliku", variable=self.app.var_save_logs,
                        command=lambda: setattr(self.app.config_mgr, "save_logs",
                                               self.app.var_save_logs.get())).pack(
            anchor=tk.W, pady=2)

    def _fill_dialogs_tab(self, pnl):
        # 1. Konfiguracja Dopasowania (Matcher) - REMOVED (Per-area now)
        # 2. Audio Speedup
        grp_audio = make_labelframe(pnl, text="Odtwarzanie Audio (Kolejkowanie)", padding=10)
        grp_audio.pack(fill=tk.X, pady=10, padx=10)

        self._add_slider(grp_audio, "Przyspieszenie (Kolejka > 0):", self.app.var_audio_speed, 1.0, 1.7,
                         "audio_speed_inc", fmt="{:.2f}")

        # 3. Filtracja i Logi
        grp_flt = make_labelframe(pnl, text="Filtracja i Inne", padding=10)
        grp_flt.pack(fill=tk.X, pady=10, padx=10)

        f_r = make_frame(grp_flt)
        f_r.pack(fill=tk.X)
        make_label(f_r, text="Regex:").pack(side=tk.LEFT)
        cb_regex = make_combobox(f_r, textvariable=self.app.var_regex_mode, values=list(self.app.regex_map.keys()),
                    state="readonly", width=25)
        cb_regex.pack(side=tk.LEFT, padx=5)
        cb_regex.bind("<<ComboboxSelected>>", self.app.on_regex_changed)

        ent_regex = make_entry(f_r, textvariable=self.app.var_custom_regex)
        ent_regex.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        mode = self.app.var_regex_mode.get()
        ent_regex.configure(state="normal" if mode == "Własny (Regex)" else "disabled")
        self.app.ent_regex = ent_regex

        make_checkbutton(grp_flt, text="Usuwaj imiona (Smart)", variable=self.app.var_auto_names,
                        command=lambda: setattr(self.app.config_mgr, "auto_remove_names",
                                               self.app.var_auto_names.get())).pack(anchor=tk.W,
                                                                                    pady=2)
        make_checkbutton(grp_flt, text="Zapisuj logi do pliku", variable=self.app.var_save_logs,
                        command=lambda: setattr(self.app.config_mgr, "save_logs",
                                               self.app.var_save_logs.get())).pack(
            anchor=tk.W, pady=2)

    def _fill_hk_tab(self, pnl):
        lf_hk = make_labelframe(pnl, text="Definicja skrótów (format pynput)", padding=15)
        lf_hk.pack(fill=tk.X, pady=(0, 15), padx=10)
        make_label(lf_hk, text="Start / Stop:").pack(anchor=tk.W)
        make_entry(lf_hk, textvariable=self.var_hk_start).pack(fill=tk.X, pady=(0, 10))
        make_label(lf_hk, text="Przykłady: <ctrl>+<f10>, <alt>+x, <f9>", text_color="gray").pack(anchor=tk.W)

    def _add_slider(self, parent, label, variable, from_, to, config_key, fmt="{:.2f}", resolution=None):
        f = make_frame(parent)
        f.pack(fill=tk.X, pady=5)
        make_label(f, text=label).pack(side=tk.LEFT)

        val_lbl = make_label(f, text=fmt.format(variable.get()), width=6)

        # Jeśli resolution nie podane, zgadnij na podstawie typu zmiennej
        if resolution is None:
            resolution = 1 if isinstance(variable, tk.IntVar) else 0.1

        scale = make_scale(f, from_=from_, to=to, variable=variable,
              command=lambda v: val_lbl.configure(text=fmt.format(float(v))))

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
            val_lbl.configure(text=fmt.format(val))
            setattr(self.app.config_mgr, config_key, val)

        scale.bind("<ButtonRelease-1>", on_release)

        scale.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        val_lbl.pack(side=tk.LEFT)

    def save(self):
        # Zapisz ustawienia globalne
        self.settings['hotkey_start_stop'] = self.var_hk_start.get()
        self.settings['hotkey_area3'] = self.var_hk_area3.get()
        self.settings['capture_backend'] = self.var_capture_backend.get()
        self.app.config_mgr.save_app_config()
        self.destroy()