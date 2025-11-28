import sys
from typing import Any, Dict

try:
    import tkinter as tk
    from tkinter import ttk
except ImportError:
    sys.exit(1)


class SettingsDialog(tk.Toplevel):
    """
    Okno dialogowe do globalnych ustawień OCR i preprocessingu.
    Modyfikuje przekazany słownik 'settings' w miejscu (mutable).
    """

    def __init__(self, parent, settings: Dict[str, Any]):
        super().__init__(parent)
        self.transient(parent)
        self.title("Ustawienia zaawansowane")
        self.settings = settings

        self.var_mode = tk.StringVar(value=settings.get('subtitle_mode', 'Full Lines'))
        self.var_scale = tk.DoubleVar(value=settings.get('ocr_scale_factor', 1.0))
        self.var_gray = tk.BooleanVar(value=settings.get('ocr_grayscale', False))
        self.var_contrast = tk.BooleanVar(value=settings.get('ocr_contrast', False))

        self._build_ui()
        self.geometry("400x350")
        self.grab_set()

    def _build_ui(self):
        frame = ttk.Frame(self, padding=10)
        frame.pack(fill=tk.BOTH, expand=True)

        # Tryb napisów
        lf_mode = ttk.LabelFrame(frame, text="Algorytm dopasowania", padding=5)
        lf_mode.pack(fill=tk.X, pady=5)
        ttk.Radiobutton(lf_mode, text="Pełne linie (Dokładne)", value="Full Lines", variable=self.var_mode).pack(
            anchor=tk.W)
        ttk.Radiobutton(lf_mode, text="Fragmenty (Eksperymentalne)", value="Partial Lines",
                        variable=self.var_mode).pack(anchor=tk.W)

        # OCR
        lf_ocr = ttk.LabelFrame(frame, text="Tweakowanie OCR", padding=5)
        lf_ocr.pack(fill=tk.X, pady=5)

        f_sc = ttk.Frame(lf_ocr)
        f_sc.pack(fill=tk.X)
        ttk.Label(f_sc, text="Skala obrazu:").pack(side=tk.LEFT)
        vals = [round(x * 0.1, 1) for x in range(10, 1, -1)]
        ttk.Combobox(f_sc, textvariable=self.var_scale, values=vals, width=5, state="readonly").pack(side=tk.LEFT,
                                                                                                     padx=5)
        ttk.Label(f_sc, text="(mniejsza = szybciej, ale mniej dokładnie)").pack(side=tk.LEFT)

        ttk.Checkbutton(lf_ocr, text="Konwersja do skali szarości", variable=self.var_gray).pack(anchor=tk.W, pady=2)
        ttk.Checkbutton(lf_ocr, text="Podbicie kontrastu", variable=self.var_contrast).pack(anchor=tk.W, pady=2)

        # Przyciski
        btn_f = ttk.Frame(frame)
        btn_f.pack(side=tk.BOTTOM, fill=tk.X, pady=10)
        ttk.Button(btn_f, text="Zapisz", command=self.save).pack(side=tk.RIGHT)
        ttk.Button(btn_f, text="Anuluj", command=self.destroy).pack(side=tk.RIGHT, padx=5)

    def save(self):
        self.settings['subtitle_mode'] = self.var_mode.get()
        self.settings['ocr_scale_factor'] = self.var_scale.get()
        self.settings['ocr_grayscale'] = self.var_gray.get()
        self.settings['ocr_contrast'] = self.var_contrast.get()
        self.destroy()