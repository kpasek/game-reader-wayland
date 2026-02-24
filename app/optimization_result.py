import tkinter as tk
from tkinter import ttk
from app.ctk_widgets import CTkToplevel, make_frame, make_label, make_button, make_combobox, make_separator


class OptimizationResultWindow(CTkToplevel):
    def __init__(self, parent, score, settings, optimized_area, existing_areas, on_apply):
        super().__init__(parent)
        self.title("Wynik Optymalizacji")
        self.geometry("500x500")
        self.on_apply = on_apply
        self.result_data = None

        content = make_frame(self, padding=20)
        content.pack(fill="both", expand=True)

        make_label(content, text="Znaleziono optymalne ustawienia", font=("Arial", 12, "bold")).pack(pady=(0, 15))
        
        def add_row(label, value):
            f = make_frame(content)
            f.pack(fill="x", pady=3)
            make_label(f, text=label).pack(side="left")
            make_label(f, text=str(value), font=("Arial", 10, "bold")).pack(side="left")

        display_score = min(score, 100)
        add_row("Wynik (Score):", f"{display_score:.1f}%")
        
        if optimized_area:
            ox, oy, ow, oh = optimized_area
            add_row("Wykryty obszar:", f"X:{ox}, Y:{oy}, {ow}x{oh}")

        add_row("Jasność (Threshold):", settings.brightness_threshold)
        add_row("Kontrast:", settings.contrast)
        add_row("Skala OCR:", settings.ocr_scale_factor)
        
        # Colors
        cols = getattr(settings, 'colors', [])
        f_cols = make_frame(content)
        f_cols.pack(fill="x", pady=3)
        make_label(f_cols, text="Kolory:").pack(side="left")
        if not cols:
            make_label(f_cols, text="Brak (Grayscale)", font=("Arial", 10, "bold")).pack(side="left")
        else:
            cframe = make_frame(f_cols)
            cframe.pack(side="left")
            for c in cols:
                swatch = tk.Label(cframe, bg=c, width=2, relief="solid", borderwidth=1)
                swatch.pack(side="left", padx=2)
                make_label(cframe, text=c).pack(side="left", padx=(0, 5))

        add_row("Tolerancja:", settings.color_tolerance)

        # Area Selection
        make_separator(content, orient="horizontal").pack(fill="x", pady=15)
        make_label(content, text="Zastosuj ustawienia do:", font=("Arial", 11, "bold")).pack(pady=(0, 10), anchor="w")
        
        area_options = ["Utwórz nowy obszar"]
        area_map = {} 
        for a in existing_areas:
            aid = getattr(a, 'id', None)
            aname = f"Obszar #{aid}"
            if getattr(a, 'type', None):
                aname += f" ({'Stały' if a.type == 'continuous' else 'Wyzwalany'})"
            area_options.append(aname)
            area_map[aname] = aid
            
        self.selected_option = tk.StringVar(value=area_options[0])
        # Default to Area #1 if exists
        for name, aid in area_map.items():
            if aid == 1:
                self.selected_option.set(name)
                break
                
        cb = make_combobox(content, textvariable=self.selected_option, values=area_options, state="readonly")
        cb.pack(fill="x", pady=5)

        btn_frame = make_frame(self, padding=10)
        btn_frame.pack(side="bottom", fill="x")

        make_button(btn_frame, text="Zastosuj i Zapisz", command=self._confirm).pack(side="right", padx=5)
        make_button(btn_frame, text="Anuluj", command=self.destroy).pack(side="right")

    def _confirm(self):
        choice = self.selected_option.get()
        target_id = None
        if choice != "Utwórz nowy obszar":
            # Extract ID from string like "Obszar #area_0 (Stały)" or "Obszar #1"
            try:
                parts = choice.split('#')
                if len(parts) > 1:
                    target_id = parts[1].split()[0]
                    # Convert to int if it's purely numerical, otherwise keep as string
                    if target_id.isdigit():
                        target_id = int(target_id)
            except:
                pass
                
        self.on_apply({"confirmed": True, "target_id": target_id})
        self.destroy()
