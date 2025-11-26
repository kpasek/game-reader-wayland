#!/usr/bin/env python3

import json
import os
import sys
import time
import subprocess
import threading
import queue
import argparse
from typing import List, Dict, Any, Optional
from app.area_selector import AreaSelector
from app.log import LogWindow
from app.player import PlayerThread
from app.reader import ReaderThread
from app.settings import SettingsDialog
from app.utils import _capture_fullscreen_image


try:
    import tkinter as tk
    from tkinter import ttk
    from tkinter import filedialog
    from tkinter import messagebox
except ImportError:
    print("Błąd: Nie znaleziono biblioteki 'tkinter'.", file=sys.stderr)
    print("Zazwyczaj jest dołączona do Pythona. W Debian/Ubuntu: sudo apt install python3-tk", file=sys.stderr)
    sys.exit(1)

APP_CONFIG_FILE = 'app_config.json'

audio_queue = queue.Queue()
log_queue = queue.Queue()
stop_event = threading.Event()

class GameReaderApp:
    def __init__(self, root: tk.Tk, autostart_preset: Optional[str], game_command: Optional[List[str]]):        
        self.root = root
        self.root.title("Game Reader (Wayland)")
        self.root.geometry("700x520")

        self.preset_var = tk.StringVar()
        self.audio_dir_var = tk.StringVar()
        self.subtitles_file_var = tk.StringVar()
        self.names_file_var = tk.StringVar()

        self.regex_mode_var = tk.StringVar()
        self.custom_regex_var = tk.StringVar()

        self.resolutions = {
            "1080p (1920x1080)": (1920, 1080),
            "1440p (2560x1440)": (2560, 1440),
            "4K (3840x2160)": (3840, 2160),
            "800p (1280x800)": (1280, 800),
            "1600p (2560x1600)": (2560, 1600),
            "Niestandardowa": None
        }

        self.audio_speed_var = tk.DoubleVar(value=1.15)
        self.audio_volume_var = tk.DoubleVar(value=1.0)
        self.resolution_var = tk.StringVar()

        self.log_queue = queue.Queue()
        self.log_window_ref = None

        self.autostart_preset = autostart_preset
        self.game_command = game_command
        self.game_process = None

        self.settings = {}

        self.reader_thread: Optional[ReaderThread] = None
        self.player_thread: Optional[PlayerThread] = None

        self.audio_dir_var = tk.StringVar()
        self.subtitles_file_var = tk.StringVar()
        self.names_file_var = tk.StringVar()
        self.regex_patterns = {
            "Brak": r"",
            "Standardowy (Imie: Kwestia)": r"^(?i)({NAMES})\s*[:：\-; ]*",
            "W nawiasach ([Imie] Kwestia)": r"^\[({NAMES})\]",
            "Samo imię na początku": r"^({NAMES})\s+",
            "Inny (wpisz własny)": "CUSTOM"
        }

        self.create_menu()
        self.build_ui()
        
        # --- Załaduj konfigurację ---
        self.settings = self.load_app_config()
        self.update_gui_from_config()
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

        # --- Logika Autostartu ---
        if self.autostart_preset:
            if os.path.exists(self.autostart_preset):
                print(f"Wykryto autostart z presetem: {self.autostart_preset}")
                self.preset_var.set(self.autostart_preset)
                self.on_preset_selected() # Ręczne wywołanie, aby załadować ścieżki
                # Użyj 'after', aby dać GUI chwilę na "złapanie oddechu"
                self.root.after(100, self.start_reading)
            else:
                print(
                    f"BŁĄD Autostartu: Plik presetu nie istnieje: {self.autostart_preset}")

    def create_menu(self):
        """Tworzy pasek menu dla aplikacji."""
        menubar = tk.Menu(self.root)
        
        # --- Menu Plik ---
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Ustawienia",
                              command=self.open_settings_dialog)
        file_menu.add_separator()
        file_menu.add_command(label="Wyjdź", command=self.on_closing)
        menubar.add_cascade(label="Plik", menu=file_menu)

        # --- Preset ---
        preset_menu = tk.Menu(menubar, tearoff=0)
        preset_menu.add_command(label="Wybierz nowego lektora", command=self.select_new_preset)

        # Podmenu Obszarów
        areas_menu = tk.Menu(preset_menu, tearoff=0)
        for i in range(3):
            sub_area = tk.Menu(areas_menu, tearoff=0)
            sub_area.add_command(label=f"Ustaw Obszar {i + 1}", command=lambda idx=i: self.manage_area(idx, 'set'))
            sub_area.add_command(label=f"Wyczyść Obszar {i + 1}", command=lambda idx=i: self.manage_area(idx, 'clear'))
            areas_menu.add_cascade(label=f"Obszar {i + 1}", menu=sub_area)

        preset_menu.add_cascade(label="Zarządzaj obszarami", menu=areas_menu)
        preset_menu.add_separator()
        preset_menu.add_command(label="Zmień katalog audio", command=self.select_audio_dir)
        preset_menu.add_command(label="Zmień plik napisów", command=self.select_subtitles_file)
        preset_menu.add_command(label="Zmień plik imion", command=self.select_names_file)
        menubar.add_cascade(label="Preset", menu=preset_menu)

        # --- Menu Narzędzia ---
        tools_menu = tk.Menu(menubar, tearoff=0)
        tools_menu.add_command(label="Pokaż logi", command=self.open_log_window)  # NOWE
        tools_menu.add_command(label="Generuj polecenie startowe Steam", command=self.generate_steam_command)

        menubar.add_cascade(label="Narzędzia", menu=tools_menu)
        
        # --- Menu Pomoc ---
        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="Zapisz logi dopasowań...",
                              command=self.save_logs)
        help_menu.add_separator()
        help_menu.add_command(label="O programie...", 
                              command=self.show_about)
        menubar.add_cascade(label="Pomoc", menu=help_menu)

        self.root.config(menu=menubar)

    def build_ui(self):
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Sekcja Presetu
        ttk.Label(main_frame, text="Wybierz lektora (Preset)").pack(anchor=tk.W)
        self.preset_combo = ttk.Combobox(main_frame, textvariable=self.preset_var, state="readonly", width=60)
        self.preset_combo.pack(fill=tk.X, pady=5)
        self.preset_combo.bind("<<ComboboxSelected>>", self.on_preset_selected)

        # Sekcja Regex
        ttk.Label(main_frame, text="Filtr dialogów").pack(anchor=tk.W, pady=(10, 0))
        regex_frame = ttk.Frame(main_frame)
        regex_frame.pack(fill=tk.X, pady=5)
        self.regex_combo = ttk.Combobox(regex_frame, textvariable=self.regex_mode_var,
                                        values=list(self.regex_patterns.keys()), state="readonly", width=35)
        self.regex_combo.pack(side=tk.LEFT, padx=(0, 5))
        self.regex_combo.bind("<<ComboboxSelected>>", lambda e: self._toggle_regex_entry())
        self.custom_regex_entry = ttk.Entry(regex_frame, textvariable=self.custom_regex_var)
        self.custom_regex_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # Sekcja Rozdzielczości
        ttk.Label(main_frame, text="Docelowa rozdzielczość gry:").pack(anchor=tk.W, pady=(10, 0))
        self.res_combo = ttk.Combobox(main_frame, textvariable=self.resolution_var,
                                      values=list(self.resolutions.keys()), width=60)
        self.res_combo.pack(fill=tk.X, pady=5)

        # Sekcja Sterowania Audio (Prędkość i Głośność)
        audio_frame = ttk.LabelFrame(main_frame, text="Ustawienia Audio", padding=10)
        audio_frame.pack(fill=tk.X, pady=10)

        # Prędkość
        ttk.Label(audio_frame, text="Prędkość:").grid(row=0, column=0, padx=5, sticky=tk.W)
        self.speed_scale = ttk.Scale(audio_frame, from_=0.8, to=2.0, variable=self.audio_speed_var,
                                     command=lambda v: self.speed_lbl.config(text=f"{float(v):.2f}x"))
        self.speed_scale.grid(row=0, column=1, sticky="ew", padx=5)
        self.speed_scale.bind("<ButtonRelease-1>",
                              lambda e: self._auto_save_to_preset("audio_speed", round(self.audio_speed_var.get(), 2)))
        self.speed_lbl = ttk.Label(audio_frame, text="1.15x", width=6)
        self.speed_lbl.grid(row=0, column=2)

        # Głośność (NOWE)
        ttk.Label(audio_frame, text="Głośność:").grid(row=1, column=0, padx=5, sticky=tk.W)
        self.vol_scale = ttk.Scale(audio_frame, from_=0.5, to=1.5, variable=self.audio_volume_var,
                                   command=lambda v: self.vol_lbl.config(text=f"{float(v):.2f}"))
        self.vol_scale.grid(row=1, column=1, sticky="ew", padx=5)
        self.vol_scale.bind("<ButtonRelease-1>",
                            lambda e: self._auto_save_to_preset("audio_volume", round(self.audio_volume_var.get(), 2)))
        self.vol_lbl = ttk.Label(audio_frame, text="1.00", width=6)
        self.vol_lbl.grid(row=1, column=2)

        audio_frame.columnconfigure(1, weight=1)

        # Przyciski Start/Stop
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=10, side=tk.BOTTOM)
        self.start_button = ttk.Button(btn_frame, text="Uruchom", command=self.start_reading)
        self.start_button.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=5)
        self.stop_button = ttk.Button(btn_frame, text="Zatrzymaj", command=self.stop_reading, state="disabled")
        self.stop_button.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=5)

        self.regex_combo.bind("<<ComboboxSelected>>", self.on_regex_change)
        self.custom_regex_entry.bind("<FocusOut>", self.on_custom_regex_save)

    def generate_steam_command(self):
        preset_path = self.preset_var.get()
        if not preset_path or not os.path.exists(preset_path):
            messagebox.showerror("Błąd", "Wybierz istniejący preset.")
            return

        try:
            abs_preset_path = os.path.abspath(preset_path)
            # Używamy sys.argv[0] jako ścieżki do skryptu/exe
            script_path = os.path.abspath(sys.argv[0])

            # Budowa polecenia: python main.py --preset "..." %command%
            # Lub jeśli skompilowane: ./main --preset "..." %command%

            if script_path.endswith('.py'):
                cmd_base = f'python3 "{script_path}"'
            else:
                cmd_base = f'"{script_path}"'

            command = f'{cmd_base} --preset "{abs_preset_path}" %command%'

            # Wyświetl okno z polem do kopiowania (niezawodne na Linuxie)
            win = tk.Toplevel(self.root)
            win.title("Polecenie Steam")
            win.geometry("600x150")

            ttk.Label(win, text="Skopiuj poniższą linię do opcji uruchamiania gry na Steam:").pack(pady=10)

            entry = ttk.Entry(win, width=80)
            entry.pack(padx=10, pady=5)
            entry.insert(0, command)
            entry.select_range(0, tk.END)  # Zaznacz wszystko

            # Próba autokopiowania
            try:
                self.root.clipboard_clear()
                self.root.clipboard_append(command)
                self.root.update()  # Ważne dla Wayland!
                ttk.Label(win, text="(Próbowano skopiować automatycznie do schowka)", font=("Arial", 8)).pack()
            except:
                pass

            ttk.Button(win, text="Zamknij", command=win.destroy).pack(pady=10)

        except Exception as e:
            messagebox.showerror("Błąd", f"Wystąpił błąd: {e}")

    def select_area_for_preset(self):
        preset_path = self.preset_var.get()
        if not preset_path or not os.path.exists(preset_path):
            messagebox.showerror("Błąd", "Wybierz preset.")
            return

        self.root.withdraw()
        time.sleep(0.5)

        # Pobieranie zrzutu ekranu raz
        screenshot = _capture_fullscreen_image()
        if not screenshot:
            self.root.deiconify()
            return

        screen_w, screen_h = screenshot.size
        # Baza 1080p (standard zapisu w tym programie)
        base_w, base_h = 1920, 1080

        # Skalowanie do zapisu (Twój Ekran -> 1080p)
        save_scale_x = base_w / screen_w
        save_scale_y = base_h / screen_h

        # Skalowanie do odczytu/wyświetlania (1080p -> Twój Ekran)
        load_scale_x = screen_w / base_w
        load_scale_y = screen_h / base_h

        new_monitors_for_save = []  # Lista przeskalowana (do zapisu w JSON)
        current_session_raw = []  # Lista surowa (to co właśnie zaznaczyłeś)
        old_regions_raw = []  # Lista surowa (to co było w pliku)

        try:
            with open(preset_path, 'r', encoding='utf-8') as f:
                saved_data = json.load(f)

            saved_mons = saved_data.get('monitor', [])
            # Obsługa przypadku, gdy monitor jest słownikiem, a nie listą
            if isinstance(saved_mons, dict):
                saved_mons = [saved_mons]

            for m in saved_mons:
                if not m: continue
                # Przeliczamy z 1080p na obecny ekran, żeby wyświetlić poprawnie
                old_regions_raw.append({
                    'left': int(m.get('left', 0) * load_scale_x),
                    'top': int(m.get('top', 0) * load_scale_y),
                    'width': int(m.get('width', 0) * load_scale_x),
                    'height': int(m.get('height', 0) * load_scale_y)
                })
        except Exception as e:
            print(f"Nie udało się wczytać podglądu starych obszarów: {e}")

        # --- KROK 2: Pętla dodawania nowych obszarów ---
        for i in range(3):
            # Wyświetlamy stare (z pliku) ORAZ te dodane w tej sesji
            regions_to_show = old_regions_raw + current_session_raw

            title = f"Wybór obszaru {i + 1}/3"
            print(title)

            # Przekazujemy sumę obszarów do wyświetlenia
            selector = AreaSelector(self.root, screenshot, existing_regions=regions_to_show)
            geom = selector.geometry

            if geom:
                # Dodajemy surową geometrię do listy "właśnie dodane"
                current_session_raw.append(geom)

                # Skalowanie do bazy 1080p dla zapisu
                scaled_geom = {
                    'left': int(geom['left'] * save_scale_x),
                    'top': int(geom['top'] * save_scale_y),
                    'width': int(geom['width'] * save_scale_x),
                    'height': int(geom['height'] * save_scale_y)
                }
                new_monitors_for_save.append(scaled_geom)

                # Pytanie o kolejny obszar
                if i < 2:
                    if not messagebox.askyesno("Kolejny obszar?",
                                               f"Zdefiniowano obszar {i + 1}. Czy chcesz dodać kolejny (np. u góry ekranu)?"):
                        break
            else:
                # Anulowanie wyboru przerywa proces
                break

        self.root.deiconify()
        if screenshot: screenshot.close()

        # --- KROK 3: Zapis ---
        if new_monitors_for_save:
            try:
                with open(preset_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                # Nadpisujemy stare obszary nowymi (skalowanymi do 1080p)
                data['monitor'] = new_monitors_for_save
                data['resolution'] = "1920x1080"

                with open(preset_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=4)

                messagebox.showinfo("Sukces", f"Zapisano {len(new_monitors_for_save)} obszar(y).")
            except Exception as e:
                messagebox.showerror("Błąd", f"Nie udało się zapisać presetu: {e}")

    def open_settings_dialog(self):
        """Otwiera okno ustawień i zapisuje zmiany."""
        dialog = SettingsDialog(
            self.root, self.settings.copy())  # type: ignore
        if dialog.result:
            self.settings = dialog.result  # Pobierz zaktualizowane
            self.save_app_config()  # Zapisz do pliku
            print("Zapisano nowe ustawienia.")

    def load_app_config(self) -> Dict[str, Any]:
        """Wczytuje konfigurację aplikacji i ZWRACA ją."""
        config = {
            'recent_presets': [],
            'last_regex': r"^(?i)({NAMES})\s*[:：]",
            'subtitle_mode': 'Full Lines',
            'ocr_scale_factor': 1.0,
            'ocr_grayscale': False,
            'ocr_contrast': False,
            'last_resolution_key': 'Niestandardowa (z presetu)'
        }
        if 'last_regex_mode' not in config: config['last_regex_mode'] = list(self.regex_patterns.keys())[0]
        if 'last_custom_regex' not in config: config['last_custom_regex'] = r"^(?i)({NAMES})\s*[:：]"
        try:
            with open(APP_CONFIG_FILE, 'r', encoding='utf-8') as f:
                config_from_file = json.load(f)
                config.update(config_from_file)
        except FileNotFoundError:
            print("Plik app_config.json nie znaleziony, tworzę domyślny.")
        except json.JSONDecodeError:
            print("Błąd odczytu app_config.json, używam domyślnych.")
            
        return config

    def save_app_config(self, new_preset: Optional[str] = None):
        """Zapisuje listę presetów, regex i rozdzielczość do pliku JSON."""
        if new_preset:
             if new_preset in self.settings['recent_presets']:
                self.settings['recent_presets'].remove(new_preset)
             self.settings['recent_presets'].insert(0, new_preset)
             self.settings['recent_presets'] = self.settings['recent_presets'][:10]

        # Zapisywanie nowych pól
        self.settings['last_regex_mode'] = self.regex_mode_var.get()
        self.settings['last_custom_regex'] = self.custom_regex_var.get()
        # Zapisujemy to co jest wpisane w Combobox (nawet jak to custom string "1366x768")
        self.settings['last_resolution_key'] = self.resolution_var.get()

        try:
            with open(APP_CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.settings, f, indent=2)
        except Exception as e:
            print(f"Błąd zapisu app_config.json: {e}", file=sys.stderr)

    def update_gui_from_config(self):
        self.preset_combo['values'] = self.settings.get('recent_presets', [])
        if self.settings.get('recent_presets'): self.preset_var.set(self.settings['recent_presets'][0])
        self.regex_mode_var.set(self.settings.get('last_regex_mode', list(self.regex_patterns.keys())[0]))
        self.custom_regex_var.set(self.settings.get('last_custom_regex', ""))
        self.resolution_var.set(self.settings.get('last_resolution_key', "Niestandardowa"))
        self._toggle_regex_entry()
        self.on_preset_selected()

    def select_new_preset(self):
        """Otwiera dialog wyboru pliku i dodaje go do listy."""
        path = filedialog.askopenfilename(
            title="Wybierz plik presetu",
            filetypes=[("Preset JSON", "*.json"), ("Wszystkie pliki", "*.*")]
        )
        if path:
            self.save_app_config(new_preset=path) # Zapisz stary stan
            self.update_gui_from_config() # Wczytaj nowy
            self.preset_var.set(path) # Ustaw nowo wybrany jako aktywny
            self.on_preset_selected() # Zaktualizuj ścieżki
            
    # --- Funkcje do zarządzania ścieżkami (teraz wywoływane z menu) ---

    def on_preset_selected(self, event=None):
        path = self.preset_var.get()
        if not path or not os.path.exists(path): return

        self._ensure_preset_1080p(path)  # Tu też poprawka w logice

        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self.audio_dir_var.set(data.get('audio_dir', ''))
            self.subtitles_file_var.set(data.get('text_file_path', ''))
            self.names_file_var.set(data.get('names_file_path', ''))

            # Wczytywanie prędkości i głośności
            speed = data.get("audio_speed", 1.15)
            self.audio_speed_var.set(speed)
            self.speed_lbl.config(text=f"{speed}x")

            volume = data.get("audio_volume", 1.0)
            self.audio_volume_var.set(volume)
            self.vol_lbl.config(text=f"{volume:.2f}")

            # Regex
            rmode = data.get("regex_mode_name", list(self.regex_patterns.keys())[0])
            self.regex_mode_var.set(rmode)
            if rmode == "Inny (wpisz własny)": self.custom_regex_var.set(data.get("regex_pattern", ""))
            self._toggle_regex_entry()

        except Exception:
            pass

    def select_audio_dir(self):
        current_dir = self.audio_dir_var.get()
        path = filedialog.askdirectory(
            title="Wybierz folder z plikami audio",
            initialdir=current_dir if os.path.isdir(current_dir) else None
        )
        if path:
            self.audio_dir_var.set(path)
            self._update_preset_field('audio_dir', path) # AUTO-ZAPIS
            messagebox.showinfo("Zapisano", f"Zmieniono i zapisano katalog audio:\n{path}", master=self.root)

    def select_subtitles_file(self):
        current_file = self.subtitles_file_var.get()
        path = filedialog.askopenfilename(
            title="Wybierz plik z napisami",
            filetypes=[("Pliki tekstowe", "*.txt"), ("Wszystkie pliki", "*.*")],
            initialfile=current_file if os.path.isfile(current_file) else None
        )
        if path:
            self.subtitles_file_var.set(path)
            self._update_preset_field('text_file_path', path) # AUTO-ZAPIS
            messagebox.showinfo("Zapisano", f"Zmieniono i zapisano plik napisów:\n{os.path.basename(path)}", master=self.root)

    def select_names_file(self):
        current_file = self.names_file_var.get()
        path = filedialog.askopenfilename(
            title="Wybierz plik z imionami (opcjonalnie)",
            filetypes=[("Pliki tekstowe", "*.txt"), ("Wszystkie pliki", "*.*")],
            initialfile=current_file if os.path.isfile(current_file) else None
        )
        if path:
            self.names_file_var.set(path)
            self._update_preset_field('names_file_path', path) # AUTO-ZAPIS
            messagebox.showinfo("Zapisano", f"Zmieniono i zapisano plik imion:\n{os.path.basename(path)}", master=self.root)
            
    def save_paths_to_preset(self):
        """Zapisuje ścieżki ze zmiennych z powrotem do pliku presetu."""
        preset_path = self.preset_var.get()
        if not preset_path or not os.path.exists(preset_path):
            messagebox.showerror("Błąd", "Nie wybrano prawidłowego pliku presetu do zapisu.")
            return

        try:
            # Wczytaj plik
            with open(preset_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Pobierz nowe wartości ze zmiennych
            data['audio_dir'] = self.audio_dir_var.get()
            data['text_file_path'] = self.subtitles_file_var.get()
            data['names_file_path'] = self.names_file_var.get()
            
            # Zapisz plik
            with open(preset_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4)
                
            messagebox.showinfo("Sukces", f"Plik presetu '{os.path.basename(preset_path)}' został zaktualizowany.")

        except Exception as e:
            print(f"BŁĄD: Nie można zapisać presetu {preset_path}: {e}", file=sys.stderr)
            messagebox.showerror("Błąd zapisu", f"Nie można było zapisać pliku presetu: {e}")

    # --- NOWE FUNKCJE (Logi i About) ---
    
    def save_logs(self):
        """Pobiera logi z wątku czytelnika i zapisuje do pliku."""
        if not self.reader_thread or not hasattr(self.reader_thread, 'log_buffer'):
            messagebox.showwarning("Brak logów", "Brak logów. Uruchom czytnik, aby rozpocząć zbieranie danych.", master=self.root)
            return

        logs = list(self.reader_thread.log_buffer)
        
        if not logs:
            messagebox.showinfo("Info", "Brak logów do zapisania (jeszcze żadne napisy nie zostały dopasowane).", master=self.root)
            return
            
        filepath = filedialog.asksaveasfilename(
            title="Zapisz logi dopasowań",
            defaultextension=".txt",
            filetypes=[("Pliki tekstowe", "*.txt"), ("Wszystkie pliki", "*.*")]
        )
        
        if not filepath:
            return
            
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(f"Logi dopasowań Game Reader ({time.asctime()})\n")
                f.write("="*40 + "\n\n")
                f.writelines(log + "\n" for log in logs)
            
            messagebox.showinfo("Sukces", f"Pomyślnie zapisano {len(logs)} wpisów logu w:\n{filepath}", master=self.root)
        except Exception as e:
            messagebox.showerror("Błąd zapisu", f"Nie można zapisać pliku logów: {e}", master=self.root)

    def show_about(self):
        """Wyświetla okno "O programie"."""
        messagebox.showinfo(
            "O programie",
            "Game Reader (Wayland)\n\n"
            "Wersja 1.1\n\n"
            "Aplikacja do odczytywania napisów z gier (przez OCR) "
            "i odtwarzania powiązanych plików audio.",
            master=self.root
        )

    # --- Sterowanie ---

    def start_reading(self):
        config_path = self.preset_var.get()
        
        # 1. Pobieranie Regexa z nowego UI
        regex_mode = self.regex_mode_var.get()
        if regex_mode == "Inne (wpisz własny)":
            regex_pattern = self.custom_regex_var.get()
        else:
            regex_pattern = self.regex_patterns.get(regex_mode, "")

        # 2. Obsługa Niestandardowej Rozdzielczości
        res_input = self.resolution_var.get()
        target_res_tuple = None
        
        # Sprawdź czy to klucz ze słownika (np. "1080p ...")
        if res_input in self.resolutions:
            target_res_tuple = self.resolutions[res_input]
        else:
            # Spróbuj sparsować ręcznie wpisany string "WxH"
            try:
                w, h = map(int, res_input.lower().split('x'))
                target_res_tuple = (w, h)
                print(f"Używam niestandardowej rozdzielczości: {w}x{h}")
            except ValueError:
                print("Nieprawidłowy format rozdzielczości. Używam domyślnej z presetu.")
                target_res_tuple = None

        if not config_path or not os.path.exists(config_path):
            messagebox.showerror("Błąd", "Nie wybrano prawidłowego pliku presetu.")
            return

        self.save_app_config(new_preset=config_path)

        # Wyczyść flagę stop i kolejkę
        stop_event.clear()
        while not audio_queue.empty():
            try: audio_queue.get_nowait()
            except queue.Empty: break

        current_speed_provider = lambda: self.audio_speed_var.get()

        self.player_thread = PlayerThread(stop_event, audio_queue, base_speed_callback=current_speed_provider)

        self.reader_thread = ReaderThread(
            config_path, regex_pattern, self.settings, stop_event, audio_queue,
            target_resolution=target_res_tuple,
            log_queue=self.log_queue  # Przekazujemy kolejkę logów
        )
        
        self.player_thread.start()
        self.reader_thread.start()
        
        self.toggle_ui_state(running=True)

        # Uruchom grę, jeśli została podana w argumentach
        if self.game_command and not self.game_process:
            try:
                print(
                    f"Uruchamianie procesu gry: {' '.join(self.game_command)}")
                self.game_process = subprocess.Popen(self.game_command)
            except Exception as e:
                print(f"BŁĄD: Nie można uruchomić gry: {e}", file=sys.stderr)
                messagebox.showerror(
                    "Błąd uruchamiania gry", f"Nie można uruchomić polecenia: {e}")

    def stop_reading(self):
        print("Wysyłanie sygnału stop...")
        stop_event.set()
        
        if self.reader_thread:
            self.reader_thread.join(timeout=2.0)
        if self.player_thread:
            self.player_thread.join(timeout=3.0)

        self.reader_thread = None
        self.player_thread = None
        
        self.toggle_ui_state(running=False)
        print("Wątki zatrzymane.")

    def toggle_ui_state(self, running: bool):
        """Blokuje/odblokowuje GUI podczas działania."""
        state = "disabled" if running else "normal"
        combo_state = "disabled" if running else "readonly"
        
        self.start_button.config(state="disabled" if running else "normal")
        self.stop_button.config(state="normal" if running else "disabled")
        
        self.preset_combo.config(state=combo_state)
        self.custom_regex_entry.config(state=state)
        self.res_combo.config(state=combo_state)
        
        try:
            menu = self.root.config('menu')[-1] # Pobierz widget menu
            self.root.nametowidget(menu).entryconfig("Preset", state=state)
            self.root.nametowidget(menu).entryconfig("Narzędzia", state=state)
            # Pozwól na zapis logów i "About" nawet podczas działania
            # self.root.nametowidget(menu).entryconfig("Pomoc", state=state) 
        except Exception as e:
            print(f"Nie można zablokować menu: {e}")


    def on_closing(self):
        """Obsługuje zamknięcie okna."""
        print("Zamykanie aplikacji...")

        # 1. Zatrzymaj wątki czytelnika i odtwarzacza
        if self.reader_thread and self.reader_thread.is_alive():
            print("Zatrzymywanie wątków...")
            self.stop_reading()

        # 2. Zatrzymaj proces gry, jeśli my go uruchomiliśmy
        if self.game_process:
            if self.game_process.poll() is None:  # Sprawdź, czy proces nadal działa
                print("Zatrzymywanie procesu gry...")
                try:
                    self.game_process.terminate()  # Wyślij SIGTERM
                    # Daj mu 3s na zamknięcie
                    self.game_process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    print(
                        "Proces gry nie odpowiedział, wymuszam zamknięcie (SIGKILL)...")
                    self.game_process.kill()  # Wyślij SIGKILL
                except Exception as e:
                    print(f"Błąd podczas zamykania gry: {e}", file=sys.stderr)
            self.game_process = None

        # 3. Zapisz ostatnie ustawienia GUI (regex, rozdzielczość)
        try:
            self.save_app_config()
            print("Zapisano ustawienia aplikacji.")
        except Exception as e:
            print(f"Błąd zapisu ustawień przy zamykaniu: {e}", file=sys.stderr)

        # 4. Zniszcz okno GUI
        self.root.destroy()

    def _update_preset_field(self, key: str, value: str):
        """Pomocnicza funkcja do szybkiej aktualizacji pojedynczego pola w presecie."""
        preset_path = self.preset_var.get()
        if not preset_path or not os.path.exists(preset_path):
            return

        try:
            with open(preset_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            data[key] = value
            
            with open(preset_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4)
            
            print(f"Zaktualizowano preset: {key} -> {value}")
        except Exception as e:
            print(f"Błąd auto-zapisu presetu: {e}", file=sys.stderr)
            messagebox.showerror("Błąd zapisu", f"Nie udało się zapisać zmiany w presecie: {e}")

    def _ensure_preset_1080p(self, preset_path):
        try:
            with open(preset_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            if data.get('resolution') == "1920x1080": return

            print("Standaryzacja presetu do 1080p...")
            orig_res = data.get('resolution', '1920x1080')
            if 'x' in orig_res:
                ow, oh = map(int, orig_res.split('x'))
            else:
                ow, oh = 1920, 1080

            sx = 1920 / ow
            sy = 1080 / oh

            # Obsługa Monitor (Dict lub List)
            mon = data.get('monitor')
            new_mon = []

            monitor_list = mon if isinstance(mon, list) else [mon]

            for m in monitor_list:
                if not m: continue
                new_mon.append({
                    'left': int(m.get('left', 0) * sx),
                    'top': int(m.get('top', 0) * sy),
                    'width': int(m.get('width', 0) * sx),
                    'height': int(m.get('height', 0) * sy)
                })

            data['monitor'] = new_mon if len(new_mon) > 1 else new_mon[0]
            data['resolution'] = "1920x1080"

            with open(preset_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            print(f"Błąd standaryzacji: {e}")

    def _toggle_regex_entry(self, event=None):
        """Włącza/wyłącza pole tekstowe w zależności od wyboru w comboboxie."""
        selection = self.regex_mode_var.get()
        if selection == "Inne (wpisz własny)":
            self.custom_regex_entry.config(state="normal")
        else:
            self.custom_regex_entry.config(state="disabled")

    def open_log_window(self):
        if self.log_window_ref is None or not self.log_window_ref.winfo_exists():
            self.log_window_ref = LogWindow(self.root, self.log_queue)
        else:
            self.log_window_ref.lift()

    def _auto_save_to_preset(self, key: str, value: Any):
        preset_path = self.preset_var.get()
        if not preset_path or not os.path.exists(preset_path): return

        try:
            with open(preset_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            data[key] = value

            with open(preset_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4)
            print(f"Auto-zapis presetu: {key} -> {value}")
        except Exception as e:
            print(f"Błąd auto-zapisu presetu: {e}")

    def on_speed_change(self, event=None):
        # Zapisz do presetu po puszczeniu suwaka
        val = round(self.audio_speed_var.get(), 2)
        self.speed_value_label.config(text=f"{val}x")  # Aktualizacja etykiety
        self._auto_save_to_preset("audio_speed", val)

    def on_regex_change(self, event=None):
        self._toggle_regex_entry()
        # Pobierz pattern
        regex_mode = self.regex_mode_var.get()
        if regex_mode != "Inny (wpisz własny)":
            # Jeśli to nie custom, zapisz od razu wybrany tryb/wzorzec
            pattern = self.regex_patterns.get(regex_mode, "")
            self._auto_save_to_preset("regex_pattern", pattern)
            self._auto_save_to_preset("regex_mode_name", regex_mode)

    def on_custom_regex_save(self, event=None):
        if self.regex_mode_var.get() == "Inny (wpisz własny)":
            pattern = self.custom_regex_var.get()
            self._auto_save_to_preset("regex_pattern", pattern)
            self._auto_save_to_preset("regex_mode_name", "Inny (wpisz własny)")

    def manage_area(self, index: int, action: str):
        preset_path = self.preset_var.get()
        if not preset_path or not os.path.exists(preset_path):
            messagebox.showerror("Błąd", "Wybierz preset.")
            return

        try:
            with open(preset_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # Pobierz aktualne monitory (upewnij się, że to lista)
            monitors = data.get('monitor', [])
            if isinstance(monitors, dict):
                monitors = [monitors]

            # Uzupełnij listę do 3 elementów, jeśli jest krótsza
            while len(monitors) < 3:
                monitors.append(None)

            if action == 'clear':
                if monitors[index] is None:
                    messagebox.showinfo("Info", f"Obszar {index + 1} jest już pusty.")
                    return
                monitors[index] = None
                data['monitor'] = [m for m in monitors if m is not None]  # Usuń None przed zapisem
                if not data['monitor']:  # Jeśli pusta lista, daj chociaż jeden pusty dict lub null
                    data['monitor'] = []

                with open(preset_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=4)
                messagebox.showinfo("Sukces", f"Wyczyszczono obszar {index + 1}.")
                return

            if action == 'set':
                self.root.withdraw()
                time.sleep(0.5)
                screenshot = _capture_fullscreen_image()
                if not screenshot:
                    self.root.deiconify()
                    return

                # Skalowanie
                screen_w, screen_h = screenshot.size
                base_w, base_h = 1920, 1080
                save_scale_x = base_w / screen_w
                save_scale_y = base_h / screen_h
                load_scale_x = screen_w / base_w
                load_scale_y = screen_h / base_h

                # Przygotuj listę INNYCH obszarów do wyświetlenia
                existing_regions_raw = []
                for i, m in enumerate(monitors):
                    if i == index: continue  # Nie wyświetlamy tego, który właśnie zmieniamy (będzie rysowany nowy)
                    if m:
                        existing_regions_raw.append({
                            'left': int(m.get('left', 0) * load_scale_x),
                            'top': int(m.get('top', 0) * load_scale_y),
                            'width': int(m.get('width', 0) * load_scale_x),
                            'height': int(m.get('height', 0) * load_scale_y)
                        })

                title = f"Ustawianie obszaru {index + 1}"
                print(title)

                selector = AreaSelector(self.root, screenshot, existing_regions=existing_regions_raw)
                geom = selector.geometry

                self.root.deiconify()
                screenshot.close()

                if geom:
                    scaled_geom = {
                        'left': int(geom['left'] * save_scale_x),
                        'top': int(geom['top'] * save_scale_y),
                        'width': int(geom['width'] * save_scale_x),
                        'height': int(geom['height'] * save_scale_y)
                    }
                    monitors[index] = scaled_geom

                    # Zapisz (filtrując None)
                    data['monitor'] = [m for m in monitors if m is not None]
                    data['resolution'] = "1920x1080"

                    with open(preset_path, 'w', encoding='utf-8') as f:
                        json.dump(data, f, indent=4)

                    messagebox.showinfo("Sukces", f"Zapisano obszar {index + 1}.")

        except Exception as e:
            self.root.deiconify()
            messagebox.showerror("Błąd", f"Błąd zarządzania obszarami: {e}")


def main():
    
    parser = argparse.ArgumentParser(description="Game Reader dla Wayland.")
    parser.add_argument(
        '--preset',
        type=str,
        help="Ścieżka do pliku presetu (.json) do automatycznego wczytania."
    )
    
    parser.add_argument(
        'game_command',
        nargs=argparse.REMAINDER,
        help="Polecenie uruchomienia gry (np. %command% ze Steam)."
    )
    
    args = parser.parse_args()
    
    autostart_preset = args.preset
    game_command = args.game_command
    
    if game_command and game_command[0] == '--':
        game_command.pop(0)

    if game_command and game_command[0] == 'game-performance':
        game_command.pop(0)
    
    if not game_command:
        game_command = None

    # --- Uruchomienie GUI ---
    print("Uruchamianie aplikacji GUI...")
    root = tk.Tk()
    app = GameReaderApp(root, autostart_preset, game_command)
    root.mainloop()

if __name__ == "__main__":
    main()
