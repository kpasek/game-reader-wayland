import tkinter as tk
from tkinter import ttk, messagebox
import os
from PIL import Image
from app.capture import capture_fullscreen
from app.area_selector import AreaSelector, ColorSelector
from app.matcher import MATCH_MODE_FULL, MATCH_MODE_STARTS, MATCH_MODE_PARTIAL
from app.gui_utils import create_tooltip

class OptimizationWizard(tk.Toplevel):
    def __init__(self, parent, on_start):
        super().__init__(parent)
        self.title("Optymalizacja Ustawień")
        self.geometry("600x600")
        
        # Shortcuts
        self.bind("<F4>", lambda e: self._add_with_selection())
        
        self.on_start = on_start
        self.frames = []
        self.current_area_data = None
        
        # UI
        main_f = ttk.Frame(self, padding=15)
        main_f.pack(fill=tk.BOTH, expand=True)
        
        ttk.Label(main_f, text="Kreator Optymalizacji", font=("Arial", 12, "bold")).pack(pady=10)
        instrukcja = (
            "Jak poprawnie zoptymalizować ustawienia:\n"
            "1. Najpierw dodaj zrzut ekranu, na którym napisy są dobrze widoczne – najlepiej taki, gdzie pojawia się cały tekst dialogu.\n"
            "2. Dodaj kolejne zrzuty, jeśli chcesz sprawdzić, czy znalezione ustawienia działają także w innych sytuacjach.\n"
            "3. Zaznacz na każdym zrzucie dokładnie ten fragment, gdzie pojawiają się napisy – im dokładniej, tym lepiej.\n"
            "4. Jeśli napisy w grze mają inny kolor niż biały, wybierz ten kolor – program domyślnie testuje biały.\n"
            "\n"
            "Im lepiej przygotujesz zrzuty i zaznaczysz napisy, tym lepszy będzie efekt optymalizacji!"
        )
        # Przycisk "Instrukcja" z tooltipem zamiast okna
        btn_instr = ttk.Label(main_f, text="❓ Instrukcja", foreground="blue", cursor="hand2")
        btn_instr.pack(anchor=tk.NE, pady=(0, 0), padx=(0, 5))
        create_tooltip(btn_instr, instrukcja)
        
        self.list_frame = ttk.Frame(main_f)
        self.list_frame.pack(fill=tk.BOTH, expand=True, pady=10)
        
        self.lb_screens = tk.Listbox(self.list_frame, height=6)
        self.lb_screens.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        btn_box = ttk.Frame(self.list_frame)
        btn_box.pack(side=tk.LEFT, fill=tk.Y, padx=5)
        
        self.btn_add_area = ttk.Button(btn_box, text="Zrób zrzut [F4]", command=self._add_with_selection)
        self.btn_add_area.pack(fill=tk.X, pady=2)
        
        self.btn_import = ttk.Button(btn_box, text="Importuj zrzuty", command=self._import_screenshot)
        self.btn_import.pack(fill=tk.X, pady=2)

        self.btn_rem = ttk.Button(btn_box, text="Usuń", command=self._remove_screenshot)
        self.btn_rem.pack(fill=tk.X, pady=2)
        
        # Options Frame
        opt_frame = ttk.LabelFrame(main_f, text="Ustawienia Wstępne", padding=10)
        opt_frame.pack(fill=tk.X, pady=5)
        
        # Match Mode
        ttk.Label(opt_frame, text="Sposób dopasowania:").pack(anchor=tk.W)
        self.var_match_mode = tk.StringVar(value="Pełne zdania")
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
        ttk.Label(opt_frame, text="Wymuś kolor (Np. dla niebieskich napisów):").pack(anchor=tk.W)
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

    def _pick_color(self):
        root = self.winfo_toplevel()
        self.withdraw()
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
            

    def _clear_color(self):
        self.var_color.set("")
        self.lbl_color_preview.config(bg="#eeeeee", text="Brak")

    def _add_with_selection(self):
        root = self.winfo_toplevel()
        self.withdraw()
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
            sel = AreaSelector(root, img)
            if sel.geometry:
                r = sel.geometry
                rect_tuple = (r['left'], r['top'], r['width'], r['height'])
                self.frames.append({"image": img, "rect": rect_tuple})
                self.lb_screens.insert(tk.END, f"Zrzut #{len(self.frames)} (Obszar: {rect_tuple})")
        except Exception as e:
            print(f"Error opening selector: {e}")
        finally:
            self.deiconify()
            

    def _import_screenshot(self):
        from tkinter import filedialog
        home = os.path.expanduser('~')
        paths = filedialog.askopenfilenames(title="Wybierz zrzut ekranu",
                          initialdir=home,
                          filetypes=[("Obrazy", "*.png *.jpg *.jpeg *.bmp"), ("Wszystkie", "*.*")], parent=self)
        if not paths:
             return
        
        root = self.winfo_toplevel()
        self.withdraw()
        self.update_idletasks()
        
        try:
            for path in paths:
                pil_img = Image.open(path).convert('RGB')
                sel = AreaSelector(root, pil_img)
                if sel.geometry:
                    r = sel.geometry
                    rect_tuple = (r['left'], r['top'], r['width'], r['height'])
                    self.frames.append({"image": pil_img, "rect": rect_tuple})
                    self.lb_screens.insert(tk.END, f"Import - Obszar: {rect_tuple}")
        except Exception as e:
            messagebox.showerror("Błąd", f"Błąd importu: {e}")
        finally:
            self.deiconify()
            

    def _remove_screenshot(self):
        sel = self.lb_screens.curselection()
        if not sel: return
        idx = sel[0]
        del self.frames[idx]
        self.lb_screens.delete(0, tk.END)
        for i, f in enumerate(self.frames):
             info = f" (Obszar: {f['rect']})"
             self.lb_screens.insert(tk.END, f"Zrzut #{i+1}{info}")

    def _start_opt(self):
        if not self.frames:
            return

        disp_mode = self.var_match_mode.get()
        mode = self.mode_map.get(disp_mode, MATCH_MODE_FULL)
        color = self.var_color.get() if self.var_color.get() != "" else None

        frames = self.frames
        callback = self.on_start
        self.destroy()
        callback(frames, mode=mode, initial_color=color)
