import tkinter as tk
from tkinter import ttk, messagebox
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
        self.geometry("600x500")
        self.areas = [a.copy() for a in areas]  # Deep copy-ish (dicts are mutable but we replace lists)
        # Ensure deep copy of nested lists like 'colors'
        for a in self.areas:
            a['colors'] = list(a.get('colors', []))
            
        self.on_save = on_save_callback
        self.current_selection_idx = -1

        self._init_ui()
        self._refresh_list()
        
        # Ensure Area 1 exists
        if not self.areas:
            self._add_default_area()

    def _init_ui(self):
        # Left side: List of areas
        left_frame = ttk.Frame(self, padding=5)
        left_frame.pack(side=tk.LEFT, fill=tk.Y)

        ttk.Label(left_frame, text="Lista Obszarów").pack(anchor=tk.W)
        
        self.lb_areas = tk.Listbox(left_frame, width=20)
        self.lb_areas.pack(fill=tk.Y, expand=True, pady=5)
        self.lb_areas.bind('<<ListboxSelect>>', self._on_list_select)

        btn_frame = ttk.Frame(left_frame)
        btn_frame.pack(fill=tk.X)
        
        ttk.Button(btn_frame, text="+ Dodaj", command=self._add_area).pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.btn_remove = ttk.Button(btn_frame, text="- Usuń", command=self._remove_area, state=tk.DISABLED)
        self.btn_remove.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # Right side: Details
        self.right_frame = ttk.Labelframe(self, text="Szczegóły", padding=10)
        self.right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Content of details (initially hidden/disabled)
        self._init_details_form()

        # Bottom buttons
        bottom_frame = ttk.Frame(self, padding=5)
        bottom_frame.pack(side=tk.BOTTOM, fill=tk.X)
        ttk.Button(bottom_frame, text="Anuluj", command=self.destroy).pack(side=tk.RIGHT, padx=5)
        ttk.Button(bottom_frame, text="Zapisz", command=self._save_and_close).pack(side=tk.RIGHT, padx=5)

    def _init_details_form(self):
        f = self.right_frame
        
        # Area Type
        ttk.Label(f, text="Typ:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.var_type = tk.StringVar()
        # English keys mapping to Polish labels
        self.type_mapping = {"continuous": "Stały", "manual": "Wyzwalany"}
        self.rev_type_mapping = {v: k for k, v in self.type_mapping.items()}
        
        self.cb_type = ttk.Combobox(f, textvariable=self.var_type, values=list(self.type_mapping.values()), state="readonly")
        self.cb_type.grid(row=0, column=1, sticky=tk.EW, pady=5)
        # Bind later to avoid early triggers

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

        # Colors
        ttk.Label(f, text="Kolory:").grid(row=5, column=0, sticky=tk.NW, pady=5)
        self.lb_colors = tk.Listbox(f, height=5)
        self.lb_colors.grid(row=5, column=1, sticky=tk.EW, pady=5)
        
        btn_col_frame = ttk.Frame(f)
        btn_col_frame.grid(row=6, column=0, columnspan=2, sticky=tk.EW)
        ttk.Button(btn_col_frame, text="+ Dodaj Kolor", command=self._add_color).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(btn_col_frame, text="- Usuń", command=self._remove_color).pack(side=tk.LEFT, padx=5)
        
        # Bind events at the end to prevent AttributeError on early trigger
        self.cb_type.bind("<<ComboboxSelected>>", self._on_field_change)

    def _refresh_list(self):
        self.lb_areas.delete(0, tk.END)
        for i, area in enumerate(self.areas):
            typ_raw = area.get('type', 'manual')
            t = "Stały" if typ_raw == 'continuous' else "Wyzwalany"
            if typ_raw not in ['continuous', 'manual']: t = typ_raw # Fallback
            
            display = f"#{area.get('id', i+1)} [{t}]"
            self.lb_areas.insert(tk.END, display)
        
        if self.current_selection_idx >= 0 and self.current_selection_idx < len(self.areas):
            self.lb_areas.selection_set(self.current_selection_idx)
            self._load_details(self.current_selection_idx)
            # Area 1 cannot be removed
            if self.areas[self.current_selection_idx].get('id') == 1:
                self.btn_remove.config(state=tk.DISABLED)
            else:
                self.btn_remove.config(state=tk.NORMAL)
        else:
            self.current_selection_idx = -1
            self._disable_details()

    def _disable_details(self):
        # Clear and disable fields
        self.var_type.set("")
        self.lbl_rect.config(text="-")
        self.var_hotkey.set("")
        self.lb_colors.delete(0, tk.END)
        
        for child in self.right_frame.winfo_children():
            try:
                child.configure(state=tk.DISABLED)
            except: pass

    def _load_details(self, idx):
        area = self.areas[idx]
        
        # Enable all children
        for child in self.right_frame.winfo_children():
            try:
                child.configure(state=tk.NORMAL)
            except: pass
            
        self.entry_hotkey.config(state="readonly") # Keep readonly
        self.cb_type.config(state="readonly")
            
        typ = area.get('type', 'manual')
        display_typ = self.type_mapping.get(typ, typ)
        self.var_type.set(display_typ)
        
        r = area.get('rect', {})
        if r:
            self.lbl_rect.config(text=f"{r.get('left')}x{r.get('top')} ({r.get('width')}x{r.get('height')})")
        else:
            self.lbl_rect.config(text="Brak (cały ekran?)")
            
        self.var_hotkey.set(area.get('hotkey', ''))
        
        self.lb_colors.delete(0, tk.END)
        for c in area.get('colors', []):
            self.lb_colors.insert(tk.END, str(c))
            
        # Area 1 special rules
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
                "colors": []
            })
         self._refresh_list()

    def _add_area(self):
        if len(self.areas) >= 5:
            return
            
        # Determine next ID
        existing_ids = {a.get('id', 0) for a in self.areas}
        next_id = 1
        while next_id in existing_ids:
            next_id += 1
            
        self.areas.append({
            "id": next_id,
            "type": "manual",
            "rect": None,
            "hotkey": "",
            "colors": []
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
        # Update model from vars
        
        # Reverse map UI string to key
        disp_val = self.var_type.get()
        real_val = self.rev_type_mapping.get(disp_val, disp_val)
        
        self.areas[self.current_selection_idx]['type'] = real_val
        self._refresh_list() # To update label

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
                
            sel = ColorSelector(self, img)
            # Waits
            if sel.selected_color:
                # Add if not exists
                current_colors = self.areas[self.current_selection_idx]['colors']
                if sel.selected_color not in current_colors:
                    current_colors.append(sel.selected_color)
                self._load_details(self.current_selection_idx)
        except Exception as e:
            print(f"Error picking color: {e}")
        finally:
            self.deiconify()

    def _remove_color(self):
        sel_idx = self.lb_colors.curselection()
        if not sel_idx: return
        color = self.lb_colors.get(sel_idx[0])
        
        if self.current_selection_idx >= 0:
            current_colors = self.areas[self.current_selection_idx]['colors']
            if color in current_colors:
                current_colors.remove(color)
            self._load_details(self.current_selection_idx)
            
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
