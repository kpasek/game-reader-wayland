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


class AreaSettingsDialog(tk.Toplevel):
    def __init__(self, parent, settings: Dict[str, Any]):
        super().__init__(parent)
        self.title("Ustawienia Obszaru")
        self.geometry("500x550")
        self.settings = settings
        
        # Working Copy variables
        self.colors = list(settings.get('subtitle_colors', []))
        self.var_tolerance = tk.IntVar(value=settings.get('color_tolerance', 10))
        self.var_scale = tk.DoubleVar(value=settings.get('ocr_scale_factor', 1.0))
        self.var_sub_mode = tk.StringVar(value=settings.get('subtitle_mode', 'Full Lines'))
        self.var_text_color_mode = tk.StringVar(value=settings.get('text_color_mode', 'Light'))
        self.var_brightness = tk.IntVar(value=settings.get('brightness_threshold', 200))
        self.var_contrast = tk.DoubleVar(value=settings.get('contrast', 0.0))
        self.var_thickening = tk.IntVar(value=settings.get('text_thickening', 0))

        self.changed = False
        self._init_ui()

    def _init_ui(self):
        main = ttk.Frame(self, padding=15)
        main.pack(fill=tk.BOTH, expand=True)

        # --- Colors Section ---
        lf_colors = ttk.Labelframe(main, text="Kolory Napisów", padding=10)
        lf_colors.pack(fill=tk.X, pady=5)
        
        row_c = ttk.Frame(lf_colors)
        row_c.pack(fill=tk.X)
        
        self.lb_colors = tk.Listbox(row_c, height=5, width=20)
        self.lb_colors.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        btn_box = ttk.Frame(row_c)
        btn_box.pack(side=tk.LEFT, fill=tk.Y, padx=5)
        
        ttk.Button(btn_box, text="Pobierz z Ekranu", command=self._pick_color_screen).pack(fill=tk.X, pady=2)
        ttk.Button(btn_box, text="Dodaj Biały", command=lambda: self._add_color_manual("#FFFFFF")).pack(fill=tk.X, pady=2)
        ttk.Button(btn_box, text="Usuń", command=self._remove_color).pack(fill=tk.X, pady=2)

        ttk.Label(lf_colors, text="Tolerancja koloru:").pack(anchor=tk.W, pady=(10, 0))
        xc = ttk.Frame(lf_colors)
        xc.pack(fill=tk.X)
        ttk.Scale(xc, from_=0, to=100, variable=self.var_tolerance, orient=tk.HORIZONTAL).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Label(xc, textvariable=self.var_tolerance, width=4).pack(side=tk.LEFT)

        self._refresh_color_list()

        # --- Parameters Section ---
        lf_params = ttk.Labelframe(main, text="Parametry OCR i Obrazu", padding=10)
        lf_params.pack(fill=tk.BOTH, expand=True, pady=10)
        
        grid = ttk.Frame(lf_params)
        grid.pack(fill=tk.X)
        grid.columnconfigure(1, weight=1)

        # Helper for grid rows
        r = 0
        def add_param(label, widget):
            nonlocal r
            ttk.Label(grid, text=label).grid(row=r, column=0, sticky=tk.W, pady=5, padx=5)
            widget.grid(row=r, column=1, sticky=tk.EW, pady=5, padx=5)
            r += 1

        # Scale
        s_scale = tk.Spinbox(grid, from_=0.5, to=5.0, increment=0.25, textvariable=self.var_scale)
        add_param("Skala OCR:", s_scale)
        
        # Mode
        cb_mode = ttk.Combobox(grid, textvariable=self.var_sub_mode, values=["Full Lines", "Partial"], state="readonly")
        add_param("Tryb dopasowania:", cb_mode)

        # Text Color Mode
        cb_tcm = ttk.Combobox(grid, textvariable=self.var_text_color_mode, values=["Light", "Dark", "Mixed"], state="readonly")
        add_param("Kolor tekstu:", cb_tcm)
        
        # Brightness
        f_br = ttk.Frame(grid)
        ttk.Scale(f_br, from_=0, to=255, variable=self.var_brightness, orient=tk.HORIZONTAL).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Label(f_br, textvariable=self.var_brightness, width=4).pack(side=tk.LEFT)
        add_param("Próg jasności:", f_br)
        
        # Contrast
        f_co = ttk.Frame(grid)
        ttk.Scale(f_co, from_=0.0, to=5.0, variable=self.var_contrast, orient=tk.HORIZONTAL).pack(side=tk.LEFT, fill=tk.X, expand=True)
        # Hack to show float with limited precision
        lbl_cont = ttk.Label(f_co, text="0.0")
        def update_lbl(*args): lbl_cont.config(text=f"{self.var_contrast.get():.1f}")
        self.var_contrast.trace_add("write", update_lbl)
        update_lbl()
        lbl_cont.pack(side=tk.LEFT)
        add_param("Kontrast:", f_co)

        # Thickening
        s_thick = tk.Spinbox(grid, from_=0, to=5, textvariable=self.var_thickening)
        add_param("Pogrubienie:", s_thick)

        # --- Buttons ---
        btn_row = ttk.Frame(self, padding=10)
        btn_row.pack(side=tk.BOTTOM, fill=tk.X)
        ttk.Button(btn_row, text="Zapisz", command=self._save).pack(side=tk.RIGHT, padx=5)
        ttk.Button(btn_row, text="Anuluj", command=self.destroy).pack(side=tk.RIGHT)

    def _refresh_color_list(self):
        self.lb_colors.delete(0, tk.END)
        for c in self.colors:
            self.lb_colors.insert(tk.END, c)

    def _add_color_manual(self, color):
        if color not in self.colors:
            self.colors.append(color)
            self._refresh_color_list()

    def _remove_color(self):
        sel = self.lb_colors.curselection()
        if not sel: return
        idx = sel[0]
        del self.colors[idx]
        self._refresh_color_list()

    def _pick_color_screen(self):
        self.withdraw()
        # Need capture logic similar to AreaSelector
        # For simplicity, reuse logic or implement simplified
        try:
             time.sleep(0.2)
             img = capture_fullscreen()
             if not img: 
                 self.deiconify()
                 return
             
             sel = ColorSelector(self, img)
             self.wait_window(sel)
             
             if sel.selected_color:
                 self._add_color_manual(sel.selected_color)
                 
        except Exception as e:
            print(e)
            
        self.deiconify()

    def _save(self):
        self.settings['subtitle_colors'] = self.colors
        self.settings['color_tolerance'] = self.var_tolerance.get()
        self.settings['ocr_scale_factor'] = self.var_scale.get()
        self.settings['subtitle_mode'] = self.var_sub_mode.get()
        self.settings['text_color_mode'] = self.var_text_color_mode.get()
        self.settings['brightness_threshold'] = self.var_brightness.get()
        self.settings['contrast'] = self.var_contrast.get()
        self.settings['text_thickening'] = self.var_thickening.get()
        self.changed = True
        self.destroy()


import time

class AreaManagerWindow(tk.Toplevel):
    def __init__(self, parent, areas: List[Dict[str, Any]], on_save_callback):
        super().__init__(parent)
        self.title("Zarządzanie Obszarami")
        self.geometry("1000x600")
        self.areas = [a.copy() for a in areas]
        
        # Migration: Move top-level colors provided by legacy code to settings
        # Also ensure 'settings' dict exists
        for a in self.areas:
            if 'settings' not in a:
                a['settings'] = {}
            
            # Migrate legacy colors
            if 'colors' in a and a['colors']:
                if 'subtitle_colors' not in a['settings']:
                    a['settings']['subtitle_colors'] = list(a['colors'])
                del a['colors']
                
            # Ensure safe defaults if missing in settings
            # We don't force them here to allow global defaults, but for UI we might needed defaults?
            # area_ctx logic handles merging, so empty is fine.

        self.on_save = on_save_callback
        self.current_selection_idx = -1

        self._init_ui()
        self._refresh_list()
        
        if not self.areas:
            self._add_default_area()

    def _init_ui(self):
        # Left side: List of areas
        left_frame = ttk.Frame(self, padding=5)
        left_frame.pack(side=tk.LEFT, fill=tk.Y)

        ttk.Label(left_frame, text="Lista Obszarów").pack(anchor=tk.W)
        
        self.lb_areas = tk.Listbox(left_frame, width=25)
        self.lb_areas.pack(fill=tk.BOTH, expand=True, pady=5)
        self.lb_areas.bind('<<ListboxSelect>>', self._on_list_select)

        btn_frame = ttk.Frame(left_frame)
        btn_frame.pack(fill=tk.X)
        
        ttk.Button(btn_frame, text="+ Dodaj", command=self._add_area).pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.btn_remove = ttk.Button(btn_frame, text="- Usuń", command=self._remove_area, state=tk.DISABLED)
        self.btn_remove.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.btn_toggle = ttk.Button(btn_frame, text="Włącz/Wyłącz", command=self._toggle_area_enabled, state=tk.DISABLED, width=15)
        self.btn_toggle.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # Main Actions
        action_frame = ttk.Frame(left_frame, padding=(0, 20, 0, 0))
        action_frame.pack(fill=tk.X, side=tk.BOTTOM)
        
        ttk.Button(action_frame, text="Zapisz", command=self._save_and_close).pack(fill=tk.X, pady=2)
        ttk.Button(action_frame, text="Anuluj", command=self.destroy).pack(fill=tk.X, pady=2)

        # Right side: Details
        self.right_frame = ttk.Labelframe(self, text="Szczegóły", padding=10)
        self.right_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)

        self._init_details_form()

    def _init_details_form(self):
        f = self.right_frame
        f.columnconfigure(1, weight=1)
        
        # Area Type
        ttk.Label(f, text="Typ:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.var_type = tk.StringVar()
        self.type_mapping = {"continuous": "Stały", "manual": "Wyzwalany"}
        self.rev_type_mapping = {v: k for k, v in self.type_mapping.items()}
        
        self.cb_type = ttk.Combobox(f, textvariable=self.var_type, values=list(self.type_mapping.values()), state="readonly")
        self.cb_type.grid(row=0, column=1, sticky=tk.EW, pady=5)

        # Bounds
        ttk.Label(f, text="Współrzędne:").grid(row=1, column=0, sticky=tk.W, pady=5)
        self.lbl_rect = ttk.Label(f, text="-")
        self.lbl_rect.grid(row=1, column=1, sticky=tk.W, pady=5)
        
        ttk.Button(f, text="Wybierz Obszar", command=self._select_area_on_screen).grid(row=2, column=0, columnspan=2, sticky=tk.EW, pady=5)

        # Hotkey
        ttk.Label(f, text="Skrót:").grid(row=3, column=0, sticky=tk.W, pady=5)
        self.var_hotkey = tk.StringVar()
        self.entry_hotkey = ttk.Entry(f, textvariable=self.var_hotkey, state="readonly")
        self.entry_hotkey.grid(row=3, column=1, sticky=tk.EW, pady=5)
        
        btn_hk_frame = ttk.Frame(f)
        btn_hk_frame.grid(row=4, column=0, columnspan=2, sticky=tk.EW)
        self.btn_record = ttk.Button(btn_hk_frame, text="Nagraj Skrót", command=self._record_hotkey)
        self.btn_record.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(btn_hk_frame, text="Wyczyść", command=self._clear_hotkey).pack(side=tk.LEFT, padx=5)

        # Colors Preview (Read Only)
        ttk.Label(f, text="Kolory:").grid(row=5, column=0, sticky=tk.NW, pady=5)
        self.cv_colors = tk.Canvas(f, height=30, bg="#f0f0f0", highlightthickness=0)
        self.cv_colors.grid(row=5, column=1, sticky=tk.EW, pady=5)
        
        # Settings Button
        ttk.Separator(f, orient=tk.HORIZONTAL).grid(row=6, column=0, columnspan=2, sticky=tk.EW, pady=15)
        self.btn_settings = ttk.Button(f, text="Edytuj Ustawienia Obszaru...", command=self._open_settings_dialog)
        self.btn_settings.grid(row=7, column=0, columnspan=2, sticky=tk.EW, pady=5)

        self.cb_type.bind("<<ComboboxSelected>>", self._on_field_change)

    def _open_settings_dialog(self):
        if self.current_selection_idx < 0: return
        area = self.areas[self.current_selection_idx]
        if 'settings' not in area: area['settings'] = {}
        
        dlg = AreaSettingsDialog(self, area['settings'])
        self.wait_window(dlg)
        
        if dlg.changed:
            self._load_details(self.current_selection_idx) # Refresh UI

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
            is_area1 = area.get('id') == 1
            is_cont = area.get('type', 'manual') == 'continuous'

            if is_area1:
                self.btn_remove.config(state=tk.DISABLED)
                self.btn_toggle.config(state=tk.DISABLED)
            else:
                self.btn_remove.config(state=tk.NORMAL)
                if is_cont:
                    self.btn_toggle.config(state=tk.NORMAL)
                    txt = "Wyłącz" if area.get('enabled', False) else "Włącz"
                    self.btn_toggle.config(text=txt)
                else:
                    self.btn_toggle.config(state=tk.DISABLED)
                    self.btn_toggle.config(text="Włącz/Wyłącz")
        else:
            self.current_selection_idx = -1
            self._disable_details()

    def _toggle_area_enabled(self):
        if self.current_selection_idx < 0: return
        area = self.areas[self.current_selection_idx]
        if area.get('type') != 'continuous' or area.get('id') == 1:
            return
        
        curr = area.get('enabled', False)
        area['enabled'] = not curr
        self._refresh_list()

    def _disable_details(self):
        self.var_type.set("")
        self.lbl_rect.config(text="-")
        self.var_hotkey.set("")
        self.cv_colors.delete("all")
        
        for child in self.right_frame.winfo_children():
            try:
                child.configure(state=tk.DISABLED)
            except: pass

    def _load_details(self, idx):
        area = self.areas[idx]
        
        for child in self.right_frame.winfo_children():
            try:
                child.configure(state=tk.NORMAL)
            except: pass
            
        self.entry_hotkey.config(state="readonly")
        self.cb_type.config(state="readonly")
            
        typ = area.get('type', 'manual')
        display_typ = self.type_mapping.get(typ, typ)
        self.var_type.set(display_typ)
        
        if area.get('id') == 1:
            self.entry_hotkey.config(state=tk.DISABLED)
            self.btn_record.config(state=tk.DISABLED)
        else:
            self.entry_hotkey.config(state="readonly")
            self.btn_record.config(state=tk.NORMAL)
        
        r = area.get('rect', {})
        if r:
            self.lbl_rect.config(text=f"{r.get('left')}x{r.get('top')} ({r.get('width')}x{r.get('height')})")
        else:
            self.lbl_rect.config(text="Brak")
            
        self.var_hotkey.set(area.get('hotkey', ''))
        
        # Colors Preview
        self.cv_colors.delete("all")
        x_off = 5
        y_off = 5
        size = 20
        
        settings = area.get('settings', {})
        colors = settings.get('subtitle_colors', [])
        
        if not colors:
             self.cv_colors.create_text(5, 15, text="(Domyślne/Brak)", anchor=tk.W, fill="gray")
        else:
            for c in colors:
                try:
                    self.cv_colors.create_rectangle(x_off, y_off, x_off+size, y_off+size, 
                                                    fill=c, outline="black")
                    x_off += size + 5
                except: pass
            
        if area.get('id') == 1:
            self.cb_type.config(state=tk.DISABLED) 
        else:
            self.cb_type.config(state="readonly")

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

    def _add_area(self):
        if len(self.areas) >= 5:
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
        self.current_selection_idx = -1
        self._refresh_list()

    def _on_field_change(self, event=None):
        if self.current_selection_idx < 0: return
        disp_val = self.var_type.get()
        real_val = self.rev_type_mapping.get(disp_val, disp_val)
        self.areas[self.current_selection_idx]['type'] = real_val
        self._refresh_list() 

        
        # Update UI state
        if real_val == 'continuous':
            self.entry_hotkey.config(state=tk.DISABLED)
            self.btn_record.config(state=tk.DISABLED)
            # Clear hotkey if switching to continuous? Optional
        else:
            self.entry_hotkey.config(state="readonly")
            self.btn_record.config(state=tk.NORMAL)

    def _select_area_on_screen(self):
        if self.current_selection_idx < 0: return
        self.withdraw()
        # Sleep a bit to allow window to minimize
        self.update() 
        import time
        time.sleep(0.3)
        
        try:
            img = capture_fullscreen()
            if not img:
                self.deiconify()
                return
            
            # Use self.master as parent for AreaSelector since self is hidden
            # Actually, standard Toplevel with parent hidden might also be hidden. 
            # We can use root window (self.master) which should be visible or deiconifiable?
            # Wait, LektorApp root might be visible.
            # However, AreaSelector needs to be fullscreen on top.
            
            # Let's try passing the grand-parent (if self.master is Toplevel or Root)
            # self.master should be valid Tk instance.
            
            # Pass full area objects for context view
            sel = AreaSelector(self.master, img, existing_regions=self.areas) 
            # AreaSelector waits for window.
            if sel.geometry:
                self.areas[self.current_selection_idx]['rect'] = sel.geometry
                self._load_details(self.current_selection_idx)
                self._refresh_list() # refresh potential changes

        except Exception as e:
            print(f"Error selecting area: {e}")
        finally:
            self.deiconify()

    def _add_color(self):
        if self.current_selection_idx < 0: return
        self.withdraw()
        # Sleep
        self.update()
        import time
        time.sleep(0.2)
        
        try:
            img = capture_fullscreen()
            if not img:
                self.deiconify()
                return
                
            sel = ColorSelector(self.master, img) # Use master (root) to ensure visibility
            # Waits
            if sel.selected_color:
                # Add if not exists (case insensitive check)
                new_col = sel.selected_color
                current_colors = self.areas[self.current_selection_idx].setdefault('colors', [])
                
                exists = False
                for c in current_colors:
                    if c.lower() == new_col.lower():
                        exists = True
                        break
                
                if not exists:
                    current_colors.append(new_col)
                self._load_details(self.current_selection_idx)
        except Exception as e:
            print(f"Error picking color: {e}")
        finally:
            self.deiconify()

    def _add_white_color(self):
        if self.current_selection_idx < 0: return
        
        current_colors = self.areas[self.current_selection_idx].setdefault('colors', [])
        white = '#ffffff'
        
        exists = False
        for c in current_colors:
            if c.lower() == white.lower():
                exists = True
                break
                
        if not exists:
            current_colors.append(white)
        self._load_details(self.current_selection_idx)

    def _on_color_click(self, event):
        if self.current_selection_idx < 0: return
        
        # Wykrywaj tylko elementy dokładnie pod kursorem
        items = self.cv_colors.find_overlapping(event.x, event.y, event.x+1, event.y+1)
        item = None
        for i in reversed(items):
            tags = self.cv_colors.gettags(i)
            if "clickable" in tags:
                item = i
                break
        
        if item is None:
            return

        tags = self.cv_colors.gettags(item)
        
        idx_to_remove = -1
        for t in tags:
            if t.startswith("col_"):
                try:
                    idx_to_remove = int(t.split("_")[1])
                except: pass
                break
                
        if idx_to_remove == -1: return
        
        current_colors = self.areas[self.current_selection_idx].get('colors', [])
        if idx_to_remove < len(current_colors):
            c = current_colors[idx_to_remove]
            if messagebox.askyesno("Usuń Kolor", f"Czy usunąć kolor {c}?", parent=self):
                del current_colors[idx_to_remove]
                self._load_details(self.current_selection_idx)
    
    def _on_color_hover(self, event):
        items = self.cv_colors.find_overlapping(event.x, event.y, event.x+1, event.y+1)
        is_clickable = False
        for i in items:
            if "clickable" in self.cv_colors.gettags(i):
                is_clickable = True
                break
                
        if is_clickable:
            self.cv_colors.config(cursor="hand2")
        else:
            self.cv_colors.config(cursor="")

    def _record_hotkey(self):
        if not keyboard:
            messagebox.showerror("Błąd", "Biblioteka pynput niedostępna.")
            return

        self.btn_record.config(text="Naciśnij klawisz...", state=tk.DISABLED)
        self.update()
        
        # Simple listener for one key
        def on_press(key):
            try:
                k = f"<{key.name}>"
            except AttributeError:
                k = f"<{key.char}>"
                
            # Normalize common keys
            # Lektor uses <f3>, <ctrl>, etc.
            self.after(0, lambda: self._set_hotkey(k))
            return False # Stop listener

        listener = keyboard.Listener(on_press=on_press)
        listener.start()
        
    def _set_hotkey(self, key_str):
        if self.current_selection_idx >= 0:
            self.areas[self.current_selection_idx]['hotkey'] = key_str
            self.var_hotkey.set(key_str)
        self.btn_record.config(text="Nagraj Skrót", state=tk.NORMAL)

    def _clear_hotkey(self):
        if self.current_selection_idx >= 0:
            self.areas[self.current_selection_idx]['hotkey'] = ""
            self.var_hotkey.set("")

    def _save_and_close(self):
        # Notify parent
        self.on_save(self.areas)
        self.destroy()
