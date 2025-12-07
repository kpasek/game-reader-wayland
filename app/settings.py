import sys
from typing import Any, Dict

try:
    import tkinter as tk
    from tkinter import ttk
except ImportError:
    sys.exit(1)


class SettingsDialog(tk.Toplevel):
    """
    Okno dialogowe do globalnych ustawień aplikacji oraz zaawansowanych ustawień presetu.
    """

    def __init__(self, parent, settings: Dict[str, Any], app_instance):
        super().__init__(parent)
        self.transient(parent)
        self.title("Ustawienia aplikacji")
        self.settings = settings
        self.app = app_instance  # Dostęp do zmiennych i metod LektorApp

        # Zmienne UI (Globalne)
        self.var_gray = tk.BooleanVar(value=settings.get('ocr_grayscale', False))
        self.var_contrast = tk.BooleanVar(value=settings.get('ocr_contrast', False))
        self.var_hk_start = tk.StringVar(value=settings.get('hotkey_start_stop', '<ctrl>+<f5>'))
        self.var_hk_area3 = tk.StringVar(value=settings.get('hotkey_area3', '<ctrl>+<f6>'))

        self._build_ui()
        self.geometry("550x700")  # Zwiększone okno, by pomieścić opcje
        self.grab_set()

    def _build_ui(self):
        tabs = ttk.Notebook(self)
        tabs.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # --- Karta 1: Zaawansowane (DOMYŚLNA) ---
        tab_adv = ttk.Frame(tabs)
        tabs.add(tab_adv, text="Zaawansowane")

        # Kontener ze scrollbarem dla zaawansowanych (gdyby okno było za małe)
        canvas = tk.Canvas(tab_adv, highlightthickness=0)
        scrollbar = ttk.Scrollbar(tab_adv, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # Myszka scroll
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        canvas.bind_all("<MouseWheel>", _on_mousewheel)
        self.bind("<Destroy>", lambda e: canvas.unbind_all("<MouseWheel>"))

        # === ZAWARTOŚĆ ZAAWANSOWANE ===
        pnl = scrollable_frame

        # --- Konfiguracja Lektora ---
        grp_cfg = ttk.LabelFrame(pnl, text="Konfiguracja Lektora", padding=10)
        grp_cfg.pack(fill=tk.X, pady=10, padx=10)

        # Mode
        f_mode = ttk.Frame(grp_cfg)
        f_mode.pack(fill=tk.X, pady=5)
        ttk.Label(f_mode, text="Tryb dopasowania:").pack(side=tk.LEFT)
        cb_mode = ttk.Combobox(f_mode, textvariable=self.app.var_subtitle_mode, values=["Full Lines", "Partial Lines"],
                               state="readonly")
        cb_mode.pack(side=tk.LEFT, padx=(5, 20))
        cb_mode.bind("<<ComboboxSelected>>",
                     lambda e: self.app._save_preset_val("subtitle_mode", self.app.var_subtitle_mode.get()))

        # Skala OCR
        f_scale = ttk.Frame(grp_cfg)
        f_scale.pack(fill=tk.X, pady=5)
        ttk.Label(f_scale, text="Skala OCR:").pack(side=tk.LEFT)
        val_scale = self.app.var_ocr_scale.get()
        lbl_scale = ttk.Label(f_scale, text=f"{val_scale:.2f}", width=5)
        s_scale = ttk.Scale(f_scale, from_=0.1, to=1.0, variable=self.app.var_ocr_scale,
                            command=lambda v: lbl_scale.config(text=f"{float(v):.2f}"))
        s_scale.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        s_scale.bind("<ButtonRelease-1>", self.app.on_manual_scale_change)
        lbl_scale.pack(side=tk.LEFT)

        # Empty Threshold
        f_empty = ttk.Frame(grp_cfg)
        f_empty.pack(fill=tk.X, pady=5)
        ttk.Label(f_empty, text="Czułość pustego:").pack(side=tk.LEFT)
        val_empty = self.app.var_empty_threshold.get()
        lbl_empty = ttk.Label(f_empty, text=f"{val_empty:.2f}")
        s_empty = ttk.Scale(f_empty, from_=0.0, to=0.6, variable=self.app.var_empty_threshold,
                            command=lambda v: lbl_empty.config(text=f"{float(v):.2f}"))
        s_empty.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        s_empty.bind("<ButtonRelease-1>",
                     lambda e: self.app._save_preset_val("empty_image_threshold",
                                                         round(self.app.var_empty_threshold.get(), 2)))
        lbl_empty.pack(side=tk.LEFT)

        # Interval
        f_int = ttk.Frame(grp_cfg)
        f_int.pack(fill=tk.X, pady=5)
        ttk.Label(f_int, text="Skanowanie (s):").pack(side=tk.LEFT)
        val_int = self.app.var_capture_interval.get()
        lbl_int = ttk.Label(f_int, text=f"{val_int:.2f}s")
        s_int = ttk.Scale(f_int, from_=0.3, to=1.0, variable=self.app.var_capture_interval,
                          command=lambda v: lbl_int.config(text=f"{float(v):.2f}s"))
        s_int.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        s_int.bind("<ButtonRelease-1>",
                   lambda e: self.app._save_preset_val("capture_interval",
                                                       round(self.app.var_capture_interval.get(), 2)))
        lbl_int.pack(side=tk.LEFT)

        # --- Optymalizacja ---
        grp_opt = ttk.LabelFrame(pnl, text="Optymalizacja i Poprawki", padding=10)
        grp_opt.pack(fill=tk.X, pady=10, padx=10)

        # Rerun
        f_rerun = ttk.Frame(grp_opt)
        f_rerun.pack(fill=tk.X, pady=5)
        ttk.Label(f_rerun, text="Ponów OCR krótszych niż:").pack(side=tk.LEFT)
        val_rerun = self.app.var_rerun_threshold.get()
        lbl_rerun = ttk.Label(f_rerun, text=f"{int(float(val_rerun))}", width=5)
        s_rerun = ttk.Scale(f_rerun, from_=0, to=150, variable=self.app.var_rerun_threshold,
                            command=lambda v: lbl_rerun.config(text=f"{int(float(v))}"))
        s_rerun.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        s_rerun.bind("<ButtonRelease-1>",
                     lambda e: self.app._save_preset_val("rerun_threshold", self.app.var_rerun_threshold.get()))
        lbl_rerun.pack(side=tk.LEFT)

        # Min Line
        f_min = ttk.Frame(grp_opt)
        f_min.pack(fill=tk.X, pady=5)
        ttk.Label(f_min, text="Ignoruj krótsze niż:").pack(side=tk.LEFT)
        val_min = self.app.var_min_line_len.get()
        lbl_min = ttk.Label(f_min, text=f"{int(float(val_min))}", width=5)
        s_min = ttk.Scale(f_min, from_=0, to=20, variable=self.app.var_min_line_len,
                          command=lambda v: lbl_min.config(text=f"{int(float(v))}"))
        s_min.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        s_min.bind("<ButtonRelease-1>",
                   lambda e: self.app._save_preset_val("min_line_length", self.app.var_min_line_len.get()))
        lbl_min.pack(side=tk.LEFT)

        # Alignment
        f_align = ttk.Frame(grp_opt)
        f_align.pack(fill=tk.X, pady=5)
        ttk.Label(f_align, text="Wyrównanie tekstu:").pack(side=tk.LEFT)
        cb_align = ttk.Combobox(f_align, textvariable=self.app.var_text_alignment, values=["Left", "Center", "Right"],
                                state="readonly", width=15)
        cb_align.pack(side=tk.LEFT, padx=5)
        cb_align.bind("<<ComboboxSelected>>",
                      lambda e: self.app._save_preset_val("text_alignment", self.app.var_text_alignment.get()))

        # --- Filtracja ---
        grp_reg = ttk.LabelFrame(pnl, text="Filtracja tekstu", padding=5)
        grp_reg.pack(fill=tk.X, pady=10, padx=10)
        f_r = ttk.Frame(grp_reg)
        f_r.pack(fill=tk.X)
        ttk.Label(f_r, text="Regex:").pack(side=tk.LEFT)
        cb_regex = ttk.Combobox(f_r, textvariable=self.app.var_regex_mode, values=list(self.app.regex_map.keys()),
                                state="readonly", width=25)
        cb_regex.pack(side=tk.LEFT, padx=5)
        cb_regex.bind("<<ComboboxSelected>>", self.app.on_regex_changed)

        # Entry dla Regex (stan kontrolowany przez callback w LektorApp, ale tutaj musimy go odświeżyć)
        ent_regex = ttk.Entry(f_r, textvariable=self.app.var_custom_regex)
        ent_regex.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        # Hack: aktualizujemy stan widgetu lokalnie
        mode = self.app.var_regex_mode.get()
        ent_regex.config(state="normal" if mode == "Własny (Regex)" else "disabled")
        # Musimy podmienić referencję w app, żeby on_regex_changed działał na tym widgecie?
        # app.ent_regex w lektor.py odnosi się do widgetu w oknie głównym (który został usunięty).
        # Rozwiązanie: Nadpiszmy self.app.ent_regex na ten lokalny, dopóki okno jest otwarte.
        self.app.ent_regex = ent_regex

        ent_regex.bind("<FocusOut>",
                       lambda e: self.app.config_mgr.update_setting('last_custom_regex',
                                                                    self.app.var_custom_regex.get()))
        ttk.Checkbutton(grp_reg, text="Usuwaj imiona (Smart)", variable=self.app.var_auto_names,
                        command=lambda: self.app._save_preset_val("auto_remove_names",
                                                                  self.app.var_auto_names.get())).pack(
            anchor=tk.W)

        # Checkbox logi
        ttk.Checkbutton(pnl, text="Zapisuj logi do pliku", variable=self.app.var_save_logs,
                        command=lambda: self.app._save_preset_val("save_logs", self.app.var_save_logs.get())).pack(
            anchor=tk.W, padx=10, pady=5)

        # --- Karta 2: Obraz (Globalne) ---
        tab_img = ttk.Frame(tabs)
        tabs.add(tab_img, text="OCR i Obraz")

        lf_ocr = ttk.LabelFrame(tab_img, text="Filtry obrazu", padding=10)
        lf_ocr.pack(fill=tk.X, pady=10, padx=5)

        ttk.Checkbutton(lf_ocr, text="Konwersja do skali szarości", variable=self.var_gray).pack(anchor=tk.W, pady=5)
        ttk.Checkbutton(lf_ocr, text="Podbicie kontrastu (Dla ciemnych gier)", variable=self.var_contrast).pack(
            anchor=tk.W, pady=5)

        # --- Karta 3: Skróty (Globalne) ---
        tab_hk = ttk.Frame(tabs)
        tabs.add(tab_hk, text="Skróty klawiszowe")

        lf_hk = ttk.LabelFrame(tab_hk, text="Definicja skrótów (format pynput)", padding=10)
        lf_hk.pack(fill=tk.X, pady=10, padx=5)

        ttk.Label(lf_hk, text="Start / Stop:").pack(anchor=tk.W)
        ttk.Entry(lf_hk, textvariable=self.var_hk_start).pack(fill=tk.X, pady=(0, 10))

        ttk.Label(lf_hk, text="Obszar 3 (Czasowy):").pack(anchor=tk.W)
        ttk.Entry(lf_hk, textvariable=self.var_hk_area3).pack(fill=tk.X, pady=(0, 10))

        ttk.Label(lf_hk, text="Przykłady: <ctrl>+<f5>, <alt>+x, <f9>", foreground="gray").pack(anchor=tk.W)

        # Przyciski
        btn_f = ttk.Frame(self)
        btn_f.pack(side=tk.BOTTOM, fill=tk.X, pady=10, padx=10)
        ttk.Button(btn_f, text="Zapisz", command=self.save).pack(side=tk.RIGHT)
        ttk.Button(btn_f, text="Anuluj", command=self.destroy).pack(side=tk.RIGHT, padx=5)

    def save(self):
        # Zapisz ustawienia globalne
        self.settings['ocr_grayscale'] = self.var_gray.get()
        self.settings['ocr_contrast'] = self.var_contrast.get()
        self.settings['hotkey_start_stop'] = self.var_hk_start.get()
        self.settings['hotkey_area3'] = self.var_hk_area3.get()
        self.destroy()