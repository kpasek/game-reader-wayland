import tkinter as tk
from tkinter import ttk

class OptimizationResultWindow(tk.Toplevel):
    def __init__(self, parent, score, settings, optimized_area, existing_areas, on_apply):
        super().__init__(parent)
        self.title("Wynik Optymalizacji")
        self.geometry("450x600")
        self.on_apply = on_apply
        self.result_data = None
        
        content = ttk.Frame(self, padding=20)
        content.pack(fill="both", expand=True)

        ttk.Label(content, text="Znaleziono optymalne ustawienia", font=("Arial", 12, "bold")).pack(pady=(0, 15))
        
        def add_row(label, value):
            f = ttk.Frame(content)
            f.pack(fill="x", pady=3)
            ttk.Label(f, text=label, width=22, anchor="w").pack(side="left")
            ttk.Label(f, text=str(value), font=("Arial", 10, "bold")).pack(side="left")

        display_score = min(score, 100)
        add_row("Wynik (Score):", f"{display_score:.1f}%")
        
        if optimized_area:
            ox, oy, ow, oh = optimized_area
            add_row("Wykryty obszar:", f"X:{ox}, Y:{oy}, {ow}x{oh}")

        add_row("Jasność (Threshold):", settings.get('brightness_threshold', '-'))
        add_row("Kontrast:", settings.get('contrast', '-'))
        add_row("Skala OCR:", settings.get('ocr_scale_factor', '-'))
        
        # Colors
        cols = settings.get('subtitle_colors', [])
        f_cols = ttk.Frame(content)
        f_cols.pack(fill="x", pady=3)
        ttk.Label(f_cols, text="Kolory:", width=22, anchor="w").pack(side="left")
        if not cols:
            ttk.Label(f_cols, text="Brak (Grayscale)", font=("Arial", 10, "bold")).pack(side="left")
        else:
            cframe = ttk.Frame(f_cols)
            cframe.pack(side="left")
            for c in cols:
                swatch = tk.Label(cframe, bg=c, width=2, relief="solid", borderwidth=1)
                swatch.pack(side="left", padx=2)
                ttk.Label(cframe, text=c).pack(side="left", padx=(0, 5))

        add_row("Tolerancja:", settings.get('color_tolerance', '-'))

        # Area Selection
        ttk.Separator(content, orient="horizontal").pack(fill="x", pady=15)
        ttk.Label(content, text="Zastosuj ustawienia do:", font=("Arial", 11, "bold")).pack(pady=(0, 10), anchor="w")
        
        area_options = ["Utwórz nowy obszar"]
        area_map = {} 
        for a in existing_areas:
            aid = a.get('id')
            aname = f"Obszar #{aid}"
            if a.get('type'):
                aname += f" ({'Stały' if a.get('type') == 'continuous' else 'Wyzwalany'})"
            area_options.append(aname)
            area_map[aname] = aid
            
        self.selected_option = tk.StringVar(value=area_options[0])
        # Default to Area #1 if exists
        for name, aid in area_map.items():
            if aid == 1:
                self.selected_option.set(name)
                break
                
        cb = ttk.Combobox(content, textvariable=self.selected_option, values=area_options, state="readonly")
        cb.pack(fill="x", pady=5)
        
        btn_frame = ttk.Frame(self, padding=10)
        btn_frame.pack(side="bottom", fill="x")
        
        ttk.Button(btn_frame, text="Zastosuj i Zapisz", command=self._confirm).pack(side="right", padx=5)
        ttk.Button(btn_frame, text="Anuluj", command=self.destroy).pack(side="right")

    def _confirm(self):
        choice = self.selected_option.get()
        target_id = None
        if choice != "Utwórz nowy obszar":
            # Extract ID from string like "Obszar #1 (Stały)"
            try:
                # Based on my code above: f"Obszar #{aid}"
                parts = choice.split('#')
                if len(parts) > 1:
                    target_id = int(parts[1].split()[0])
            except:
                pass
                
        self.on_apply({"confirmed": True, "target_id": target_id})
        self.destroy()
