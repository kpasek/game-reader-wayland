import tkinter as tk
from tkinter import messagebox
from app.ctk_widgets import (
    make_frame, make_label, make_button, make_combobox, 
    CTkToplevel, make_labelframe, make_notebook, make_notebook_tab,
    make_checkbutton, make_scale, make_entry
)
import os
from PIL import Image
from app.capture import capture_fullscreen
from app.area_selector import AreaSelector, ColorSelector
from app.matcher import MATCH_MODE_FULL, MATCH_MODE_STARTS, MATCH_MODE_PARTIAL
from app.gui_utils import create_tooltip

class OptimizationWizard(CTkToplevel):
    def __init__(self, parent, on_start):
        super().__init__(parent)
        self.title("Optymalizacja Ustawień")
        self.geometry("1000x850")
        
        # Shortcuts
        self.bind("<F4>", lambda e: self._add_with_selection())
        
        self.on_start = on_start
        self.frames = []
        self.current_area_data = None
        
        # Main layout replacing previous main_f
        self.notebook = make_notebook(self)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        self.tab_detection = make_notebook_tab(self.notebook, "Wykrywanie")
        self.tab_advanced = make_notebook_tab(self.notebook, "Zaawansowane")
        self.tab_instruction = make_notebook_tab(self.notebook, "Instrukcja")
        
        self._build_detection_tab()
        self._build_advanced_tab()
        self._build_instruction_tab()

    def _build_detection_tab(self):
        main_f = make_frame(self.tab_detection, padding=20)
        main_f.pack(fill=tk.BOTH, expand=True)

        make_label(main_f, text="Kreator Optymalizacji", font=("Arial", 12, "bold")).pack(pady=(0, 10))
        
        self.list_frame = make_frame(main_f, fg_color="transparent")
        self.list_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 15))
        
        from app.ctk_widgets import make_listbox
        self.lb_screens = make_listbox(self.list_frame, height=6)
        self.lb_screens.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        btn_box = make_frame(self.list_frame)
        btn_box.pack(side=tk.LEFT, fill=tk.Y, padx=5)

        self.btn_add_area = make_button(btn_box, text="Zrób zrzut [F4]", command=self._add_with_selection, fg_color="#1f6aa5", hover_color="#145f8a", text_color="#ffffff")
        self.btn_add_area.pack(fill=tk.X, pady=(0, 5))
        self.btn_import = make_button(btn_box, text="Importuj zrzuty", command=self._import_screenshot, fg_color="#1f6aa5", hover_color="#145f8a", text_color="#ffffff")
        self.btn_import.pack(fill=tk.X, pady=(0, 5))

        self.btn_rem = make_button(btn_box, text="Usuń", command=self._remove_screenshot, fg_color="#c0392b", hover_color="#992d22", text_color="#ffffff")
        self.btn_rem.pack(fill=tk.X, pady=(0, 5))
        
        # Options Frame
        opt_frame = make_labelframe(main_f, text="Ustawienia Wstępne", padding=15)
        opt_frame.pack(fill=tk.X, pady=(0, 15))
        
        # Match Mode
        make_label(opt_frame, text="Sposób dopasowania:").pack(anchor=tk.W)
        self.var_match_mode = tk.StringVar(value="Pełne zdania")
        self.mode_map = {
            "Pełne zdania": MATCH_MODE_FULL, 
            "Zaczyna się od": MATCH_MODE_STARTS,
            "Częściowe": MATCH_MODE_PARTIAL
        }
        self.mode_map_reverse = {v: k for k, v in self.mode_map.items()}
        modes = list(self.mode_map.keys())
        cb_mode = make_combobox(opt_frame, textvariable=self.var_match_mode, values=modes, state="readonly")
        cb_mode.pack(fill=tk.X, pady=(0, 5))
        
        # Color Picker
        make_label(opt_frame, text="Wymuś kolor (Np. dla niebieskich napisów):").pack(anchor=tk.W)
        self.var_color = tk.StringVar(value="#FFFFFF")
        
        col_frame = make_frame(opt_frame, fg_color="transparent")
        col_frame.pack(fill=tk.X, pady=(5, 0))

        # Color preview uses a plain tk.Label to allow background color changes
        initial_bg = self.var_color.get() or "#FFFFFF"
        self.lbl_color_preview = tk.Label(col_frame, text="", font=("Arial", 8), width=10, bg=initial_bg)
        self.lbl_color_preview.pack(side=tk.LEFT, padx=(0, 5))

        make_button(col_frame, text="Wybierz...", command=self._pick_color, fg_color="#1f6aa5", hover_color="#145f8a", text_color="#ffffff").pack(side=tk.LEFT)
        make_button(col_frame, text="X", width=5, command=self._clear_color, fg_color="#c0392b", hover_color="#992d22", text_color="#ffffff").pack(side=tk.LEFT, padx=5)
        
        # Start
        self.btn_run = make_button(main_f, text="Uruchom Optymalizację", command=self._start_opt, fg_color="#27ae60", hover_color="#1e8449", text_color="#ffffff")
        self.btn_run.pack(pady=10, fill=tk.X)

    def _build_advanced_tab(self):
        f = make_frame(self.tab_advanced, padding=20)
        f.pack(fill=tk.BOTH, expand=True)

        make_label(f, text="Tryby poszukiwania", font=("Arial", 11, "bold")).pack(anchor=tk.W, pady=(0, 5))
        
        self.var_use_color = tk.BooleanVar(value=True)
        self.var_use_brightness = tk.BooleanVar(value=False)

        cb_color = make_checkbutton(f, text="Włącz szukanie po kolorze tekstu (Zalecane)", variable=self.var_use_color)
        cb_color.pack(anchor=tk.W, pady=2)
        cb_bright = make_checkbutton(f, text="Włącz szukanie po jasności ekranu (Wolniejsze)", variable=self.var_use_brightness)
        cb_bright.pack(anchor=tk.W, pady=2)

        make_label(f, text="Zakresy tolerancji (Min - Max)", font=("Arial", 11, "bold")).pack(anchor=tk.W, pady=(15, 5))

        # Color Mode
        lf_color = make_labelframe(f, text="Kolor: Tolerancja kolorów [1-100]")
        lf_color.pack(fill=tk.X, pady=5)
        self.var_color_tol_min = tk.IntVar(value=1)
        self.var_color_tol_max = tk.IntVar(value=30)
        self._make_range_slider(lf_color, self.var_color_tol_min, self.var_color_tol_max, 1, 100)
        
        # Brightness Mode
        lf_bright = make_labelframe(f, text="Jasność: Próg jasności [100-255]")
        lf_bright.pack(fill=tk.X, pady=5)
        self.var_bright_min = tk.IntVar(value=150)
        self.var_bright_max = tk.IntVar(value=255)
        self._make_range_slider(lf_bright, self.var_bright_min, self.var_bright_max, 100, 255)

        # Common 
        lf_common = make_labelframe(f, text="Wspólne parametry")
        lf_common.pack(fill=tk.X, pady=5)

        make_label(lf_common, text="Pogrubienie czcionki [0-3 px]").pack(anchor=tk.W, pady=(5,0))
        self.var_thick_min = tk.IntVar(value=0)
        self.var_thick_max = tk.IntVar(value=1)
        self._make_range_slider(lf_common, self.var_thick_min, self.var_thick_max, 0, 3, step=1)

        make_label(lf_common, text="Kontrast [Mnożnik]").pack(anchor=tk.W, pady=(5,0))
        self.var_cont_min = tk.DoubleVar(value=0.0)
        self.var_cont_max = tk.DoubleVar(value=2.0)
        self._make_range_slider(lf_common, self.var_cont_min, self.var_cont_max, 0.0, 5.0, step=0.1)

        make_label(lf_common, text="Skala wewn. OCR [Mnożnik]").pack(anchor=tk.W, pady=(5,0))
        self.var_scale_min = tk.DoubleVar(value=0.3)
        self.var_scale_max = tk.DoubleVar(value=0.75)
        self._make_range_slider(lf_common, self.var_scale_min, self.var_scale_max, 0.1, 2.0, step=0.05)


    def _make_range_slider(self, parent, var_min, var_max, min_val, max_val, is_grid=False, row=0, step=1):
        f = make_frame(parent, fg_color="transparent")
        f.pack(fill=tk.X, padx=10, pady=5)

        is_float = isinstance(step, float)
        fmt = "{:.2f}" if is_float else "{:.0f}"

        lbl_min = make_label(f, text="Min:")
        lbl_min.grid(row=0, column=0, padx=(0, 10))
        scale_min = make_scale(f, from_=min_val, to=max_val, variable=var_min)
        scale_min.grid(row=0, column=1, sticky='ew', padx=5, pady=2)
        val_min = make_label(f, text=fmt.format(var_min.get()), width=40)
        val_min.grid(row=0, column=2, padx=(10, 0))

        lbl_max = make_label(f, text="Max:")
        lbl_max.grid(row=1, column=0, padx=(0, 10))
        scale_max = make_scale(f, from_=min_val, to=max_val, variable=var_max)
        scale_max.grid(row=1, column=1, sticky='ew', padx=5, pady=2)
        val_max = make_label(f, text=fmt.format(var_max.get()), width=40)
        val_max.grid(row=1, column=2, padx=(10, 0))

        f.columnconfigure(1, weight=1)

        def update_labels(*args):
            # enforce limits (cross-over)
            if var_min.get() > var_max.get():
                if args and len(args) > 0 and args[0] == str(var_min): # min driven
                    var_min.set(var_max.get())
                else:
                    var_max.set(var_min.get())
                    
            if not is_float:
                # Snap to int
                var_min.set(int(round(var_min.get())))
                var_max.set(int(round(var_max.get())))
                
            val_min.configure(text=fmt.format(var_min.get()))
            val_max.configure(text=fmt.format(var_max.get()))

        scale_min.configure(command=lambda v: update_labels())
        scale_max.configure(command=lambda v: update_labels())
        # Initial update
        update_labels()

    def _build_instruction_tab(self):
        f = make_frame(self.tab_instruction, padding=20)
        f.pack(fill=tk.BOTH, expand=True)

        instrukcja = (
            "Jak poprawnie zoptymalizować ustawienia:\n\n"
            "1. Najpierw dodaj zrzut ekranu, na którym napisy są dobrze widoczne\n"
            "   – najlepiej taki, gdzie pojawia się cały tekst dialogu.\n"
            "2. Dodaj kolejne zrzuty, jeśli chcesz sprawdzić, czy znalezione\n"
            "   ustawienia działają także w innych sytuacjach.\n"
            "3. Zaznacz na każdym zrzucie dokładnie ten fragment, gdzie pojawiają\n"
            "   się napisy – im dokładniej, tym lepiej.\n"
            "4. Jeśli napisy w grze mają inny kolor niż biały, wybierz ten kolor\n"
            "   – program domyślnie testuje biały.\n\n"
            "ZAAWANSOWANE:\n"
            "Możesz przejść do zakładki 'Zaawansowane', aby zawęzić lub poszerzyć\n"
            "zakres parametrów (tolerancja koloru, kontrast, skala OCR), które\n"
            "są używane przy poszukiwaniu najlepszych ustawień. Opcje te\n"
            "pozwalają znaleźć bardziej specyficzne konfiguracje lub\n"
            "przyspieszyć proces przy mniejszym zakresie poszukiwań.\n\n"
            "Im lepiej przygotujesz zrzuty i zaznaczysz napisy, tym lepszy\n"
            "będzie efekt optymalizacji!"
        )
        
        # We can use a Text widget or Label for scrollable text
        # Since it's not a huge text, a normal Label inside a layout or disabled Text is good.
        text_widget = tk.Text(f, wrap="word", bg=self._get_bg_color(), fg=self._get_fg_color(), font=("Arial", 11), borderwidth=0, highlightthickness=0)
        text_widget.insert("1.0", instrukcja)
        text_widget.config(state="disabled")
        text_widget.pack(fill=tk.BOTH, expand=True)

    def _get_bg_color(self):
        try:
            import customtkinter as ctk
            if ctk.get_appearance_mode() == 'Dark': return '#2b2b2b'
        except: pass
        return '#ffffff'

    def _get_fg_color(self):
        try:
            import customtkinter as ctk
            if ctk.get_appearance_mode() == 'Dark': return '#eaeaea'
        except: pass
        return '#000000'

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
            if hasattr(self, 'area_manager') and self.area_manager: self.area_manager.deiconify()
            return
            
        try:
            sel = ColorSelector(root, img)
            if sel.selected_color:
                hex_color = sel.selected_color
                self.var_color.set(hex_color)
                self.lbl_color_preview.configure(bg=hex_color, text="")
        except Exception as e:
            print(f"Error picking color: {e}")
        finally:
            self.deiconify()

    def _clear_color(self):
        self.var_color.set("")
        self.lbl_color_preview.configure(bg="#eeeeee", text="Brak")

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
            if hasattr(self, 'area_manager') and self.area_manager: self.area_manager.deiconify()
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

        advanced_settings = {
            "use_color_mode": self.var_use_color.get(),
            "use_brightness_mode": self.var_use_brightness.get(),
            "color_tol_min": self.var_color_tol_min.get(),
            "color_tol_max": self.var_color_tol_max.get(),
            "bright_min": self.var_bright_min.get(),
            "bright_max": self.var_bright_max.get(),
            "thick_min": self.var_thick_min.get(),
            "thick_max": self.var_thick_max.get(),
            "cont_min": self.var_cont_min.get(),
            "cont_max": self.var_cont_max.get(),
            "scale_min": self.var_scale_min.get(),
            "scale_max": self.var_scale_max.get(),
        }

        frames = self.frames
        callback = self.on_start
        self.destroy()
        # callback teraz powinno pobierać kwargs z advanced settings; ponieważ lektor.py on_wizard_finish spodziewa się
        # stałej sygnatury (uruchamianie optimizer.optimize), powinniśmy przekazać to jako nową właściwość lub rozszerzyć arguments
        # W lektor.py callback on_wizard_finish() przyjmuje tylko 3 argumenty, więc wstrzykniemy w ten sam dictionary co kwargs lub przekażemy
        # przez dodatkowy opcjonalny argument initial_color a nowo jako dict -> To wpłynie na zmianę w lektor.py
        # Aby uniknąć modyfikowania w wielu miejscach, przekażemy advanced_settings jako dodatkowy **kwargs argument w on_wizard_finish
        callback(frames, mode=mode, initial_color=color, advanced_settings=advanced_settings)
