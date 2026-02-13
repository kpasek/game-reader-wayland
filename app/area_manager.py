import tkinter as tk
from tkinter import ttk, messagebox, colorchooser
import threading
from typing import List, Dict, Any, Optional

try:
    from pynput import keyboard
except ImportError:
    keyboard = None

from app.area_selector import AreaSelector, ColorSelector
from app.capture import capture_fullscreen


class AreaManagerWindow(tk.Toplevel):
    def __init__(self, parent, areas: List[Dict[str, Any]], on_save_callback):
        super().__init__(parent)
        self.title("Zarządzanie Obszarami")
        self.geometry("1000x700")
        self.areas = [a.copy() for a in areas]
        
        # Migration: Move top-level colors provided by legacy code to settings
        for a in self.areas:
            if 'settings' not in a:
                a['settings'] = {}
            if 'colors' in a and a['colors']:
                if 'subtitle_colors' not in a['settings']:
                    a['settings']['subtitle_colors'] = list(a['colors'])
                del a['colors']

        self.on_save = on_save_callback
        self.current_selection_idx = -1
        self.ignore_updates = False

        self._init_ui()
        self._refresh_list()
        
        # Select first if exists
        if self.areas:
            self.current_selection_idx = 0
            self._refresh_list()
        else:
            self._add_default_area()

    def _init_ui(self):
        # Left side: List
        left_frame = ttk.Frame(self, padding=5)
        left_frame.pack(side=tk.LEFT, fill=tk.Y)

        ttk.Label(left_frame, text="Lista Obszarów").pack(anchor=tk.W)
        self.lb_areas = tk.Listbox(left_frame, width=30)
        self.lb_areas.pack(fill=tk.BOTH, expand=True, pady=5)
        self.lb_areas.bind('<<ListboxSelect>>', self._on_list_select)

        btn_frame = ttk.Frame(left_frame)
        btn_frame.pack(fill=tk.X)
        ttk.Button(btn_frame, text="+ Dodaj", command=self._add_area).pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.btn_remove = ttk.Button(btn_frame, text="- Usuń", command=self._remove_area, state=tk.DISABLED)
        self.btn_remove.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        # Save / Close
        action_frame = ttk.Frame(left_frame, padding=(0, 20, 0, 0))
        action_frame.pack(fill=tk.X, side=tk.BOTTOM)
        ttk.Button(action_frame, text="Zapisz i Zamknij", command=self._save_and_close).pack(fill=tk.X, pady=5)
        ttk.Button(action_frame, text="Anuluj", command=self.destroy).pack(fill=tk.X)

        # Right side: Full Editor (Notebook)
        self.right_frame = ttk.Frame(self, padding=10)
        self.right_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        self.notebook = ttk.Notebook(self.right_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True)
        
        # Tab 1: Ogólne (Type, Rect, Hotkey)
        self.tab_general = ttk.Frame(self.notebook, padding=15)
        self.notebook.add(self.tab_general, text="Ogólne")
        self._init_tab_general(self.tab_general)
        
        # Tab 2: Obraz i OCR (Scale, Brightness, etc.)
        self.tab_ocr = ttk.Frame(self.notebook, padding=15)
        self.notebook.add(self.tab_ocr, text="Obraz i OCR")
        self._init_tab_ocr(self.tab_ocr)
        
        # Tab 3: Kolory (Colors List)
        self.tab_colors = ttk.Frame(self.notebook, padding=15)
        self.notebook.add(self.tab_colors, text="Kolory")
        self._init_tab_colors(self.tab_colors)

    def _init_tab_general(self, parent):
        grid = ttk.Frame(parent)
        grid.pack(fill=tk.X)
        grid.columnconfigure(1, weight=1)
        
        # Type
        ttk.Label(grid, text="Typ obszaru:", font=("Arial", 10, "bold")).grid(row=0, column=0, sticky=tk.W, pady=10)
        self.var_type = tk.StringVar()
        self.type_mapping = {"continuous": "Stały (Ciągłe czytanie)", "manual": "Wyzwalany (Na żądanie)"}
        self.rev_type_mapping = {v: k for k, v in self.type_mapping.items()}
        self.cb_type = ttk.Combobox(grid, textvariable=self.var_type, values=list(self.type_mapping.values()), state="readonly")
        self.cb_type.grid(row=0, column=1, sticky=tk.EW, padx=10)
        self.cb_type.bind("<<ComboboxSelected>>", self._on_field_change)
        
        # Tab General
        self.var_enabled = tk.BooleanVar()
        self.chk_enabled = ttk.Checkbutton(grid, text="Aktywny (Włączony)", variable=self.var_enabled, command=self._on_field_change)
        self.chk_enabled.grid(row=1, column=1, sticky=tk.W, padx=10)

        # Rect
        ttk.Separator(parent, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=15)
        
        f_rect = ttk.Frame(parent)
        f_rect.pack(fill=tk.X)
        ttk.Label(f_rect, text="Pozycja i Rozmiar:", font=("Arial", 10, "bold")).pack(anchor=tk.W)
        self.lbl_rect = ttk.Label(f_rect, text="Brak zdefiniowanego obszaru", foreground="#555")
        self.lbl_rect.pack(anchor=tk.W, pady=5)
        ttk.Button(f_rect, text="[ ] Zaznacz obszar na ekranie", command=self._select_area_on_screen).pack(anchor=tk.W, pady=5)
        
        # Hotkey
        ttk.Separator(parent, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=15)
        
        f_hk = ttk.Frame(parent)
        f_hk.pack(fill=tk.X)
        ttk.Label(f_hk, text="Skrót klawiszowy:", font=("Arial", 10, "bold")).pack(anchor=tk.W)
        
        h_row = ttk.Frame(f_hk)
        h_row.pack(fill=tk.X, pady=5)
        self.var_hotkey = tk.StringVar()
        self.entry_hotkey = ttk.Entry(h_row, textvariable=self.var_hotkey, state="readonly")
        self.entry_hotkey.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.btn_record = ttk.Button(h_row, text="Nagraj", command=self._record_hotkey)
        self.btn_record.pack(side=tk.LEFT, padx=5)
        ttk.Button(h_row, text="X", width=3, command=self._clear_hotkey).pack(side=tk.LEFT)

    def _init_tab_ocr(self, parent):
        pl = ttk.Frame(parent)
        pl.pack(fill=tk.BOTH, expand=True)
        pl.columnconfigure(1, weight=1)
        r = 0
        def add_row(label, widget):
            nonlocal r
            ttk.Label(pl, text=label).grid(row=r, column=0, sticky=tk.W, pady=5, padx=5)
            widget.grid(row=r, column=1, sticky=tk.EW, pady=5, padx=5)
            r += 1
            return widget

        # Scale
        f_scale = ttk.Frame(pl)
        self.var_scale = tk.DoubleVar()
        ttk.Scale(f_scale, from_=0.5, to=3.0, variable=self.var_scale, command=lambda v: self._on_field_change()).pack(side=tk.LEFT, fill=tk.X, expand=True)
        l_sc = ttk.Label(f_scale, text="1.0")
        l_sc.pack(side=tk.LEFT, padx=5)
        self.var_scale.trace_add("write", lambda *a: l_sc.config(text=f"{self.var_scale.get():.2f}"))
        add_row("Skala OCR:", f_scale)
        
        # Thickening
        f_th = ttk.Frame(pl)
        self.var_thickening = tk.IntVar()
        ttk.Scale(f_th, from_=0, to=5, variable=self.var_thickening, command=lambda v: self._on_field_change()).pack(side=tk.LEFT, fill=tk.X, expand=True)
        l_th = ttk.Label(f_th, text="0")
        l_th.pack(side=tk.LEFT, padx=5)
        self.var_thickening.trace_add("write", lambda *a: l_th.config(text=f"{self.var_thickening.get()}"))
        add_row("Pogrubienie:", f_th)
        
        # Mode
        self.var_mode = tk.StringVar()
        cb_mode = ttk.Combobox(pl, textvariable=self.var_mode, values=["Full Lines", "Partial"], state="readonly")
        cb_mode.bind("<<ComboboxSelected>>", self._on_field_change)
        add_row("Tryb dopasowania:", cb_mode)
        
        # Color Mode
        self.var_cmode = tk.StringVar()
        cb_cm = ttk.Combobox(pl, textvariable=self.var_cmode, values=["Light", "Dark", "Mixed"], state="readonly")
        cb_cm.bind("<<ComboboxSelected>>", self._on_field_change)
        add_row("Tryb koloru tła:", cb_cm)
        
        # Brightness
        f_br = ttk.Frame(pl)
        self.var_brightness = tk.IntVar()
        ttk.Scale(f_br, from_=0, to=255, variable=self.var_brightness, command=lambda v: self._on_field_change()).pack(side=tk.LEFT, fill=tk.X, expand=True)
        l_br = ttk.Label(f_br, textvariable=self.var_brightness)
        l_br.pack(side=tk.LEFT, padx=5)
        add_row("Próg jasności:", f_br)
        
        # Contrast
        f_co = ttk.Frame(pl)
        self.var_contrast = tk.DoubleVar()
        ttk.Scale(f_co, from_=0.0, to=5.0, variable=self.var_contrast, command=lambda v: self._on_field_change()).pack(side=tk.LEFT, fill=tk.X, expand=True)
        l_co = ttk.Label(f_co, text="0.0")
        l_co.pack(side=tk.LEFT, padx=5)
        self.var_contrast.trace_add("write", lambda *a: l_co.config(text=f"{self.var_contrast.get():.1f}"))
        add_row("Kontrast:", f_co)

    def _init_tab_colors(self, parent):
        self.var_use_colors = tk.BooleanVar()
        self.chk_use_colors.pack(anchor=tk.W, pady=10)
        
        row = ttk.Frame(parent)
        row.pack(fill=tk.BOTH, expand=True)
        
        self.lb_colors = tk.Listbox(row, height=8)
        self.lb_colors.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        btns = ttk.Frame(row)
        btns.pack(side=tk.LEFT, fill=tk.Y, padx=5)
        ttk.Button(btns, text="Pobierz z Ekranu", command=self._pick_color_screen).pack(fill=tk.X, pady=2)
        ttk.Button(btns, text="Dodaj Biały", command=lambda: self._add_color_manual("#FFFFFF")).pack(fill=tk.X, pady=2)
        ttk.Button(btns, text="Usuń zaznaczony", command=self._remove_color).pack(fill=tk.X, pady=2)
        
        # Tolerance
        f_tol = ttk.Frame(parent)
        f_tol.pack(fill=tk.X, pady=15)
        ttk.Label(f_tol, text="Tolerancja koloru:").pack(anchor=tk.W)
        self.var_tolerance = tk.IntVar()
        ttk.Scale(f_tol, from_=0, to=100, variable=self.var_tolerance, orient=tk.HORIZONTAL, command=lambda v: self._on_field_change()).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Label(f_tol, textvariable=self.var_tolerance).pack(side=tk.LEFT, padx=5)

    def _load_details(self, idx):
        self.ignore_updates = True
        area = self.areas[idx]
        settings = area.get('settings', {})
        
        # Tab General
        typ = area.get('type', 'manual')
        self.var_type.set(self.type_mapping.get(typ, typ))
        
        self.var_enabled.set(area.get('enabled', False))
        if typ == 'continuous' and area.get('id') != 1:
            self.chk_enabled.config(state=tk.NORMAL)
        else:
            self.chk_enabled.config(state=tk.DISABLED)
            
        r = area.get('rect')
        if r:
            self.lbl_rect.config(text=f"X:{r.get('left')} Y:{r.get('top')} {r.get('width')}x{r.get('height')}")
        else:
            self.lbl_rect.config(text="Brak (Kliknij 'Wybierz Obszar')")
            
        self.var_hotkey.set(area.get('hotkey', ''))
        
        # Tab OCR
        self.var_scale.set(settings.get('ocr_scale_factor', 1.0))
        self.var_thickening.set(settings.get('text_thickening', 0))
        self.var_mode.set(settings.get('subtitle_mode', 'Full Lines'))
        self.var_cmode.set(settings.get('text_color_mode', 'Light'))
        self.var_brightness.set(settings.get('brightness_threshold', 200))
        self.var_contrast.set(settings.get('contrast', 0.0))
        
        # Tab Colors
        self.var_use_colors.set(settings.get('use_colors', True))
        self.var_tolerance.set(settings.get('color_tolerance', 10))
        
        self.lb_colors.delete(0, tk.END)
        for c in settings.get('subtitle_colors', []):
            self.lb_colors.insert(tk.END, c)
            
        self.ignore_updates = False
        
        for tab in [self.tab_general, self.tab_ocr, self.tab_colors]:
             for child in tab.winfo_children():
                 try: child.config(state=tk.NORMAL)
                 except: pass
                 
    def _disable_details(self):
         # Helper to disable right pane when no selection
         pass # Implementation skipped for brevity, user likely selects first item always

    def _on_field_change(self, event=None):
        if self.ignore_updates or self.current_selection_idx < 0: return
        
        area = self.areas[self.current_selection_idx]
        if 'settings' not in area: area['settings'] = {}
        s = area['settings']
        
        # Map back to area/settings struct
        disp_type = self.var_type.get()
        real_type = self.rev_type_mapping.get(disp_type, disp_type)
        area['type'] = real_type
        
        area['enabled'] = self.var_enabled.get()
        area['hotkey'] = self.var_hotkey.get()
        
        s['ocr_scale_factor'] = self.var_scale.get()
        s['text_thickening'] = self.var_thickening.get()
        s['subtitle_mode'] = self.var_mode.get()
        s['text_color_mode'] = self.var_cmode.get()
        s['brightness_threshold'] = self.var_brightness.get()
        s['contrast'] = self.var_contrast.get()
        s['use_colors'] = self.var_use_colors.get()
        s['color_tolerance'] = self.var_tolerance.get()
        
        # Refresh list name if type changed
        self.lb_areas.delete(self.current_selection_idx)
        typ_raw = area.get('type')
        t = "Stały" if typ_raw == 'continuous' else "Wyzwalany"
        display = f"#{area.get('id')} [{t}]"
        if typ_raw == 'continuous' and area.get('id') != 1:
             state = "ON" if area.get('enabled') else "OFF"
             display += f" [{state}]"
        self.lb_areas.insert(self.current_selection_idx, display)
        self.lb_areas.selection_set(self.current_selection_idx)

    def _refresh_list(self):
        self.lb_areas.delete(0, tk.END)
        for i, area in enumerate(self.areas):
            typ_raw = area.get('type', 'manual')
            t = "Stały" if typ_raw == 'continuous' else "Wyzwalany"
            if typ_raw not in ['continuous', 'manual']: t = typ_raw
            
            display = f"#{area.get('id', i+1)} [{t}]"

            if typ_raw == 'continuous' and area.get('id') != 1:
                state = "ON" if area.get('enabled', False) else "OFF"
                display += f" [{state}]"

            self.lb_areas.insert(tk.END, display)
        
        if self.current_selection_idx >= 0 and self.current_selection_idx < len(self.areas):
            self.lb_areas.selection_set(self.current_selection_idx)
            self._load_details(self.current_selection_idx)
            
            area = self.areas[self.current_selection_idx]
            if area.get('id') == 1:
                 self.btn_remove.config(state=tk.DISABLED)
            else:
                 self.btn_remove.config(state=tk.NORMAL)
        else:
            self._disable_details()

    def _disable_details(self):
        self.ignore_updates = True
        self.var_type.set("")
        self.lbl_rect.config(text="Brak zaznaczenia")
        self.var_hotkey.set("")
        self.lb_colors.delete(0, tk.END)
        
        for tab in [self.tab_general, self.tab_ocr, self.tab_colors]:
             for child in tab.winfo_children():
                 try: child.config(state=tk.DISABLED)
                 except: pass
        self.ignore_updates = False

    def _add_area(self):
        if len(self.areas) >= 5:
            messagebox.showinfo("Limit", "Osiągnięto limit obszarów (5).")
            return
            
        existing_ids = {a.get('id', 0) for a in self.areas}
        next_id = 1
        while next_id in existing_ids:
            next_id += 1
            
        self.areas.append({
            "id": next_id,
            "type": "manual",
            "rect": None,
            "hotkey": "",
            "settings": {}
        })
        self.current_selection_idx = len(self.areas) - 1
        self._refresh_list()

    def _remove_area(self):
        if self.current_selection_idx < 0: return
        area = self.areas[self.current_selection_idx]
        if area.get('id') == 1:
            messagebox.showwarning("Błąd", "Nie można usunąć głównego obszaru.")
            return
            
        del self.areas[self.current_selection_idx]
        if self.current_selection_idx >= len(self.areas):
            self.current_selection_idx = len(self.areas) - 1
        self._refresh_list()

    def _on_list_select(self, event):
        sel = self.lb_areas.curselection()
        if not sel: return
        self.current_selection_idx = sel[0]
        self._refresh_list() 

    def _add_default_area(self):
         self.areas.append({
                "id": 1,
                "type": "continuous",
                "rect": None,
                "hotkey": "",
                "settings": {}
            })
         self._refresh_list()

    def _select_area_on_screen(self):
        if self.current_selection_idx < 0: return
        self.withdraw()
        self.update() 
        import time
        time.sleep(0.3)
        
        try:
            img = capture_fullscreen()
            if not img:
                self.deiconify()
                return
            
            sel = AreaSelector(self.master, img, existing_regions=self.areas) 
            self.wait_window(sel)
            
            if sel.geometry:
                self.areas[self.current_selection_idx]['rect'] = sel.geometry
                self._load_details(self.current_selection_idx)
                
                # Auto update bounds label
                r = sel.geometry
                self.lbl_rect.config(text=f"X:{r.get('left')} Y:{r.get('top')} {r.get('width')}x{r.get('height')}")

        except Exception as e:
            print(f"Error selecting area: {e}")
        finally:
            self.deiconify()

    def _add_color_manual(self, color):
        if self.current_selection_idx < 0: return
        area = self.areas[self.current_selection_idx]
        if 'settings' not in area: area['settings'] = {}
        
        colors = area['settings'].setdefault('subtitle_colors', [])
        if color not in colors:
            colors.append(color)
            # Safe update
            s = set(colors)
            area['settings']['subtitle_colors'] = list(s)
            self._load_details(self.current_selection_idx)

    def _remove_color(self):
        if self.current_selection_idx < 0: return
        sel_idx = self.lb_colors.curselection()
        if not sel_idx: return
        
        idx = sel_idx[0]
        area = self.areas[self.current_selection_idx]
        colors = area['settings'].get('subtitle_colors', [])
        
        if 0 <= idx < len(colors):
            del colors[idx]
            self._load_details(self.current_selection_idx)

    def _pick_color_screen(self):
        if self.current_selection_idx < 0: return
        self.withdraw()
        self.update()
        import time
        time.sleep(0.2)
        
        try:
            img = capture_fullscreen()
            if not img:
                self.deiconify()
                return
                
            sel = ColorSelector(self.master, img)
            self.wait_window(sel)
            
            if sel.selected_color:
                self._add_color_manual(sel.selected_color)

        except Exception as e:
            print(f"Error picking color: {e}")
        finally:
            self.deiconify()

    def _record_hotkey(self):
        if not keyboard:
            messagebox.showerror("Błąd", "Biblioteka pynput niedostępna.")
            return

        self.btn_record.config(text="Naciśnij klawisz...", state=tk.DISABLED)
        self.update()
        
        def on_press(key):
            try:
                k = f"<{key.name}>"
            except AttributeError:
                k = f"<{key.char}>"
            self.after(0, lambda: self._set_hotkey(k))
            return False 

        listener = keyboard.Listener(on_press=on_press)
        listener.start()
        
    def _set_hotkey(self, key_str):
        if self.current_selection_idx >= 0:
            self.areas[self.current_selection_idx]['hotkey'] = key_str
            self.var_hotkey.set(key_str)
        self.btn_record.config(text="Nagraj", state=tk.NORMAL)

    def _clear_hotkey(self):
        if self.current_selection_idx >= 0:
            self.areas[self.current_selection_idx]['hotkey'] = ""
            self.var_hotkey.set("")

    def _save_and_close(self):
        import copy
        # Ensure data is clean (no Tk vars)
        cleaned = []
        for a in self.areas:
            new_a = {}
            for k, v in a.items():
                if k == 'settings':
                    new_a[k] = copy.deepcopy(v)
                else:
                    new_a[k] = v
            cleaned.append(new_a)
            
        try:
            self.on_save(cleaned)
            self.destroy()
        except Exception as e:
            messagebox.showerror("Błąd zapisu", f"Nie udało się zapisać obszarów: {e}")
            print(f"Save error: {e}")
