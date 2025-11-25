import sys
from typing import Any, Dict


try:
    import tkinter as tk
    from tkinter import ttk
except ImportError:
    print("Błąd: Nie znaleziono biblioteki 'tkinter'.", file=sys.stderr)
    print("Zazwyczaj jest dołączona do Pythona. W Debian/Ubuntu: sudo apt install python3-tk", file=sys.stderr)
    sys.exit(1)

    
class SettingsDialog(tk.Toplevel):
    """Okno dialogowe do edycji ustawień aplikacji."""

    def __init__(self, parent, settings: Dict[str, Any]):
        super().__init__(parent)
        self.transient(parent)
        self.title("Ustawienia")

        self.settings = settings
        self.result = None

        # Zmienne Tkinter
        self.subtitle_mode_var = tk.StringVar(
            value=self.settings.get('subtitle_mode', 'Full Lines'))
        self.ocr_scale_var = tk.DoubleVar(
            value=self.settings.get('ocr_scale_factor', 1.0))
        self.ocr_grayscale_var = tk.BooleanVar(
            value=self.settings.get('ocr_grayscale', False))
        self.ocr_contrast_var = tk.BooleanVar(
            value=self.settings.get('ocr_contrast', False))

        frame = ttk.Frame(self, padding="10")
        frame.pack(fill=tk.BOTH, expand=True)

        # --- Grupa Trybu Napisów ---
        mode_group = ttk.LabelFrame(
            frame, text="Tryb dopasowania napisów", padding="10")
        mode_group.pack(fill=tk.X, pady=5)
        # ... (Radiobuttony bez zmian) ...
        ttk.Radiobutton(
            mode_group, text="Pełne linie", value="Full Lines", variable=self.subtitle_mode_var
        ).pack(anchor=tk.W)
        ttk.Radiobutton(
            mode_group, text="Częściowe linie (eksperymentalne)", value="Partial Lines", variable=self.subtitle_mode_var
        ).pack(anchor=tk.W)

        ocr_group = ttk.LabelFrame(
            frame, text="Wydajność i Preprocessing OCR", padding="10")
        ocr_group.pack(fill=tk.X, pady=5)

        # Skalowanie
        scale_frame = ttk.Frame(ocr_group)
        scale_frame.pack(fill=tk.X)
        ttk.Label(scale_frame, text="Skala obrazu:").pack(side=tk.LEFT)
        scale_combo = ttk.Combobox(
            scale_frame,
            textvariable=self.ocr_scale_var,
            values=[1.0, 0.75, 0.5],
            state="readonly",
            width=5
        )
        scale_combo.pack(side=tk.LEFT, padx=5)
        ttk.Label(scale_frame, text="(mniejsza = szybszy OCR, niższa jakość)").pack(
            side=tk.LEFT)

        # Checkboxy
        ttk.Checkbutton(
            ocr_group, text="Konwertuj do skali szarości", variable=self.ocr_grayscale_var
        ).pack(anchor=tk.W, pady=(5, 0))

        ttk.Checkbutton(
            ocr_group, text="Zwiększ kontrast (może pomóc z dziwnymi czcionkami)", variable=self.ocr_contrast_var
        ).pack(anchor=tk.W)

        # --- Przyciski Zapisz/Anuluj ---
        button_frame = ttk.Frame(frame)
        button_frame.pack(fill=tk.X, side=tk.BOTTOM, pady=(10, 0))
        # ... (Przyciski bez zmian) ...
        ttk.Button(button_frame, text="Anuluj",
                   command=self.destroy).pack(side=tk.RIGHT, padx=5)
        ttk.Button(button_frame, text="Zapisz",
                   command=self.save_and_close).pack(side=tk.RIGHT)

        self.geometry("450x380")  # Zwiększono wysokość
        self.grab_set()
        self.wait_window()

    def save_and_close(self):
        """Aktualizuje słownik ustawień i zamyka okno."""
        self.settings['subtitle_mode'] = self.subtitle_mode_var.get()
        self.settings['ocr_scale_factor'] = self.ocr_scale_var.get()
        self.settings['ocr_grayscale'] = self.ocr_grayscale_var.get()
        self.settings['ocr_contrast'] = self.ocr_contrast_var.get()

        self.result = self.settings
        self.destroy()
