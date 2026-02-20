import tkinter as tk
from tkinter import ttk, messagebox
import os
from typing import List, Dict, Any, Optional, TYPE_CHECKING

from app.config_manager import ConfigManager, AreaConfig

if TYPE_CHECKING:
    from lektor import LektorApp

try:
    from pynput import keyboard
except ImportError:
    keyboard = None

from app.area_selector import AreaSelector, ColorSelector
from app.capture import capture_fullscreen
from app.optimizer import SettingsOptimizer
from app.matcher import precompute_subtitles
from app.ocr import find_text_bounds

# --- Stałe / tłumaczenia dla AreaManager ---
# Typy obszarów (wartości przechowywane w konfiguracji)
TYPE_CONTINUOUS = "continuous"
TYPE_MANUAL = "manual"

# Krótkie etykiety używane w listach i comboboxie
TYPE_SHORT_MAP = {
    TYPE_CONTINUOUS: "Stały",
    TYPE_MANUAL: "Wyzwalany",
}

# Etykiety stanu
STATE_ON = "ON"
STATE_OFF = "OFF"


class AreaManagerWindow(tk.Toplevel):

    def __init__(self, parent: tk.Misc, app: 'LektorApp', subtitle_lines: Optional[List[Dict[str, Any]]] = None):
        """Accepts the main `LektorApp` instance so AreaManager can access
        `config_mgr`, resolution and other context directly. Subtitle lines may
        be provided for the test UI.
        """
        super().__init__(parent)
        self.title("Zarządzanie Obszarami")
        self.geometry("1000x700")
        self.app: 'LektorApp' = app
        self.config_mgr: Optional[ConfigManager] = app.config_mgr
        self.subtitle_lines: Optional[List[Dict[str, Any]]] = subtitle_lines

        self.areas: List[AreaConfig] = self.config_mgr.get_areas() if self.config_mgr else []
        self.current_selection_idx = 0 if self.areas else -1
        self._init_ui()
        self._refresh_list()

    # Persistence is handled directly via `self.config_mgr.set_areas()`
    def _is_main_area(self, area_id: Any) -> bool:
        """Helper to identify the primary area which cannot be removed."""
        return area_id == 1 or str(area_id).lower() == "area_0" or str(area_id).lower() == "area_1"

    def _refresh_list(self):
        self.lb_areas.delete(0, tk.END)
        for i, area in enumerate(self.areas):
            typ_raw = area.type
            t = TYPE_SHORT_MAP.get(typ_raw, typ_raw)
            display = f"#{area.id if area.id is not None else i+1}"
            if area.name:
                display += f" {area.name}"
            display += f" [{t}]"
            if typ_raw == TYPE_CONTINUOUS and not self._is_main_area(area.id):
                state = STATE_ON if area.enabled else STATE_OFF
                display += f" [{state}]"
            self.lb_areas.insert(tk.END, display)
        if self.current_selection_idx >= 0 and self.current_selection_idx < len(self.areas):
            self.lb_areas.selection_set(self.current_selection_idx)
            self._load_details(self.current_selection_idx)
            area = self.areas[self.current_selection_idx]
            if self._is_main_area(area.id):
                self.btn_remove.config(state=tk.DISABLED)
            else:
                self.btn_remove.config(state=tk.NORMAL)

    def _init_ui(self):
        # Left side: List
        left_frame = ttk.Frame(self, padding=5)
        left_frame.pack(side=tk.LEFT, fill=tk.Y)

        ttk.Label(left_frame, text="Lista Obszarów").pack(anchor=tk.W)
        self.lb_areas = tk.Listbox(left_frame, width=30)
        self.lb_areas.pack(fill=tk.BOTH, expand=True, pady=5)
        self.lb_areas.bind('<<ListboxSelect>>', self._on_list_select)
        self.lb_areas.bind('<Double-Button-1>', self._rename_area_dialog)

        btn_frame = ttk.Frame(left_frame)
        btn_frame.pack(fill=tk.X)
        ttk.Button(btn_frame, text="+ Dodaj",
                   command=self._add_area).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(btn_frame, text="Duplikuj", command=self._duplicate_area).pack(
            side=tk.LEFT, fill=tk.X, expand=True)
        self.btn_remove = ttk.Button(
            btn_frame, text="- Usuń", command=self._remove_area, state=tk.DISABLED)
        self.btn_remove.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # Save / Close
        action_frame = ttk.Frame(left_frame, padding=(0, 20, 0, 0))
        action_frame.pack(fill=tk.X, side=tk.BOTTOM)
        ttk.Button(action_frame, text="Zapisz i Zamknij",
                   command=self._save_and_close).pack(fill=tk.X, pady=5)

        # Test Button
        self.btn_test = ttk.Button(
            action_frame, text="🧪 Testuj ustawienia", command=self._test_current_settings)
        self.btn_test.pack(fill=tk.X, pady=5)

        ttk.Button(action_frame, text="Anuluj",
                   command=self.destroy).pack(fill=tk.X)

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
        ttk.Label(grid, text="Typ obszaru:", font=("Arial", 10, "bold")).grid(
            row=0, column=0, sticky=tk.W, pady=10)
        self.var_type = tk.StringVar()
        self.type_mapping = TYPE_SHORT_MAP
        self.rev_type_mapping = {v: k for k, v in self.type_mapping.items()}
        self.cb_type = ttk.Combobox(grid, textvariable=self.var_type, values=list(
            self.type_mapping.values()), state="readonly")
        self.cb_type.grid(row=0, column=1, sticky=tk.EW, padx=10)
        self.cb_type.bind("<<ComboboxSelected>>", self._on_field_change)

        # Name
        ttk.Label(grid, text="Nazwa:", font=("Arial", 10, "bold")).grid(
            row=1, column=0, sticky=tk.W, pady=10)
        self.var_name = tk.StringVar()
        self.entry_name = ttk.Entry(grid, textvariable=self.var_name)
        self.entry_name.grid(row=1, column=1, sticky=tk.EW, padx=10)
        self.entry_name.bind("<KeyRelease>", self._on_field_change)

        # Tab General
        self.var_enabled = tk.BooleanVar()
        self.chk_enabled = ttk.Checkbutton(
            grid, text="Aktywny (Włączony)", variable=self.var_enabled, command=self._on_field_change)
        self.chk_enabled.grid(row=2, column=1, sticky=tk.W, padx=10)

        # Rect
        ttk.Separator(parent, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=15)

        f_rect = ttk.Frame(parent)
        f_rect.pack(fill=tk.X)
        ttk.Label(f_rect, text="Pozycja i Rozmiar:", font=(
            "Arial", 10, "bold")).pack(anchor=tk.W)
        self.lbl_rect = ttk.Label(
            f_rect, text="Brak zdefiniowanego obszaru", foreground="#555")
        self.lbl_rect.pack(anchor=tk.W, pady=5)
        ttk.Button(f_rect, text="Ręcznie zaznacz obszar",
                   command=self._select_area_on_screen).pack(anchor=tk.W, pady=5)

        # Hotkey
        ttk.Separator(parent, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=15)

        f_hk = ttk.Frame(parent)
        f_hk.pack(fill=tk.X)
        ttk.Label(f_hk, text="Skrót klawiszowy:", font=(
            "Arial", 10, "bold")).pack(anchor=tk.W)

        h_row = ttk.Frame(f_hk)
        h_row.pack(fill=tk.X, pady=5)
        self.var_hotkey = tk.StringVar()
        self.entry_hotkey = ttk.Entry(
            h_row, textvariable=self.var_hotkey, state="readonly")
        self.entry_hotkey.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.btn_record = ttk.Button(
            h_row, text="Nagraj", command=self._record_hotkey)
        self.btn_record.pack(side=tk.LEFT, padx=5)
        ttk.Button(h_row, text="X", width=3,
                   command=self._clear_hotkey).pack(side=tk.LEFT)

        # OCR Settings
        ttk.Separator(parent, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=15)
        ttk.Label(parent, text="Ustawienia Obrazu i OCR:", font=(
            "Arial", 10, "bold")).pack(anchor=tk.W, pady=(0, 10))

        pl = ttk.Frame(parent)
        pl.pack(fill=tk.BOTH, expand=True)
        pl.columnconfigure(1, weight=1)
        r = 0

        def add_row(label, widget):
            nonlocal r
            ttk.Label(pl, text=label).grid(
                row=r, column=0, sticky=tk.W, pady=5, padx=5)
            widget.grid(row=r, column=1, sticky=tk.EW, pady=5, padx=5)
            r += 1
            return widget

        # Thickening
        f_th = ttk.Frame(pl)
        self.var_thickening = tk.IntVar()
        ttk.Scale(f_th, from_=0, to=5, variable=self.var_thickening,
                  command=lambda v: self._on_field_change()).pack(side=tk.LEFT, fill=tk.X, expand=True)
        l_th = ttk.Label(f_th, text="0")
        l_th.pack(side=tk.LEFT, padx=5)
        self.var_thickening.trace_add(
            "write", lambda *a: l_th.config(text=f"{self.var_thickening.get()}"))
        add_row("Pogrubienie:", f_th)

        # Mode
        self.var_mode = tk.StringVar()
        from app.matcher import MATCH_MODE_FULL, MATCH_MODE_STARTS, MATCH_MODE_PARTIAL
        self.mode_mapping = {
            MATCH_MODE_FULL: "Pełne linie",
            MATCH_MODE_STARTS: "Zaczyna się od",
            MATCH_MODE_PARTIAL: "Częściowe"
        }
        self.rev_mode_mapping = {v: k for k, v in self.mode_mapping.items()}
        cb_mode = ttk.Combobox(pl, textvariable=self.var_mode, values=list(
            self.mode_mapping.values()), state="readonly")
        cb_mode.bind("<<ComboboxSelected>>", self._on_field_change)
        add_row("Tryb dopasowania:", cb_mode)

        # Brightness
        f_br = ttk.Frame(pl)
        self.var_brightness = tk.IntVar()
        def _on_brightness_change(v):
            try:
                # Scale reports floats; store as int for display and settings
                self.var_brightness.set(int(float(v)))
            except Exception:
                pass
            self._on_field_change()

        ttk.Scale(f_br, from_=0, to=255, variable=self.var_brightness,
                  command=_on_brightness_change).pack(side=tk.LEFT, fill=tk.X, expand=True)
        l_br = ttk.Label(f_br, text="0")
        l_br.pack(side=tk.LEFT, padx=5)
        self.var_brightness.trace_add("write", lambda *a: l_br.config(text=f"{self.var_brightness.get()}"))
        add_row("Próg jasności:", f_br)

        # Contrast
        f_co = ttk.Frame(pl)
        self.var_contrast = tk.DoubleVar()
        ttk.Scale(f_co, from_=0.0, to=5.0, variable=self.var_contrast,
                  command=lambda v: self._on_field_change()).pack(side=tk.LEFT, fill=tk.X, expand=True)
        l_co = ttk.Label(f_co, text="0.0")
        l_co.pack(side=tk.LEFT, padx=5)
        self.var_contrast.trace_add(
            "write", lambda *a: l_co.config(text=f"{self.var_contrast.get():.1f}"))
        add_row("Kontrast:", f_co)

    def _init_tab_colors(self, parent):
        self.var_use_colors = tk.BooleanVar()
        self.chk_use_colors = ttk.Checkbutton(
            parent, text="Używaj filtrowania kolorów", variable=self.var_use_colors, command=self._on_field_change)
        self.chk_use_colors.pack(anchor=tk.W, pady=10)

        row = ttk.Frame(parent)
        row.pack(fill=tk.BOTH, expand=True)

        self.lb_colors = tk.Listbox(row, height=8)
        self.lb_colors.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        btns = ttk.Frame(row)
        btns.pack(side=tk.LEFT, fill=tk.Y, padx=5)
        ttk.Button(btns, text="Pobierz z Ekranu",
                   command=self._pick_color_screen).pack(fill=tk.X, pady=2)
        ttk.Button(btns, text="Dodaj Biały", command=lambda: self._add_color_manual(
            "#FFFFFF")).pack(fill=tk.X, pady=2)
        ttk.Button(btns, text="Usuń zaznaczony",
                   command=self._remove_color).pack(fill=tk.X, pady=2)

        # Tolerance
        f_tol = ttk.Frame(parent)
        f_tol.pack(fill=tk.X, pady=15)
        ttk.Label(f_tol, text="Tolerancja koloru:").pack(anchor=tk.W)
        self.var_tolerance = tk.IntVar()

        def on_tol_change(v):
            self.var_tolerance.set(int(float(v)))
            self._on_field_change()
        ttk.Scale(f_tol, from_=0, to=100, variable=self.var_tolerance, orient=tk.HORIZONTAL,
                  command=on_tol_change).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Label(f_tol, textvariable=self.var_tolerance).pack(
            side=tk.LEFT, padx=5)

    def _load_details(self, idx):
        if idx < 0 or idx >= len(self.areas):
            return
        area = self.areas[idx]
        # AreaConfig is flattened; authoritative settings are accessed directly
        # via the AreaConfig instance belonging to the manager.
        settings = area

        # Tab General
        typ = area.type
        self.var_type.set(self.type_mapping.get(typ, typ))
        self.var_name.set(area.name or "")

        self.var_enabled.set(area.enabled)
        if typ == TYPE_CONTINUOUS and area.id != 1:
            self.chk_enabled.config(state=tk.NORMAL)
        else:
            self.chk_enabled.config(state=tk.DISABLED)

        r = area.rect
        if r:
            # area['rect'] is expected to be in screen coordinates
            try:
                srect = {'left': int(r.get('left', 0)), 'top': int(r.get('top', 0)), 'width': int(
                    r.get('width', 0)), 'height': int(r.get('height', 0))}
                self.lbl_rect.config(
                    text=f"X:{srect['left']} Y:{srect['top']} {srect['width']}x{srect['height']}")
            except Exception:
                self.lbl_rect.config(text="Błąd przeliczenia obszaru")
        else:
            self.lbl_rect.config(text="Brak (Kliknij 'Wybierz Obszar')")

        self.var_hotkey.set(area.hotkey or '')

        # Tab OCR - AreaConfig is flattened, read attrs directly
        self.var_thickening.set(settings.text_thickening)

        from app.matcher import MATCH_MODE_FULL
        mode_val = settings.subtitle_mode if settings.subtitle_mode is not None else MATCH_MODE_FULL
        self.var_mode.set(self.mode_mapping.get(mode_val, mode_val))

        self.var_brightness.set(settings.brightness_threshold)
        self.var_contrast.set(settings.contrast)

        # Tab Colors
        self.var_use_colors.set(settings.use_colors)
        self.var_tolerance.set(settings.color_tolerance)

        self.lb_colors.delete(0, tk.END)
        colors_list = settings.colors or []
        for c in colors_list:
            self.lb_colors.insert(tk.END, c)

        # Note: we intentionally do not block _on_field_change here —
        # settings are saved explicitly via the "Zapisz i Zamknij" button.

        for tab in [self.tab_general, self.tab_colors]:
            for child in tab.winfo_children():
                try:
                    child.config(state=tk.NORMAL)
                except tk.TclError:
                    pass

    def _on_field_change(self, event=None):
        if self.current_selection_idx < 0:
            return
        area = self.areas[self.current_selection_idx]
        # Map UI fields back to flattened area attributes
        disp_type = self.var_type.get()
        real_type = self.rev_type_mapping.get(disp_type, disp_type)
        area.type = real_type
        area.name = self.var_name.get()

        area.enabled = self.var_enabled.get()
        area.hotkey = self.var_hotkey.get()

        area.text_thickening = self.var_thickening.get()

        disp_mode = self.var_mode.get()
        area.subtitle_mode = self.rev_mode_mapping.get(disp_mode, disp_mode)

        # s['text_color_mode'] removed
        area.brightness_threshold = self.var_brightness.get()
        area.contrast = self.var_contrast.get()
        area.use_colors = self.var_use_colors.get()
        area.color_tolerance = self.var_tolerance.get()
        # Zapisz tryb dopasowania do settings (ensure normalized)
        if self.var_mode.get() in self.rev_mode_mapping:
            area.subtitle_mode = self.rev_mode_mapping[self.var_mode.get()]

        # Refresh list name if type changed
        self.lb_areas.delete(self.current_selection_idx)
        typ_raw = area.type
        t = TYPE_SHORT_MAP.get(typ_raw, typ_raw)
        display = f"#{area.id}"
        if area.name:
            display += f" {area.name}"
        display += f" [{t}]"
        if typ_raw == TYPE_CONTINUOUS and area.id != 1:
            state = STATE_ON if area.enabled else STATE_OFF
            display += f" [{state}]"
        self.lb_areas.insert(self.current_selection_idx, display)
        self.lb_areas.selection_set(self.current_selection_idx)
        # Persist immediate changes to ConfigManager so it's authoritative
        self.config_mgr.set_areas(self.areas)


    def _select_area_on_screen(self):
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

        ttk.Button(btns, text="Importuj wybrane",
                   command=do_ok).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Anuluj", command=do_cancel).pack(
            side=tk.LEFT, padx=4)

        self.wait_window(dlg)

        paths = selected_paths
        if not paths:
            return

        # Hide window once for all imports
        root = self._get_root()
        self.withdraw()
        if self.area_manager:
            self.area_manager.withdraw()
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
                    # Blokuje aż do zamknięcia
                    sel = AreaSelector(root, pil_img)

                    if sel.geometry:
                        r = sel.geometry
                        rect_tuple = (r['left'], r['top'],
                                      r['width'], r['height'])

                        self.frames.append(
                            {"image": pil_img, "rect": rect_tuple})

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
            if self.app and hasattr(self.app, 'area_manager') and self.app.area_manager:
                 self.app.area_manager.deiconify()

        existing_ids = {a.id for a in self.areas}
        next_id = 1
        while next_id in existing_ids:
            next_id += 1

        self.areas.append(AreaConfig(id=next_id, type=TYPE_MANUAL, rect=None, hotkey=""))
        self.config_mgr.set_areas(self.areas)
        self.current_selection_idx = len(self.areas) - 1
        self._refresh_list()

    def _remove_area(self):
        if self.current_selection_idx < 0:
            return
        area = self.areas[self.current_selection_idx]
        if self._is_main_area(area.id):
            messagebox.showwarning(
                "Błąd", "Nie można usunąć głównego obszaru.")
            return
        del self.areas[self.current_selection_idx]
        # ensure index is valid
        if self.current_selection_idx >= len(self.areas):
            self.current_selection_idx = max(0, len(self.areas) - 1)
        self.config_mgr.set_areas(self.areas)
        self._refresh_list()

    def _rename_area_dialog(self, event=None):
        sel = self.lb_areas.curselection()
        if sel:
            self.current_selection_idx = sel[0]

        if self.current_selection_idx < 0 or self.current_selection_idx >= len(self.areas):
            return
        area = self.areas[self.current_selection_idx]
        from tkinter import simpledialog
        name = simpledialog.askstring(
            "Nazwa obszaru", f"Podaj nazwę dla obszaru #{area.id}:", initialvalue=area.name, parent=self)
        if name is not None:
            area.name = name.strip()
            self.config_mgr.set_areas(self.areas)
            self._refresh_list()

    def _on_list_select(self, event):
        sel = self.lb_areas.curselection()
        if not sel:
            return
        self.current_selection_idx = sel[0]
        self._refresh_list()

    def _add_default_area(self):
        self.areas.append(AreaConfig(id=1, type=TYPE_CONTINUOUS, rect=None, hotkey=""))
        self.config_mgr.set_areas(self.areas)
        self._refresh_list()

    def _add_area(self):
        # Create and select a new manual area
        existing_ids = [a.id for a in self.areas]
        new_id = (max(existing_ids) if existing_ids else 0) + 1
        new_area = AreaConfig(id=new_id, type=TYPE_MANUAL, rect=None, hotkey="")
        self.areas.append(new_area)
        self.config_mgr.set_areas(self.areas)
        self.current_selection_idx = len(self.areas) - 1
        self._refresh_list()

    def _select_area_on_screen(self):
        if self.current_selection_idx < 0:
            return
        self.withdraw()
        self.update()
        import time
        time.sleep(0.3)
        try:
            img = capture_fullscreen()
            if not img:
                self.deiconify()
                return

            regions_screen = []
            for idx, area in enumerate(self.areas):
                r = area.rect
                if not r:
                    continue
                # assume r is already screen coordinates
                box = {'left': int(r.get('left', 0)), 'top': int(r.get('top', 0)), 'width': int(
                    r.get('width', 0)), 'height': int(r.get('height', 0))}
                regions_screen.append({'rect': box})
            root = self._get_root()
            sel = AreaSelector(root, img, existing_regions=[
                               r['rect'] for r in regions_screen])
            # AreaSelector is blocking in init, so no need to wait here.
            if sel.geometry:
                # Store geometry as screen coordinates and persist immediately
                area = self.areas[self.current_selection_idx]
                if area:
                    area.rect = {'left': int(sel.geometry['left']), 'top': int(
                        sel.geometry['top']), 'width': int(sel.geometry['width']), 'height': int(sel.geometry['height'])}
                self.config_mgr.set_areas(self.areas)
                self._load_details(self.current_selection_idx)
                # Auto update bounds label (screen coords)
                r = self.areas[self.current_selection_idx].rect or {}
                self.lbl_rect.config(
                    text=f"X:{r.get('left')} Y:{r.get('top')} {r.get('width')}x{r.get('height')}")
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
        if self.current_selection_idx < 0:
            return
        area = self.areas[self.current_selection_idx]
        colors = area.colors

        if color not in colors:
            colors.append(color)
            # Keep insertion order unique
            uniq = list(dict.fromkeys(colors))
            area.colors = uniq
        # Persist change and refresh details
        self.config_mgr.set_areas(self.areas)
        self._load_details(self.current_selection_idx)

    def _remove_color(self):
        if self.current_selection_idx < 0:
            return
        sel_idx = self.lb_colors.curselection()
        if not sel_idx:
            return

        idx = sel_idx[0]
        area = self.areas[self.current_selection_idx]
        colors = area.colors or []

        if 0 <= idx < len(colors):
            del colors[idx]
            area.colors = colors
            self.config_mgr.set_areas(self.areas)
            self._load_details(self.current_selection_idx)

    def _pick_color_screen(self):
        if self.current_selection_idx < 0:
            return
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
            area = self.areas[self.current_selection_idx]
            if area:
                area.hotkey = key_str
            self.config_mgr.set_areas(self.areas)
            self.var_hotkey.set(key_str)
        self.btn_record.config(text="Nagraj", state=tk.NORMAL)

    def _clear_hotkey(self):
        if self.current_selection_idx >= 0:
            area = self.areas[self.current_selection_idx]
            if area:
                area.hotkey = ""
            self.config_mgr.set_areas(self.areas)
            self.var_hotkey.set("")

    def _duplicate_area(self):
        if self.current_selection_idx < 0:
            return
        orig = self.areas[self.current_selection_idx]
        import copy
        area_copy = copy.deepcopy(orig)

        # New Unique ID
        max_id = max((a.id for a in self.areas), default=0)
        area_copy.id = max_id + 1

        # Normalize subtitle colors on the copy (flattened area attributes)
        try:
            area_copy.colors = list(area_copy.colors or area_copy.colors or [])
        except Exception:
            area_copy.colors = list(area_copy.colors or [])
        
        self.areas.append(area_copy)
        self.config_mgr.set_areas(self.areas)
        self._refresh_list()
        if area_copy.rect:
            try:
                area_copy.rect = dict(area_copy.rect)
            except Exception:
                pass

        self.areas.append(area_copy)
        self.config_mgr.set_areas(self.areas)
        self._refresh_list()
        self.lb_areas.selection_clear(0, tk.END)
        self.lb_areas.selection_set(tk.END)
        self.current_selection_idx = len(self.areas) - 1
        self._load_details(self.current_selection_idx)

    def _test_current_settings(self):
        if self.current_selection_idx < 0:
            return
        if not self.subtitle_lines:
            messagebox.showerror(
                "Błąd", "Brak załadowanych napisów (plik tekstowy).")
            return

        area = self.areas[self.current_selection_idx]
        rect = area.rect
        if not rect:
            messagebox.showerror(
                "Błąd", "Obszar nie ma zdefiniowanych współrzędnych.")
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

            # rect in storage is expected to be in screen coordinates — use directly for cropping
            try:
                srect = {'left': int(rect.get('left', 0)), 'top': int(rect.get('top', 0)), 'width': int(
                    rect.get('width', 0)), 'height': int(rect.get('height', 0))}
            except Exception:
                srect = rect.copy()

            ox = srect['left']
            oy = srect['top']
            ow = srect['width']
            oh = srect['height']

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

            # Evaluate original: use flattened area attrs; produce a dict for optimizer
            settings_area = area
            pre_db = precompute_subtitles(self.subtitle_lines)
            optimizer = SettingsOptimizer()
            from app.matcher import MATCH_MODE_FULL
            try:
                mode = settings_area.subtitle_mode
            except Exception:
                mode = MATCH_MODE_FULL

            # Build a plain settings dict for the optimizer by reading authoritative
            # properties from the AreaConfig instance. We use private _to_dict for this
            # internal optimization step.
            settings_dict = settings_area._to_dict()

            score_original, _ = optimizer._evaluate_settings(
                normal_crop, settings_dict, pre_db, mode)

            # Evaluate expanded
            score_expanded, _ = optimizer._evaluate_settings(
                expanded_crop, settings_dict, pre_db, mode)

            # Logic: If expanded score is significantly better OR (if both are good, check bounds)
            # Actually, if we expand, we might catch garbage which lowers score.
            # But if we catch the FULL text which was cut off, score should improve.

            final_score = score_original
            expanded_better = False

            if score_expanded > score_original + 5:  # Threshold for "better"
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
                msg += "\n\nSłaby wynik."
                messagebox.showinfo("Wynik Testu", msg)

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
            r_old = area.rect
            old_w = r_old.get('width') if r_old else None
            old_h = r_old.get('height') if r_old else None
            if messagebox.askyesno("Korekta Obszaru",
                                   f"Wykryto tekst w szerszym obszarze.\n"
                                   f"Nowy wymiar: {bw}x{bh} (stary: {old_w}x{old_h})\n"
                                   "Czy zaktualizować granice obszaru?"):
                # Store proposed rect as screen coordinates
                r = area.rect or {}
                r['left'] = int(abs_x)
                r['top'] = int(abs_y)
                r['width'] = int(bw)
                r['height'] = int(bh)
                area.rect = r
                # Persist change via authoritative ConfigManager
                self.config_mgr.set_areas(self.areas)
                # Update UI
                self._load_details(self.current_selection_idx)

    def _save_and_close(self):
        try:
            if self.config_mgr and self.areas:
                self.config_mgr.set_areas(self.areas)
            self.destroy()
        except Exception as e:
            messagebox.showerror("Błąd zapisu", f"Nie udało się zapisać obszarów: {e}")


class OptimizationResultWindow(tk.Toplevel):
    # This class is now imported from app.optimization_result
    # The redundant implementation here is removed.
    pass
