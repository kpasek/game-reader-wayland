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

try:
    from PIL import Image, ImageTk
except ImportError:
    print("Błąd: Nie znaleziono biblioteki 'Pillow'. Zainstaluj ją: pip install Pillow", file=sys.stderr)
    sys.exit(1)

APP_CONFIG_FILE = 'app_config.json'

audio_queue = queue.Queue()
stop_event = threading.Event()

class GameReaderApp:
    def __init__(self, root: tk.Tk, autostart_preset: Optional[str], game_command: Optional[List[str]]):        
        self.root = root
        self.root.title("Game Reader (Wayland)")
        # Zmniejszono rozmiar okna po usunięciu sekcji ścieżek
        self.root.geometry("700x380")

        # Zmienne
        self.preset_var = tk.StringVar()
        self.audio_dir_var = tk.StringVar()
        self.subtitles_file_var = tk.StringVar()
        self.names_file_var = tk.StringVar()
        
        # Zmienne dla Regex
        self.regex_mode_var = tk.StringVar()
        self.custom_regex_var = tk.StringVar()

        self.resolutions = {
            "1080p (1920x1080)": (1920, 1080),
            "1440p (2560x1440)": (2560, 1440),
            "4K (3840x2160)": (3840, 2160),
            "800p (1280x800)": (1280, 800),
            "1600p (2560x1600)": (2560, 1600),
            "Niestandardowa (z presetu)": None
        }
        
        # Zapisz argumenty startowe
        self.autostart_preset = autostart_preset
        self.game_command = game_command
        self.game_process = None  # Do śledzenia procesu gry

        self.settings = {}  # Zostanie wypełnione przez load_app_config

        self.reader_thread: Optional[ReaderThread] = None
        self.player_thread: Optional[PlayerThread] = None
        
        # Zmienne przechowujące ścieżki (teraz niewidoczne w GUI, ale używane przez menu)
        self.audio_dir_var = tk.StringVar()
        self.subtitles_file_var = tk.StringVar()
        self.names_file_var = tk.StringVar()

        # --- Menu ---
        self.create_menu()

        # --- Główny kontener ---
        main_frame = ttk.Frame(root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # --- Wybór presetu ---
        ttk.Label(main_frame, text="Wybierz preset:").pack(anchor=tk.W)
        self.preset_combo = ttk.Combobox(main_frame, textvariable=self.preset_var, state="readonly", width=60)
        self.preset_combo.pack(fill=tk.X, anchor=tk.W, pady=5)
        self.preset_combo.bind("<<ComboboxSelected>>", self.on_preset_selected)
        
        ttk.Label(main_frame, text="Wzorzec wycinania imion:").pack(anchor=tk.W, pady=(10, 0))
        
        regex_frame = ttk.Frame(main_frame)
        regex_frame.pack(fill=tk.X, pady=5)
        
        self.regex_patterns = {
            "Nie wycinaj imion": r"",
            "Standardowy (Imie: Kwestia)": r"^(?i)({NAMES})\s*[:：]",
            "W nawiasach ([Imie] Kwestia)": r"^\[({NAMES})\]",
            "Samo imię na początku": r"^({NAMES})\s+",
            "Inne (wpisz własny)": "CUSTOM"
        }
        
        self.regex_combo = ttk.Combobox(
            regex_frame, 
            textvariable=self.regex_mode_var,
            values=list(self.regex_patterns.keys()),
            state="readonly", 
            width=35
        )
        self.regex_combo.pack(side=tk.LEFT, padx=(0, 5))
        self.regex_combo.bind("<<ComboboxSelected>>", self._toggle_regex_entry)

        self.custom_regex_entry = ttk.Entry(regex_frame, textvariable=self.custom_regex_var)
        self.custom_regex_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        ttk.Label(main_frame, text="Docelowa rozdzielczość gry (skalowanie obszaru):").pack(anchor=tk.W, pady=(10, 0))
        
        self.resolution_var = tk.StringVar()
        self.res_combo = ttk.Combobox(main_frame, textvariable=self.resolution_var,
                                      width=60,
                                      values=list(self.resolutions.keys()))
        self.res_combo.pack(fill=tk.X, anchor=tk.W, pady=5)

        # --- Przyciski ---
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=10, side=tk.BOTTOM)
        
        self.start_button = ttk.Button(button_frame, text="Uruchom", command=self.start_reading)
        self.start_button.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=5)
        
        self.stop_button = ttk.Button(button_frame, text="Zatrzymaj", command=self.stop_reading, state="disabled")
        self.stop_button.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=5)
        
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
        file_menu.add_command(label="Ustawienia (OCR, ...)",
                              command=self.open_settings_dialog)
        file_menu.add_separator()
        file_menu.add_command(label="Wyjdź", command=self.on_closing)
        menubar.add_cascade(label="Plik", menu=file_menu)
        
        # --- Menu Preset ---
        preset_menu = tk.Menu(menubar, tearoff=0)
        preset_menu.add_command(label="Wybierz nowy plik presetu...", 
                                command=self.select_new_preset)
        preset_menu.add_command(label="Wybierz obszar (dla aktywnego)...", 
                                command=self.select_area_for_preset)
        preset_menu.add_separator()
        preset_menu.add_command(label="Zmień katalog audio...", 
                                command=self.select_audio_dir)
        preset_menu.add_command(label="Zmień plik napisów...", 
                                command=self.select_subtitles_file)
        preset_menu.add_command(label="Zmień plik imion...", 
                                command=self.select_names_file)
        preset_menu.add_separator()
        preset_menu.add_command(label="Zapisz zmiany ścieżek w presecie", 
                                command=self.save_paths_to_preset)
        menubar.add_cascade(label="Preset", menu=preset_menu)

        # --- Menu Narzędzia ---
        tools_menu = tk.Menu(menubar, tearoff=0)
        tools_menu.add_command(label="Generuj polecenie startowe Steam...",
                              command=self.generate_steam_command)
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

    def generate_steam_command(self):
        """Generuje polecenie startowe dla Steam i kopiuje do schowka."""
        preset_path = self.preset_var.get()
        if not preset_path:
            messagebox.showerror("Błąd", "Najpierw wybierz preset z listy.")
            return
        
        if not os.path.exists(preset_path):
                messagebox.showerror("Błąd", f"Wybrany plik presetu nie istnieje: {preset_path}")
                return

        try:            
            abs_preset_path = os.path.abspath(preset_path)

            command = f'reader --preset "{abs_preset_path}"'
            
            # Spróbuj skopiować do schowka
            self.root.clipboard_clear()
            self.root.clipboard_append(command)
            self.root.update()
            
            messagebox.showinfo(
                "Polecenie Steam wygenerowane",
                "Polecenie startowe zostało skopiowane do schowka.\n\n"
                "Wklej je w opcjach uruchamiania Steam *przed* poleceniem gry, np.:\n\n"
                f'{command} %command%'
            )
        except tk.TclError:
            messagebox.showwarning(
                "Błąd schowka",
                "Nie można skopiować do schowka. Oto polecenie do skopiowania ręcznego:\n\n"
                f"{command}"
            )
        except Exception as e:
                messagebox.showerror("Błąd", f"Wystąpił nieoczekiwany błąd: {e}")

    def select_area_for_preset(self):
        """Uruchamia selektor obszaru, przelicza na 1080p i nadpisuje plik presetu."""
        preset_path = self.preset_var.get()
        if not preset_path or not os.path.exists(preset_path):
            messagebox.showerror("Błąd", "Wybierz prawidłowy plik presetu z listy.")
            return

        # Wczytaj obecny preset, aby pobrać starą geometrię
        old_geometry_scaled = None
        try:
            with open(preset_path, 'r', encoding='utf-8') as f:
                preset_data = json.load(f)
                old_monitor = preset_data.get('monitor')
                old_res_str = preset_data.get('resolution', '1920x1080') # Domyślne 1080p
        except Exception:
            old_monitor = None
            old_res_str = '1920x1080'

        # Ukryj główne okno
        self.root.withdraw()
        time.sleep(0.5)

        screenshot = None
        try:
            screenshot = _capture_fullscreen_image()
            if not screenshot:
                messagebox.showerror("Błąd", "Nie można było zrobić zrzutu ekranu.")
                self.root.deiconify()
                return

            screen_w, screen_h = screenshot.size

            # --- PRZELICZANIE STAREGO OBSZARU DO AKTUALNEGO EKRANU ---
            # Jeśli mamy stary obszar, musimy go przeskalować z "resolution" w JSON
            # do aktualnej rozdzielczości zrzutu ekranu, żeby wyświetlić go poprawnie.
            if old_monitor:
                try:
                    orig_w, orig_h = map(int, old_res_str.lower().split('x'))
                    scale_x = screen_w / orig_w
                    scale_y = screen_h / orig_h
                    
                    old_geometry_scaled = {
                        'left': int(old_monitor['left'] * scale_x),
                        'top': int(old_monitor['top'] * scale_y),
                        'width': int(old_monitor['width'] * scale_x),
                        'height': int(old_monitor['height'] * scale_y)
                    }
                except Exception as e:
                    print(f"Nie udało się przeskalować starego obszaru: {e}")

            # Przekazujemy old_geometry_scaled do selektora
            selector = AreaSelector(self.root, screenshot, current_geometry=old_geometry_scaled)
            new_geometry_screen = selector.geometry
        
        except Exception as e:
            print(f"Błąd podczas wyboru obszaru: {e}", file=sys.stderr)
            new_geometry_screen = None
        finally:
            self.root.deiconify()
            if screenshot:
                screenshot.close()

        if new_geometry_screen:
            try:
                # Niezależnie od tego jaki masz monitor (4K, 1440p, 800p),
                # zapisujemy współrzędne przeliczone na bazę 1920x1080.
                
                base_w, base_h = 1920, 1080
                current_w, current_h = screen_w, screen_h # type: ignore (zdefiniowane wyżej)

                # Obliczamy faktor skalowania W DÓŁ (lub w górę) do 1080p
                scale_to_base_x = base_w / current_w
                scale_to_base_y = base_h / current_h

                final_geometry = {
                    'left': int(new_geometry_screen['left'] * scale_to_base_x),
                    'top': int(new_geometry_screen['top'] * scale_to_base_y),
                    'width': int(new_geometry_screen['width'] * scale_to_base_x),
                    'height': int(new_geometry_screen['height'] * scale_to_base_y)
                }

                with open(preset_path, 'r', encoding='utf-8') as f:
                    preset_data = json.load(f)
                
                preset_data['monitor'] = final_geometry
                preset_data['resolution'] = "1920x1080" # Wymuszamy standard 1080p
                
                with open(preset_path, 'w', encoding='utf-8') as f:
                    json.dump(preset_data, f, indent=4)
                    
                messagebox.showinfo("Sukces", 
                    f"Obszar zaktualizowany.\n\n"
                    f"Zrzut ekranu: {current_w}x{current_h}\n"
                    f"Zapisano jako (Baza 1080p): {final_geometry}")

            except Exception as e:
                print(f"BŁĄD: Nie można zapisać presetu: {e}", file=sys.stderr)
                messagebox.showerror("Błąd zapisu", f"Nie można było zapisać pliku presetu: {e}")
        else:
            print("Wybór obszaru anulowany.")

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
        """Aktualizuje GUI na podstawie wczytanego self.settings."""
        self.preset_combo['values'] = self.settings.get('recent_presets', [])
        if self.settings.get('recent_presets'):
            self.preset_var.set(self.settings['recent_presets'][0])
            
        # Regex GUI
        last_mode = self.settings.get('last_regex_mode', list(self.regex_patterns.keys())[0])
        self.regex_mode_var.set(last_mode)
        self.custom_regex_var.set(self.settings.get('last_custom_regex', ""))
        self._toggle_regex_entry() # Odśwież stan pola tekstowego
        
        # Rozdzielczość
        self.resolution_var.set(self.settings.get('last_resolution_key', 'Niestandardowa (z presetu)'))
        
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
        preset_path = self.preset_var.get()
        if not preset_path or not os.path.exists(preset_path):
            return
        
        # 1. Automatyczna naprawa rozdzielczości w pliku presetu
        self._ensure_preset_1080p(preset_path)

        # 2. Wczytanie ścieżek (bez zmian)
        try:
            with open(preset_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self.audio_dir_var.set(data.get('audio_dir', ''))
            self.subtitles_file_var.set(data.get('text_file_path', ''))
            self.names_file_var.set(data.get('names_file_path', ''))
        except Exception as e:
            print(f"Błąd odczytu presetu: {e}")

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
            
        self.player_thread = PlayerThread(stop_event, audio_queue)
        self.reader_thread = ReaderThread(
            config_path, regex_pattern, self.settings, stop_event, audio_queue,
            target_resolution=target_res_tuple) # Przekazujemy tuple (z listy lub custom)
        
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
        self.regex_entry.config(state=state)
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
    
    def _ensure_preset_1080p(self, preset_path: str):
        """
        Sprawdza, czy preset jest w bazie 1920x1080. 
        Jeśli nie, przelicza koordynaty obszaru, aktualizuje plik i zapisuje.
        """
        try:
            with open(preset_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            current_res_str = data.get('resolution', '')
            monitor = data.get('monitor', {})
            
            # Jeśli to już 1080p lub brak danych, nic nie rób
            if current_res_str == "1920x1080":
                return

            print(f"Standaryzacja presetu z {current_res_str} na 1920x1080...")
            
            # Parsowanie obecnej rozdzielczości
            if not current_res_str or 'x' not in current_res_str:
                # Zakładamy, że stare, błędne presety bez rozdzielczości były robione pod 1080p lub ignorujemy
                orig_w, orig_h = 1920, 1080 
            else:
                orig_w, orig_h = map(int, current_res_str.lower().split('x'))

            # Obliczanie skali do 1080p
            target_w, target_h = 1920, 1080
            scale_x = target_w / orig_w
            scale_y = target_h / orig_h

            # Przeliczanie obszaru
            new_monitor = {
                'left': int(monitor.get('left', 0) * scale_x),
                'top': int(monitor.get('top', 0) * scale_y),
                'width': int(monitor.get('width', 0) * scale_x),
                'height': int(monitor.get('height', 0) * scale_y)
            }

            # Aktualizacja danych
            data['monitor'] = new_monitor
            data['resolution'] = "1920x1080"

            # Zapis do pliku
            with open(preset_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4)
            
            print(f"Zaktualizowano preset do standardu 1080p: {new_monitor}")

        except Exception as e:
            print(f"BŁĄD podczas standaryzacji presetu: {e}", file=sys.stderr)

    def _toggle_regex_entry(self, event=None):
        """Włącza/wyłącza pole tekstowe w zależności od wyboru w comboboxie."""
        selection = self.regex_mode_var.get()
        if selection == "Inne (wpisz własny)":
            self.custom_regex_entry.config(state="normal")
        else:
            self.custom_regex_entry.config(state="disabled")
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
