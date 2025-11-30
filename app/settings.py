import sys
from typing import Any, Dict

try:
    import tkinter as tk
    from tkinter import ttk
except ImportError:
    sys.exit(1)


class SettingsDialog(tk.Toplevel):
    """
    Okno dialogowe do globalnych ustawień OCR i preprocessingu (Tylko filtry obrazu).
    """

    def __init__(self, parent, settings: Dict[str, Any]):
        super().__init__(parent)
        self.transient(parent)
        self.title("Ustawienia Obrazu OCR")
        self.settings = settings

        self.var_gray = tk.BooleanVar(value=settings.get('ocr_grayscale', False))
        self.var_contrast = tk.BooleanVar(value=settings.get('ocr_contrast', False))

        self._build_ui()
        self.geometry("300x200")
        self.grab_set()

    def _build_ui(self):
        frame = ttk.Frame(self, padding=10)
        frame.pack(fill=tk.BOTH, expand=True)

        # OCR
        lf_ocr = ttk.LabelFrame(frame, text="Filtry obrazu", padding=5)
        lf_ocr.pack(fill=tk.X, pady=5)

        ttk.Checkbutton(lf_ocr, text="Konwersja do skali szarości", variable=self.var_gray).pack(anchor=tk.W, pady=5)
        ttk.Checkbutton(lf_ocr, text="Podbicie kontrastu (Dla ciemnych gier)", variable=self.var_contrast).pack(anchor=tk.W, pady=5)

        # Przyciski
        btn_f = ttk.Frame(frame)
        btn_f.pack(side=tk.BOTTOM, fill=tk.X, pady=10)
        ttk.Button(btn_f, text="Zapisz", command=self.save).pack(side=tk.RIGHT)
        ttk.Button(btn_f, text="Anuluj", command=self.destroy).pack(side=tk.RIGHT, padx=5)

    def save(self):
        self.settings['ocr_grayscale'] = self.var_gray.get()
        self.settings['ocr_contrast'] = self.var_contrast.get()
        self.destroy()