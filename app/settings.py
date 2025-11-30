import sys
from typing import Any, Dict

try:
    import tkinter as tk
    from tkinter import ttk
except ImportError:
    sys.exit(1)


class SettingsDialog(tk.Toplevel):
    """
    Okno dialogowe do globalnych ustawień aplikacji.
    """

    def __init__(self, parent, settings: Dict[str, Any]):
        super().__init__(parent)
        self.transient(parent)
        self.title("Ustawienia aplikacji")
        self.settings = settings

        # Zmienne UI
        self.var_gray = tk.BooleanVar(value=settings.get('ocr_grayscale', False))
        self.var_contrast = tk.BooleanVar(value=settings.get('ocr_contrast', False))

        self.var_hk_start = tk.StringVar(value=settings.get('hotkey_start_stop', '<ctrl>+<f5>'))
        self.var_hk_area3 = tk.StringVar(value=settings.get('hotkey_area3', '<ctrl>+<f6>'))

        self._build_ui()
        self.geometry("400x400")
        self.grab_set()

    def _build_ui(self):
        tabs = ttk.Notebook(self)
        # POPRAWKA: padding -> padx, pady
        tabs.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Karta 1: Obraz
        tab_img = ttk.Frame(tabs)
        tabs.add(tab_img, text="OCR i Obraz")

        lf_ocr = ttk.LabelFrame(tab_img, text="Filtry obrazu", padding=10)
        lf_ocr.pack(fill=tk.X, pady=10, padx=5)

        ttk.Checkbutton(lf_ocr, text="Konwersja do skali szarości", variable=self.var_gray).pack(anchor=tk.W, pady=5)
        ttk.Checkbutton(lf_ocr, text="Podbicie kontrastu (Dla ciemnych gier)", variable=self.var_contrast).pack(
            anchor=tk.W, pady=5)

        # Karta 2: Skróty
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
        self.settings['ocr_grayscale'] = self.var_gray.get()
        self.settings['ocr_contrast'] = self.var_contrast.get()
        self.settings['hotkey_start_stop'] = self.var_hk_start.get()
        self.settings['hotkey_area3'] = self.var_hk_area3.get()
        self.destroy()