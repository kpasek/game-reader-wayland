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
from app.optimizer import SettingsOptimizer
from app import scale_utils
from app.matcher import precompute_subtitles, MATCH_MODE_FULL, MATCH_MODE_STARTS, MATCH_MODE_PARTIAL
from app.ocr import find_text_bounds
from app.geometry_utils import calculate_merged_area

class AreaManagerWindow(tk.Toplevel):
    def _refresh_list(self):
        self.lb_areas.delete(0, tk.END)
        for i, area in enumerate(self.areas):
            typ_raw = area.get('type', 'manual')
            t = "Stały" if typ_raw == 'continuous' else "Wyzwalany"
            if typ_raw not in ['continuous', 'manual']:
                t = typ_raw
            display = f"#{area.get('id', i+1)}"
            if area.get('name'):
                display += f" {area.get('name')}"
            display += f" [{t}]"
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
    def __init__(self, parent, areas: List[Dict[str, Any]], on_save_callback, subtitle_lines: List[str] = None):
        super().__init__(parent)
        self.title("Zarządzanie Obszarami")
        self.geometry("900x600")
        self.areas = [a.copy() for a in areas]
        self.subtitle_lines = subtitle_lines
        
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
        self.lb_areas.bind('<Double-Button-1>', self._rename_area_dialog)
        
        self.context_menu = tk.Menu(self.lb_areas, tearoff=0)
        self.context_menu.add_command(label="Kreator Optymalizacji...", command=self._open_optimizer)
        self.lb_areas.bind("<Button-3>", self._show_context_menu)

        btn_frame = ttk.Frame(left_frame)
        btn_frame.pack(fill=tk.X)
        ttk.Button(btn_frame, text="+ Dodaj", command=self._add_area).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(btn_frame, text="Duplikuj", command=self._duplicate_area).pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.btn_remove = ttk.Button(btn_frame, text="- Usuń", command=self._remove_area, state=tk.DISABLED)
        self.btn_remove.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        # Save / Close
        action_frame = ttk.Frame(left_frame, padding=(0, 20, 0, 0))
        action_frame.pack(fill=tk.X, side=tk.BOTTOM)
        ttk.Button(action_frame, text="Zapisz i Zamknij", command=self._save_and_close).pack(fill=tk.X, pady=5)
        
        # Test Button
        self.btn_test = ttk.Button(action_frame, text="🧪 Testuj ustawienia", command=self._test_current_settings)
        self.btn_test.pack(fill=tk.X, pady=5)
        
        ttk.Button(action_frame, text="Anuluj", command=self.destroy).pack(fill=tk.X)

        # Right side: Full Editor (Notebook)
        self.right_frame = ttk.Frame(self, padding=10)
        self.right_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        self.notebook = ttk.Notebook(self.right_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True)
        
        # Tab 1: Ogólne (Type, Rect, Hotkey + OCR)
        self.tab_general = ttk.Frame(self.notebook, padding=15)
        self.notebook.add(self.tab_general, text="Ogólne")
        self._init_tab_general(self.tab_general)
        
        # Tab 2: Kolory (Colors List)
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
        ttk.Button(f_rect, text="Ręcznie zaznacz obszar", command=self._select_area_on_screen).pack(anchor=tk.W, pady=5)
        
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

        # OCR Settings
        ttk.Separator(parent, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=15)
        ttk.Label(parent, text="Ustawienia Obrazu i OCR:", font=("Arial", 10, "bold")).pack(anchor=tk.W, pady=(0, 10))

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
        from app.matcher import MATCH_MODE_FULL, MATCH_MODE_STARTS, MATCH_MODE_PARTIAL
        self.mode_mapping = {
            MATCH_MODE_FULL: "Pełne linie", 
            MATCH_MODE_STARTS: "Zaczyna się na",
            MATCH_MODE_PARTIAL: "Częściowe"
        }
        self.rev_mode_mapping = {v: k for k, v in self.mode_mapping.items()}
        cb_mode = ttk.Combobox(pl, textvariable=self.var_mode, values=list(self.mode_mapping.values()), state="readonly")
        cb_mode.bind("<<ComboboxSelected>>", self._on_field_change)
        add_row("Tryb dopasowania:", cb_mode)
        
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
        self.chk_use_colors = ttk.Checkbutton(parent, text="Używaj filtrowania kolorów", variable=self.var_use_colors, command=self._on_field_change)
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
        def on_tol_change(v):
            self.var_tolerance.set(int(float(v)))
            self._on_field_change()
        ttk.Scale(f_tol, from_=0, to=100, variable=self.var_tolerance, orient=tk.HORIZONTAL, command=on_tol_change).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Label(f_tol, textvariable=self.var_tolerance).pack(side=tk.LEFT, padx=5)

    def _load_details(self, idx):
        import traceback
        print(f"[AreaManager][LOG] _load_details(idx={idx}) called. Stack:")
        traceback.print_stack(limit=4)
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
        print(f"[AreaManager][LOG] _load_details: area['rect'] type={type(r)}, value={r}")
        if r:
            # Convert canonical 4K rect to current screen pixels for display
            screen_w = self.winfo_screenwidth()
            screen_h = self.winfo_screenheight()
            try:
                srect = scale_utils.scale_rect_to_physical(r, screen_w, screen_h)
                print(f"[AreaManager][LOG] _load_details: screen_w={screen_w}, screen_h={screen_h}")
                print(f"[AreaManager][LOG] _load_details: rect 4K->screen: {srect}")
                self.lbl_rect.config(text=f"X:{srect['left']} Y:{srect['top']} {srect['width']}x{srect['height']}")
            except Exception:
                self.lbl_rect.config(text="Błąd przeliczenia obszaru")
        else:
            print(f"[AreaManager][LOG] _load_details: area['rect'] is None")
            self.lbl_rect.config(text="Brak (Kliknij 'Wybierz Obszar')")
            
        self.var_hotkey.set(area.get('hotkey', ''))
        
        # Tab OCR
        self.var_thickening.set(settings.get('text_thickening', 0))
        
        from app.matcher import MATCH_MODE_FULL
        mode_val = settings.get('subtitle_mode', MATCH_MODE_FULL)
        self.var_mode.set(self.mode_mapping.get(mode_val, mode_val))
        
        # Removed var_cmode logic
        self.var_brightness.set(settings.get('brightness_threshold', 200))
        self.var_contrast.set(settings.get('contrast', 0.0))
        
        # Tab Colors
        self.var_use_colors.set(settings.get('use_colors', True))
        self.var_tolerance.set(settings.get('color_tolerance', 10))
        
        self.lb_colors.delete(0, tk.END)
        for c in settings.get('subtitle_colors', []):
            self.lb_colors.insert(tk.END, c)
            
        self.ignore_updates = False
        
        for tab in [self.tab_general, self.tab_colors]:
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
        
        s['text_thickening'] = self.var_thickening.get()
        
        disp_mode = self.var_mode.get()
        s['subtitle_mode'] = self.rev_mode_mapping.get(disp_mode, disp_mode)
        
        # s['text_color_mode'] removed
        s['brightness_threshold'] = self.var_brightness.get()
        s['contrast'] = self.var_contrast.get()
        s['use_colors'] = self.var_use_colors.get()
        s['color_tolerance'] = self.var_tolerance.get()
        # Zapisz tryb dopasowania do settings
        if self.var_mode.get() in self.rev_mode_mapping:
            s['subtitle_mode'] = self.rev_mode_mapping[self.var_mode.get()]
        
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

    def _select_area_on_screen(self):
        from tkinter import filedialog
        from PIL import Image

        # Custom large import dialog (shows files from user's home)
        home = os.path.expanduser('~')
        files = []
        try:
            for f in sorted(os.listdir(home)):
                if f.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp')):
                    files.append(os.path.join(home, f))
        except Exception:
            files = []

        selected_paths = []

        dlg = tk.Toplevel(self)
        dlg.title("Import zrzutów - wybierz pliki")
        dlg.geometry("900x600")
        dlg.transient(self)
        dlg.grab_set()

        frm = ttk.Frame(dlg, padding=10)
        frm.pack(fill=tk.BOTH, expand=True)

        lb = tk.Listbox(frm, selectmode=tk.EXTENDED)
        lb.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        for p in files:
            lb.insert(tk.END, os.path.basename(p))

        scr = ttk.Scrollbar(frm, orient=tk.VERTICAL, command=lb.yview)
        scr.pack(side=tk.LEFT, fill=tk.Y)
        lb.config(yscrollcommand=scr.set)

        right = ttk.Frame(frm)
        right.pack(side=tk.LEFT, fill=tk.Y, padx=8)

        preview_lab = ttk.Label(right, text="Brak podglądu", width=40)
        preview_lab.pack(pady=4)

        def on_preview(evt=None):
            sel = lb.curselection()
            if not sel:
                preview_lab.config(text="Brak podglądu")
                return
            idx = sel[0]
            preview_lab.config(text=os.path.basename(files[idx]))

        lb.bind('<<ListboxSelect>>', on_preview)

        btns = ttk.Frame(dlg, padding=8)
        btns.pack(fill=tk.X)
        def do_ok():
            for i in lb.curselection():
                selected_paths.append(files[i])
            dlg.destroy()
        def do_cancel():
            dlg.destroy()

        ttk.Button(btns, text="Importuj wybrane", command=do_ok).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Anuluj", command=do_cancel).pack(side=tk.LEFT, padx=4)

        self.wait_window(dlg)

        paths = selected_paths
        if not paths:
            return

        # Hide window once for all imports
        root = self._get_root()
        self.withdraw()
        if self.area_manager: self.area_manager.withdraw()
        self.update_idletasks()

        try:
            for path in paths:
                try:
                    # 1. Wczytaj obraz
                    pil_img = Image.open(path).convert('RGB')
                    w, h = pil_img.size
                    target_res = (w, h)

                    # 2. Selekcja obszaru na zaimportowanym obrazie
                    # AreaSelector otworzy się na pełny ekran z tym obrazem jako tło
                    sel = AreaSelector(root, pil_img) # Blokuje aż do zamknięcia

                    if sel.geometry:
                        r = sel.geometry
                        rect_tuple = (r['left'], r['top'], r['width'], r['height'])

                        self.frames.append({"image": pil_img, "rect": rect_tuple})

                        # Formatting info for listbox
                        info = f"Import ({target_res[0]}x{target_res[1]}) - Obszar: {rect_tuple}"
                        self.lb_screens.insert(tk.END, info)
                except Exception as ex:
                    print(f"Błąd importu pliku {path}: {ex}")
                    # Continue to next file
                    pass
        except Exception as e:
            messagebox.showerror("Błąd", f"Błąd importu: {e}")
        finally:
            self.deiconify()
            if self.area_manager: self.area_manager.deiconify()
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

    def _rename_area_dialog(self, event=None):
        sel = self.lb_areas.curselection()
        if sel:
             self.current_selection_idx = sel[0]
        
        if self.current_selection_idx < 0 or self.current_selection_idx >= len(self.areas):
            return

        area = self.areas[self.current_selection_idx]
        from tkinter import simpledialog
        name = simpledialog.askstring("Nazwa obszaru", f"Podaj nazwę dla obszaru #{area.get('id')}:", initialvalue=area.get('name', ''), parent=self)
        if name is not None:
             area['name'] = name.strip()
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

    def _add_area(self):
        # Create and select a new manual area
        existing_ids = [a.get('id', 0) for a in self.areas]
        new_id = (max(existing_ids) if existing_ids else 0) + 1
        new_area = {
            "id": new_id,
            "type": "manual",
            "rect": None,
            "hotkey": "",
            "settings": {}
        }
        self.areas.append(new_area)
        self.current_selection_idx = len(self.areas) - 1
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
            # Przekazuj tylko listę dictów {'rect': ...} (bez id, type, settings)
            screen_w = self.winfo_screenwidth()
            screen_h = self.winfo_screenheight()
            regions_screen = []
            for idx, area in enumerate(self.areas):
                r = area.get('rect')
                if not r:
                    continue
                try:
                    box = scale_utils.scale_rect_to_physical(r, screen_w, screen_h)
                except Exception:
                    box = {'left': 0, 'top': 0, 'width': 0, 'height': 0}
                print(f"[AreaManager] Przeliczony rect #{idx} z 4K na ekran: {box}, screen_w={screen_w}, screen_h={screen_h}")
                if box['left'] < 0 or box['top'] < 0 or box['left'] + box['width'] > screen_w or box['top'] + box['height'] > screen_h:
                    print(f"[AreaManager][WARN] Rect #{idx} wykracza poza ekran: {box}, screen_w={screen_w}, screen_h={screen_h}")
                regions_screen.append({'rect': box})
            print(f"[AreaManager] Przekazuję existing_regions do AreaSelector (ekran, tylko rect): {[r['rect'] for r in regions_screen]}")
            root = self._get_root()
            sel = AreaSelector(root, img, existing_regions=[r['rect'] for r in regions_screen])
            # AreaSelector is blocking in init, so no need to wait here.
            if sel.geometry:
                print(f"[AreaManager] Otrzymana geometria z AreaSelector (ekran): {sel.geometry}")
                # Przelicz z powrotem do 4K przed zapisem
                try:
                    rect_4k = scale_utils.scale_rect_to_4k(sel.geometry, screen_w, screen_h)
                except Exception:
                    left_4k = int(round(sel.geometry['left'] * 3840 / screen_w))
                    top_4k = int(round(sel.geometry['top'] * 2160 / screen_h))
                    width_4k = int(round(sel.geometry['width'] * 3840 / screen_w))
                    height_4k = int(round(sel.geometry['height'] * 2160 / screen_h))
                    rect_4k = {'left': left_4k, 'top': top_4k, 'width': width_4k, 'height': height_4k}

                print(f"[AreaManager] Przeliczam do 4K przed zapisem: {rect_4k} (z ekranu: {sel.geometry}, ekran: {screen_w}x{screen_h})")
                print(f"[AreaManager] Area przed aktualizacją: {self.areas[self.current_selection_idx]}")
                self.areas[self.current_selection_idx]['rect'] = rect_4k
                print(f"[AreaManager] Area po aktualizacji: {self.areas[self.current_selection_idx]}")
                self._load_details(self.current_selection_idx)
                # Auto update bounds label
                r = rect_4k
                self.lbl_rect.config(text=f"X:{r.get('left')} Y:{r.get('top')} {r.get('width')}x{r.get('height')}")
        except Exception as e:
            print(f"Error selecting area: {e}")
        finally:
            self.deiconify()

    def _get_root(self):
        w = self
        while w.master:
             w = w.master
        return w

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
            
            # Use root as parent
            root = self._get_root()
            sel = ColorSelector(root, img)
            # wColorSelector is also blocking in init
            
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

    def _duplicate_area(self):
        if self.current_selection_idx < 0: return
        area_copy = self.areas[self.current_selection_idx].copy()
        
        # New Unique Name
        max_id = max((a.get('id', 0) for a in self.areas), default=0)
        area_copy['id'] = max_id + 1
        
        if 'settings' in area_copy:
             area_copy['settings'] = area_copy['settings'].copy()
             if 'subtitle_colors' in area_copy['settings']:
                 area_copy['settings']['subtitle_colors'] = list(area_copy['settings']['subtitle_colors'])
        if 'rect' in area_copy:
             area_copy['rect'] = area_copy['rect'].copy()
             
        self.areas.append(area_copy)
        self._refresh_list()
        self.lb_areas.selection_clear(0, tk.END)
        self.lb_areas.selection_set(tk.END)
        self.current_selection_idx = len(self.areas) - 1
        self._load_details(self.current_selection_idx)

    def _test_current_settings(self):
        if self.current_selection_idx < 0: return
        if not self.subtitle_lines:
             messagebox.showerror("Błąd", "Brak załadowanych napisów (plik tekstowy).")
             return
             
        area = self.areas[self.current_selection_idx]
        rect = area.get('rect')
        if not rect:
             messagebox.showerror("Błąd", "Obszar nie ma zdefiniowanych współrzędnych.")
             return
             
        # Hide and capture
        self.withdraw()
        self.update()
        import time
        time.sleep(0.3)
        
        try:
             full_img = capture_fullscreen()
             if not full_img:
                 self.deiconify()
                 return
             img_w, img_h = full_img.size

             # rect in storage is canonical 4K — convert to physical/image coords before cropping
             try:
                 srect = scale_utils.scale_rect_to_physical(rect, img_w, img_h)
             except Exception:
                 srect = rect.copy()

             ox = srect['left']; oy = srect['top']
             ow = srect['width']; oh = srect['height']
             
             # Calculate expanded rect (20% padding)
             # Clamp padding to image bounds
             # Actually, expand by 20% of width/height
             x_pad = int(ow * 0.2)
             y_pad = int(oh * 0.2)
             
             ex = max(0, ox - x_pad)
             ey = max(0, oy - y_pad)
             ew = min(img_w - ex, ow + 2 * x_pad)
             eh = min(img_h - ey, oh + 2 * y_pad)
             
             # Crops
             normal_crop = full_img.crop((ox, oy, ox+ow, oy+oh))
             expanded_crop = full_img.crop((ex, ey, ex+ew, ey+eh))
             
             # Evaluate original
             settings = area.get('settings', {})
             pre_db = precompute_subtitles(self.subtitle_lines)
             optimizer = SettingsOptimizer()
             from app.matcher import MATCH_MODE_FULL
             mode = settings.get('subtitle_mode', MATCH_MODE_FULL)
             
             score_original, _ = optimizer._evaluate_settings(normal_crop, settings, pre_db, mode)
             
             # Evaluate expanded
             # We use the SAME settings on expanded crop to see if we missed text
             score_expanded, _ = optimizer._evaluate_settings(expanded_crop, settings, pre_db, mode)
             
             # Logic: If expanded score is significantly better OR (if both are good, check bounds)
             # Actually, if we expand, we might catch garbage which lowers score.
             # But if we catch the FULL text which was cut off, score should improve.
             
             final_score = score_original
             expanded_better = False
             
             if score_expanded > score_original + 5: # Threshold for "better"
                 expanded_better = True
                 final_score = score_expanded
                 
             display_score = min(final_score, 100)
             msg = f"Wynik dopasowania (Score): {display_score:.1f}%"
             
             if final_score >= 101:
                  msg += "\n\nPerfekcyjne dopasowanie (Exact Match)!"
                  messagebox.showinfo("Wynik Testu", msg)
                  # If expanded was perfect and original wasn't, we should update rect
                  if expanded_better:
                      self._propose_rect_update(expanded_crop, ex, ey, area)
                      
             elif final_score >= 80:
                  msg += "\n\nDobry wynik."
                  messagebox.showinfo("Wynik Testu", msg)
                  if expanded_better:
                      self._propose_rect_update(expanded_crop, ex, ey, area)
             else:
                  msg += "\n\nSłaby wynik. Czy chcesz uruchomić optymalizator?"
                  if messagebox.askyesno("Wynik Testu", msg):
                       from app.matcher import MATCH_MODE_FULL
                       def run_opt_callback(frames_data, mode=MATCH_MODE_FULL, initial_color=None):
                            # Prepare data synchronously, but run heavy optimize() in background thread
                            base = (ex, ey, ew, eh) if expanded_better else (ox, oy, ow, oh)

                            valid_rects = []
                            valid_images = []
                            for f in frames_data:
                                if f.get('image') is not None:
                                    valid_images.append(f['image'])
                                if f.get('rect'):
                                    valid_rects.append(f['rect'])
                                else:
                                    valid_rects.append(base)

                            if not valid_rects:
                                valid_rects = [base]

                            fw, fh = valid_images[0].size
                            fx, fy, real_w, real_h = calculate_merged_area(valid_rects, fw, fh, 0.05)
                            target_rect_final = (fx, fy, real_w, real_h)

                            # Progress Window (parented to root so it is visible even if area manager is withdrawn)
                            root = self._get_root()
                            w_prog = tk.Toplevel(root)
                            w_prog.title("Przetwarzanie")
                            try:
                                w_prog.transient(root)
                                w_prog.lift()
                                w_prog.attributes('-topmost', True)
                            except Exception:
                                pass
                            tk.Label(w_prog, text="Optymalizacja w toku...\n(To może chwilę potrwać)", padx=20, pady=20).pack()
                            w_prog.update()
                            print("[AreaManager] run_opt_callback: created progress window (w_prog)")
                            try:
                                # remove forced topmost to allow normal stacking afterwards
                                w_prog.attributes('-topmost', False)
                            except Exception:
                                pass

                            def worker():
                                try:
                                    print("[AreaManager] run_opt_callback: worker thread started")
                                    optimizer = SettingsOptimizer()
                                    res = optimizer.optimize(valid_images, target_rect_final, self.subtitle_lines, mode, initial_color=initial_color)

                                    def finish():
                                        try:
                                            w_prog.destroy()
                                        except:
                                            pass

                                        if res and res.get('score', 0) > final_score:
                                            ns = res['score']
                                            if messagebox.askyesno("Sukces", 
                                                                   f"Znaleziono lepsze ustawienia!\nŚredni wynik: {ns:.1f}%\n"
                                                                   "Czy chcesz zaktualizować obszar i parametry OCR?"):
                                                area['settings'].update(res['settings'])
                                                if 'rect' not in area or not area['rect']:
                                                    area['rect'] = {}
                                                try:
                                                    rect4 = scale_utils.scale_rect_to_4k({'left': int(fx), 'top': int(fy), 'width': int(real_w), 'height': int(real_h)}, fw, fh)
                                                except Exception:
                                                    rect4 = {'left': int(fx), 'top': int(fy), 'width': int(real_w), 'height': int(real_h)}
                                                area['rect'] = rect4
                                                self._load_details(self.current_selection_idx)
                                                messagebox.showinfo("Zapisano", "Zaktualizowano ustawienia i granice obszaru.")
                                        else:
                                            messagebox.showinfo("Info", "Nie udało się znaleźć lepszych parametrów.")

                                        # If there are rejected screens, show them
                                        if res and isinstance(res, dict) and res.get("rejected_screens") and opt_win:
                                            opt_win._show_rejected(res["rejected_screens"])

                                    self.after(0, finish)
                                except Exception as ex:
                                    print(f"[AreaManager] run_opt_callback: worker exception: {ex}")
                                    self.after(0, lambda: (w_prog.destroy(), messagebox.showerror("Błąd Optymalizacji", str(ex))))

                            try:
                                t = threading.Thread(target=worker, daemon=True)
                                print("[AreaManager] run_opt_callback: starting thread object", t)
                                t.start()
                                print("[AreaManager] run_opt_callback: thread started")
                            except Exception as ex:
                                print(f"[AreaManager] run_opt_callback: failed to start thread: {ex}")
                                messagebox.showerror("Błąd", f"Nie udało się uruchomić wątku optymalizatora: {ex}")
                            # Return None to signal asynchronous handling (keep optimization window open)
                            return None

                       # Open Capture Window
                       opt_win = OptimizationCaptureWindow(self, run_opt_callback, self)
                       # Add the initial capture we already have
                       opt_win.frames.append({'image': full_img, 'rect': None})
                       opt_win.lb_screens.insert(tk.END, "Zrzut #1 (Aktualny ekran)")

        except Exception as e:
             messagebox.showerror("Błąd", f"Podczas testu wystąpił błąd: {e}")
        finally:
             self.deiconify()

    def _propose_rect_update(self, image, offset_x, offset_y, area):
         """Helper to check bounds and ask user to update rect"""
         bounds = find_text_bounds(image)
         if bounds:
             bx, by, bw, bh = bounds
             # Absolute coords
             abs_x = offset_x + bx
             abs_y = offset_y + by
             
             # Ask user
             if messagebox.askyesno("Korekta Obszaru", 
                                    f"Wykryto tekst w szerszym obszarze.\n"
                                    f"Nowy wymiar: {bw}x{bh} (stary: {area['rect']['width']}x{area['rect']['height']})\n"
                                    "Czy zaktualizować granice obszaru?"):
                 # Convert absolute (image/screen) coords back to canonical 4K for storage
                 try:
                     src_w, src_h = image.size
                     rect4 = scale_utils.scale_rect_to_4k({'left': abs_x, 'top': abs_y, 'width': bw, 'height': bh}, src_w, src_h)
                 except Exception:
                     rect4 = {'left': abs_x, 'top': abs_y, 'width': bw, 'height': bh}
                 area['rect']['left'] = rect4['left']
                 area['rect']['top'] = rect4['top']
                 area['rect']['width'] = rect4['width']
                 area['rect']['height'] = rect4['height']
                 # Update settings from OCR might be needed too? No, just rect.
                 self._load_details(self.current_selection_idx)


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

    def _show_context_menu(self, event):
        try:
             idx = self.lb_areas.nearest(event.y)
             self.lb_areas.selection_clear(0, tk.END)
             self.lb_areas.selection_set(idx)
             self.lb_areas.activate(idx)
             self._on_list_select(None)
             self.context_menu.tk_popup(event.x_root, event.y_root)
        finally:
             self.context_menu.grab_release()

    def _open_optimizer(self):
        if self.current_selection_idx < 0: return
        if not self.subtitle_lines:
             messagebox.showwarning("Błąd", "Brak załadowanych napisów (plik txt) w presecie.\nNie można uruchomić optymalizacji.")
             return
             
        OptimizationCaptureWindow(self, self._run_optimizer, area_manager=self)


    def _run_optimizer(self, frames, mode=None, initial_color=None):
        from app.matcher import MATCH_MODE_FULL
        if mode is None:
            mode = MATCH_MODE_FULL
        if not frames:
            return

        subtitle_db = self.subtitle_lines

        results = []
        errors = []

        root = self._get_root()
        print(f"[AreaManager] _run_optimizer: creating progress window with root={root}")
        prog = tk.Toplevel(root)
        prog.title("Optymalizacja...")
        prog.geometry("350x120")
        try:
            prog.transient(root)
            prog.lift()
            prog.attributes('-topmost', True)
        except Exception:
            pass
        status_label = ttk.Label(prog, text="Trwa analiza... Proszę czekać.", font=("Arial", 10))
        status_label.pack(pady=20)
        prog.update()
        try:
            prog.attributes('-topmost', False)
        except Exception:
            pass
        print(f"[AreaManager] _run_optimizer: starting optimization (frames={len(frames)}, mode={mode}, initial_color={initial_color})")

        # Potrzebujemy referencji do okna optymalizacji, by wywołać _show_rejected
        opt_win = None
        for w in self.winfo_children():
            if isinstance(w, OptimizationCaptureWindow):
                opt_win = w
                break

        def task():
            try:
                print("[AreaManager] _run_optimizer: worker thread started")
                optimizer = SettingsOptimizer()
                # Zbierz wszystkie obrazy i sprawdź, czy mają rect (obszar)
                valid_images = []
                rects = []
                for f in frames:
                    if f.get('image') is not None:
                        valid_images.append(f['image'])
                    if f.get('rect') is not None:
                        rects.append(f['rect'])
                if not valid_images:
                    errors.append("Brak obrazów do optymalizacji.")
                    self.after(0, lambda: self._on_multi_opt_finished([], errors, prog))
                    return
                # Ustal wspólny rect (obszar) - bierzemy pierwszy z listy lub domyślny
                rough_area = rects[0] if rects else None
                if not rough_area:
                    errors.append("Brak obszaru (rect) do optymalizacji.")
                    self.after(0, lambda: self._on_multi_opt_finished([], errors, prog))
                    return
                status_label.config(text=f"Optymalizacja {len(valid_images)} zrzutów...")
                prog.update()
                print(f"[AreaManager] _run_optimizer: running optimizer.optimize on {len(valid_images)} images")
                result = optimizer.optimize(valid_images, rough_area, subtitle_db, match_mode=mode, initial_color=initial_color)
                results = [(0, result)]
                # Przekaż rejected_screens do okna optymalizacji
                if opt_win and result and "rejected_screens" in result:
                    self.after(0, lambda: opt_win._show_rejected(result["rejected_screens"]))
            except Exception as e:
                errors.append(f"Błąd optymalizacji: {e}")
                results = []
            finally:
                self.after(0, lambda: self._on_multi_opt_finished(results, errors, prog))

        threading.Thread(target=task, daemon=True).start()

    def _on_multi_opt_finished(self, results, errors, prog_win):
        # Destroy any fallback progress window created by the capture window
        try:
            if hasattr(self, '_opt_fallback') and self._opt_fallback:
                try: self._opt_fallback.destroy()
                except Exception: pass
                self._opt_fallback = None
        except Exception:
            pass
        try:
            prog_win.destroy()
        except Exception:
            pass
        if not results:
            msg = "Nie udało się przeprowadzić optymalizacji."
            if errors:
                msg += "\n" + "\n".join(errors)
            messagebox.showerror("Błąd", msg)
            return

        summary = []
        for idx, result in results:
            if not result or result.get('error'):
                summary.append(f"Zrzut #{idx+1}: Błąd: {result.get('error') if result else 'Brak wyniku'}")
            else:
                score = result.get('score', 0)
                summary.append(f"Zrzut #{idx+1}: Score: {score:.1f}%")

        msg = "Wyniki optymalizacji:\n" + "\n".join(summary)
        # Dodaj info o odrzuconych zrzutach jeśli są
        rejected = []
        for _, result in results:
            if result and isinstance(result, dict) and result.get("rejected_screens"):
                for r in result["rejected_screens"]:
                    idx = r.get("index", "?")
                    score = r.get("score", 0)
                    ocr = r.get("ocr", "")
                    preview = r.get("preview", "")
                    rejected.append(f"- Zrzut #{idx}: Najlepszy wynik: {score:.1f}%, Tekst OCR: {ocr}, Podgląd: {preview}")
        if rejected:
            msg += "\n\nOdrzucone zrzuty (brak ustawień z wynikiem >50%):\n" + "\n".join(rejected)
        if errors:
            msg += "\n\nBłędy:\n" + "\n".join(errors)

        # Zapytaj, czy zastosować najlepszy wynik (najwyższy score)
        best = max((r for r in results if r[1] and not r[1].get('error')), key=lambda x: x[1].get('score', 0), default=None)
        if best:
            idx, best_result = best
            if messagebox.askyesno("Wynik", msg + "\n\nCzy chcesz zastosować najlepsze ustawienia zrzutu #{0}?".format(idx+1), parent=self):
                self._apply_opt_result(best_result)
        else:
            messagebox.showinfo("Wynik", msg)

    def _on_opt_finished(self, result, prog_win):
        # Destroy any fallback progress window
        try:
            if hasattr(self, '_opt_fallback') and self._opt_fallback:
                try: self._opt_fallback.destroy()
                except Exception: pass
                self._opt_fallback = None
        except Exception:
            pass
        try:
            prog_win.destroy()
        except Exception:
            pass
        if not result or result.get('error'):
             messagebox.showerror("Błąd", f"Optymalizacja nie powiodła się: {result.get('error')}")
             return
             
        score = result.get('score', 0)
        msg = f"Znaleziono ustawienia (Score: {score:.1f}%).\nCzy chcesz je zastosować?"
        if messagebox.askyesno("Wynik", msg, parent=self):
             self._apply_opt_result(result)

    def _apply_opt_result(self, result):
        if self.current_selection_idx < 0: return
        area = self.areas[self.current_selection_idx]
        try:
            print(f"[AreaManager] _apply_opt_result: received optimized_area={result.get('optimized_area')} settings_keys={list(result.get('settings', {}).keys())}")
        except Exception:
            pass
        
        opt_rect = result.get('optimized_area')
        if opt_rect and isinstance(opt_rect, (list, tuple)):
            # opt_rect is in image/screen coordinates; convert to canonical 4K for storage
            try:
                screen_w = self.winfo_screenwidth()
                screen_h = self.winfo_screenheight()
                rect4 = scale_utils.scale_rect_to_4k({'left': opt_rect[0], 'top': opt_rect[1], 'width': opt_rect[2], 'height': opt_rect[3]}, screen_w, screen_h)
            except Exception:
                rect4 = {'left': opt_rect[0], 'top': opt_rect[1], 'width': opt_rect[2], 'height': opt_rect[3]}
            area['rect'] = rect4
            
        new_settings = result.get('settings', {})
        if 'settings' not in area: area['settings'] = {}
        
        for k, v in new_settings.items():
             area['settings'][k] = v
        
        self._load_details(self.current_selection_idx)
        messagebox.showinfo("Sukces", "Ustawienia zostały zaktualizowane.")


class OptimizationCaptureWindow(tk.Toplevel):
    def __init__(self, parent, on_start, area_manager=None):
        super().__init__(parent)
        self.title("Optymalizacja Ustawień")
        self.geometry("500x500")
        
        # Shortcuts
        self.bind("<F4>", lambda e: self._add_with_selection())
        
        self.on_start = on_start
        self.area_manager = area_manager
        self.frames = []
        self.current_area_data = None
        
        # UI
        main_f = ttk.Frame(self, padding=15)
        main_f.pack(fill=tk.BOTH, expand=True)
        
        ttk.Label(main_f, text="Kreator Optymalizacji", font=("Arial", 12, "bold")).pack(pady=10)
        instrukcja = (
            "Jak poprawnie zoptymalizować ustawienia:\n"
            "1. Najpierw dodaj zrzut ekranu, na którym napisy są dobrze widoczne – najlepiej taki, gdzie pojawia się cały tekst dialogu. To na tym pierwszym zrzucie program będzie szukał najlepszych ustawień.\n"
            "2. Dodaj kolejne zrzuty, jeśli chcesz sprawdzić, czy znalezione ustawienia działają także w innych sytuacjach (np. inny kolor tła, inne miejsce na ekranie).\n"
            "3. Zaznacz na każdym zrzucie dokładnie ten fragment, gdzie pojawiają się napisy – im dokładniej, tym lepiej.\n"
            "4. Jeśli napisy w grze mają inny kolor niż biały, wybierz ten kolor – program domyślnie testuje biały.\n"
            "\n"
            "Wyjaśnienie trybów dopasowania:\n"
            "• Pełne zdania: Wybierz tę opcję, jeśli w grze napisy pojawiają się od razu w całości (cały dialog na raz). To najpewniejszy i najdokładniejszy tryb.\n"
            "• Zaczyna się od: Użyj, jeśli napisy w grze pojawiają się stopniowo, np. najpierw pierwsze słowa, potem kolejne. Jeśli tryb Pełne zdania nie działa, ten prawie zawsze zadziała.\n"
            "• Częściowe: To tryb awaryjny – wybierz go tylko wtedy, gdy dwa poprzednie nie działają. Może być mniej dokładny i czasem rozpoznawać napisy błędnie.\n"
            "\n"
            "Im lepiej przygotujesz zrzuty i zaznaczysz napisy, tym lepszy będzie efekt optymalizacji!"
        )
        # Przycisk "Instrukcja" z tooltipem
        btn_instr = ttk.Button(main_f, text="Instrukcja")
        btn_instr.pack(anchor=tk.NE, pady=(0, 0), padx=(0, 5))

        tooltip = tk.Toplevel(main_f)
        tooltip.withdraw()
        tooltip.overrideredirect(True)
        tooltip_label = ttk.Label(tooltip, text=instrukcja, justify=tk.LEFT, wraplength=480, background="#ffffe0", relief="solid", borderwidth=1)
        tooltip_label.pack(ipadx=8, ipady=6)

        def show_tooltip(event=None):
            x = btn_instr.winfo_rootx() + btn_instr.winfo_width() + 8
            y = btn_instr.winfo_rooty() + btn_instr.winfo_height() // 2
            tooltip.geometry(f"+{x}+{y}")
            tooltip.deiconify()
        def hide_tooltip(event=None):
            tooltip.withdraw()
        btn_instr.bind("<Button-1>", show_tooltip)
        btn_instr.bind("<Leave>", hide_tooltip)
        
        self.list_frame = ttk.Frame(main_f)
        self.list_frame.pack(fill=tk.BOTH, expand=True, pady=10)
        
        self.lb_screens = tk.Listbox(self.list_frame, height=6)
        self.lb_screens.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        btn_box = ttk.Frame(self.list_frame)
        btn_box.pack(side=tk.LEFT, fill=tk.Y, padx=5)
        
        self.btn_add_area = ttk.Button(btn_box, text="Zrób zrzut ekranu zrzut [F4]", command=self._add_with_selection)
        self.btn_add_area.pack(fill=tk.X, pady=2)
        
        self.btn_import = ttk.Button(btn_box, text="Importuj zrzuty", command=self._import_screenshot)
        self.btn_import.pack(fill=tk.X, pady=2)

        # Removed Add Full Screen button as per request
        
        self.btn_rem = ttk.Button(btn_box, text="Usuń", command=self._remove_screenshot)
        self.btn_rem.pack(fill=tk.X, pady=2)
        
        # Options Frame
        opt_frame = ttk.LabelFrame(main_f, text="Ustawienia Wstępne", padding=10)
        opt_frame.pack(fill=tk.X, pady=5)
        
        # Match Mode
        ttk.Label(opt_frame, text="Sposób dopasowania:").pack(anchor=tk.W)
        self.var_match_mode = tk.StringVar(value="Pełne zdania")
        # Mapowanie nazw wyświetlanych na stałe
        self.mode_map = {
            "Pełne zdania": MATCH_MODE_FULL, 
            "Zaczyna się od": MATCH_MODE_STARTS,
            "Częściowe": MATCH_MODE_PARTIAL
        }
        self.mode_map_reverse = {v: k for k, v in self.mode_map.items()}
        modes = list(self.mode_map.keys())
        cb_mode = ttk.Combobox(opt_frame, textvariable=self.var_match_mode, values=modes, state="readonly")
        cb_mode.pack(fill=tk.X, pady=(0, 5))
        
        # Color Picker
        ttk.Label(opt_frame, text="Wymuś kolor (Wymagane dla szarych napisów):").pack(anchor=tk.W)
        self.var_color = tk.StringVar(value="#FFFFFF")
        
        col_frame = ttk.Frame(opt_frame)
        col_frame.pack(fill=tk.X)
        
        self.lbl_color_preview = tk.Label(col_frame, text="", bg="#FFFFFF", relief="sunken", width=10)
        self.lbl_color_preview.pack(side=tk.LEFT, padx=(0, 5))
        
        ttk.Button(col_frame, text="Wybierz...", command=self._pick_color).pack(side=tk.LEFT)
        ttk.Button(col_frame, text="X", width=3, command=self._clear_color).pack(side=tk.LEFT, padx=2)

        # Start
        self.btn_run = ttk.Button(main_f, text="Uruchom Optymalizację", command=self._start_opt)
        self.btn_run.pack(pady=10, fill=tk.X)
        self.status = ttk.Label(main_f, text="")
        self.status.pack(pady=5)

        # Label na odrzucone zrzuty
        self.rejected_label = ttk.Label(main_f, text="", foreground="red", wraplength=450, justify=tk.LEFT)
        self.rejected_label.pack(pady=5)
    
    def _pick_color(self):
        # Store root reference
        root = self._get_root()
        
        self.withdraw()
        if self.area_manager: self.area_manager.withdraw()
        
        # Ensure UI updates before sleeping
        self.update()
        import time
        time.sleep(0.3)
        
        try:
            img = capture_fullscreen()
        except:
            img = None
        
        if not img:
            self.deiconify()
            if self.area_manager: self.area_manager.deiconify()
            return
            
        try:
            sel = ColorSelector(root, img)
            
            if sel.selected_color:
                hex_color = sel.selected_color
                self.var_color.set(hex_color)
                self.lbl_color_preview.config(bg=hex_color, text="")
                
        except Exception as e:
            print(f"Error picking color: {e}")
            
        finally:
            self.deiconify()
            if self.area_manager: self.area_manager.deiconify()

    def _clear_color(self):
        self.var_color.set("")
        self.lbl_color_preview.config(bg="#eeeeee", text="Brak")

    # Removed _add_screenshot method

    def _add_with_selection(self):
        # We need a reference to root to create the selector correctly
        root = self.winfo_toplevel()
        
        self.withdraw()
        if self.area_manager: self.area_manager.withdraw()
        
        # Ensure UI updates before sleeping
        self.update()
        import time
        time.sleep(0.3)
        
        try:
            img = capture_fullscreen()
        except:
            img = None
        
        if not img:
            self.deiconify()
            if self.area_manager: self.area_manager.deiconify()
            return
            
        # Select area
        try:
            # Explicitly find root to parent the selector
            # This prevents issues with withdrawn parents hiding children
            root = self._get_root()
            
            # Pass root as parent. If root is invalid, None (default) is used.
            sel = AreaSelector(root, img)
            
            # REMOVED sel.wait_window() because AreaSelector calls it in __init__
            # Calling it again here on a destroyed widget caused "bad window path".
            
        except Exception as e:
            # Fallback
            print(f"Error opening selector: {e}")
            self.deiconify()
            if self.area_manager: self.area_manager.deiconify()
            return
            # Fallback
            print(f"Error opening selector: {e}")
            self.deiconify()
            if self.area_manager: self.area_manager.deiconify()
            return
        
        self.deiconify()
        if self.area_manager: self.area_manager.deiconify()
        
        if sel.geometry:
            r = sel.geometry
            # Store rect relative to screen
            # (left, top, width, height)
            rect_tuple = (r['left'], r['top'], r['width'], r['height'])
            self.frames.append({"image": img, "rect": rect_tuple})
            self.lb_screens.insert(tk.END, f"Zrzut #{len(self.frames)} (Zaznaczony obszar: {rect_tuple})")
        else:
            # User cancelled selection but maybe still wants image? 
            # Assume cancel means cancel add.
            pass

    def _import_screenshot(self):
        from tkinter import filedialog
        from PIL import Image
        import os
        
        # Allow multiple selection
        home = os.path.expanduser('~')
        print(f"[OptimizationWindow] _import_screenshot: default dir={home}")
        paths = filedialog.askopenfilenames(title="Wybierz zrzut ekranu",
                          initialdir=home,
                          filetypes=[("Obrazy", "*.png *.jpg *.jpeg *.bmp"), ("Wszystkie", "*.*")], parent=self)
        if not paths:
             return
        
        # Hide window once for all imports
        root = self._get_root()
        self.withdraw()
        if self.area_manager: self.area_manager.withdraw()
        self.update_idletasks()
        
        try:
            for path in paths:
                try:
                    # 1. Wczytaj obraz
                    pil_img = Image.open(path).convert('RGB')
                    w, h = pil_img.size
                    target_res = (w, h)
                    
                    # 2. Selekcja obszaru na zaimportowanym obrazie
                    # AreaSelector otworzy się na pełny ekran z tym obrazem jako tło
                    sel = AreaSelector(root, pil_img) # Blokuje aż do zamknięcia
                    
                    if sel.geometry:
                        r = sel.geometry
                        rect_tuple = (r['left'], r['top'], r['width'], r['height'])
                        
                        self.frames.append({"image": pil_img, "rect": rect_tuple})
                        
                        # Formatting info for listbox
                        info = f"Import ({target_res[0]}x{target_res[1]}) - Obszar: {rect_tuple}"
                        self.lb_screens.insert(tk.END, info)
                except Exception as ex:
                    print(f"Błąd importu pliku {path}: {ex}")
                    # Continue to next file
                    pass
                    
        except Exception as e:
            messagebox.showerror("Błąd", f"Błąd importu: {e}")
        finally:
            self.deiconify()
            if self.area_manager: self.area_manager.deiconify()

    def _get_root(self):
        w = self
        while w.master:
             w = w.master
        return w

    def _remove_screenshot(self):
        sel = self.lb_screens.curselection()
        if not sel: return
        idx = sel[0]
        del self.frames[idx]
        self.lb_screens.delete(idx)
        # Renumber/refresh list? lazy way:
        self.lb_screens.delete(0, tk.END)
        for i, f in enumerate(self.frames):
             info = f" (Zaznaczony obszar: {f['rect']})" if f['rect'] else " (Pełny ekran)"
             self.lb_screens.insert(tk.END, f"Zrzut #{i+1}{info}")

    def _start_opt(self):
        if not self.frames:
            messagebox.showerror("Błąd", "Dodaj przynajmniej jeden zrzut ekranu.")
            return
        disp_mode = self.var_match_mode.get()
        mode = self.mode_map.get(disp_mode, MATCH_MODE_FULL)
        color = self.var_color.get() if self.var_color.get() else None

        print(f"[OptimizationWindow] _start_opt: frames={len(self.frames)}")
        for i,f in enumerate(self.frames):
            print(f"[OptimizationWindow] frame#{i}: has_image={('image' in f and f['image'] is not None)}, has_rect={('rect' in f and f['rect'] is not None)}")
        # Przechwyć callback, aby przechwycić rejected_screens
        def on_start_with_rejected(frames, mode, initial_color):
            print(f"[OptimizationWindow] calling on_start with {len(frames)} frames, mode={mode}, initial_color={initial_color}")
            try:
                print(f"[OptimizationWindow] on_start object: {self.on_start} (repr: {repr(self.on_start)})")
                try:
                    qual = getattr(self.on_start, '__qualname__', None)
                except Exception:
                    qual = None
                print(f"[OptimizationWindow] on_start qualname: {qual}")
            except Exception:
                pass
            result = self.on_start(frames, mode=mode, initial_color=initial_color)
            # Oczekujemy, że on_start zwraca result (lub None)
            if result and isinstance(result, dict) and "rejected_screens" in result:
                self._show_rejected(result["rejected_screens"])
            return result

        # Spróbuj wywołać i przechwycić rejected_screens (jeśli on_start zwraca wynik synchronicznie)
        # Spróbuj wywołać i przechwycić rejected_screens (jeśli on_start zwraca wynik synchronicznie)
        res = on_start_with_rejected(self.frames, mode, color)
        print(f"[OptimizationWindow] on_start returned: {res}")
        # Jeśli on_start zwróci None, oznacza to, że uruchomiono pracę asynchroniczną;
        # w takim wypadku nie zamykamy okna - to wywołujący (w wątku) zadzwoni do
        # _show_rejected lub innego mechanizmu powiadomienia, a następnie okno można zamknąć.
        if res is None:
            # Callback started asynchronous work — hide this wizard so caller's progress window is visible
            try:
                self.withdraw()
            except Exception:
                pass

            # Ensure progress window appears: if caller for some reason didn't create it,
            # create a small fallback window after short delay so user is not left without feedback.
            def ensure_prog_visible():
                root = self._get_root()
                found = False
                try:
                    for w in root.winfo_children():
                        try:
                            if isinstance(w, tk.Toplevel) and w.winfo_exists():
                                title = w.title()
                                if "Optymalizacja" in title or "Przetwarzanie" in title:
                                    found = True
                                    break
                        except Exception:
                            pass
                except Exception:
                    found = False

                if not found:
                    try:
                        print("[OptimizationWindow] ensure_prog_visible: no progress window found, creating fallback")
                        fb = tk.Toplevel(root)
                        fb.title("Optymalizacja...")
                        ttk.Label(fb, text="Uruchamianie optymalizatora...", padding=10).pack()
                        try:
                            fb.transient(root); fb.lift(); fb.attributes('-topmost', True); fb.update(); fb.attributes('-topmost', False)
                        except Exception:
                            pass
                        # store fallback on area_manager so it can be removed later
                        if self.area_manager:
                            try: self.area_manager._opt_fallback = fb
                            except Exception: pass
                    except Exception as e:
                        print(f"[OptimizationWindow] failed to create fallback prog window: {e}")

            # Schedule check shortly after returning
            try:
                self.after(300, ensure_prog_visible)
            except Exception:
                ensure_prog_visible()

            return

        # Jeśli on_start jest synchroniczny i zwrócił wynik z rejected_screens, pozostaw okno
        if isinstance(res, dict) and res.get("rejected_screens"):
            return

        # W przeciwnym wypadku (synchroniczny wynik bez odrzuconych zrzutów) zamykamy okno
        self.destroy()

    def _show_rejected(self, rejected_screens):
        if not rejected_screens:
            self.rejected_label.config(text="")
            return
        lines = [f"Odrzucone zrzuty (brak ustawień z wynikiem >50%):"]
        for r in rejected_screens:
            idx = r.get("index", "?")
            score = r.get("score", 0)
            ocr = r.get("ocr", "")
            preview = r.get("preview", "")
            lines.append(f"- Zrzut #{idx}: Najlepszy wynik: {score:.1f}%, Tekst OCR: {ocr}, Podgląd: {preview}")
        self.rejected_label.config(text="\n".join(lines))
