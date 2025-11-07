#!/usr/bin/env python3

"""
Game Reader - zamiennik dla Wayland (Wersja z GUI i kolejką audio)
Autor: AI (Gemini)
Data: 03.11.2025

Wymagania systemowe:
- spectacle (dla KDE) lub gnome-screenshot (dla GNOME)
- tesseract-ocr (silnik OCR)
- tesseract-data-pol

Wymagania Python (pip install):
- pillow (PIL)
- pytesseract
- pygame
- thefuzz
"""

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
from app.utils import _capture_fullscreen_image, check_dependencies

# --- Importy GUI (Tkinter) ---
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
        self.root.geometry("500x250")
        
        # Zapisz argumenty startowe
        self.autostart_preset = autostart_preset
        self.game_command = game_command
        self.game_process = None  # Do śledzenia procesu gry

        self.settings = {}  # Zostanie wypełnione przez load_app_config

        self.reader_thread: Optional[ReaderThread] = None
        self.player_thread: Optional[PlayerThread] = None

        # --- Menu ---
        self.create_menu()

        # --- Główny kontener ---
        main_frame = ttk.Frame(root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # --- Wybór presetu ---
        ttk.Label(main_frame, text="Wybierz preset:").pack(anchor=tk.W)
        self.preset_var = tk.StringVar()
        self.preset_combo = ttk.Combobox(main_frame, textvariable=self.preset_var, state="readonly", width=60)
        self.preset_combo.pack(fill=tk.X, anchor=tk.W, pady=5)
        
        # --- Pole Regex ---
        ttk.Label(main_frame, text="Regex do usuwania imion:").pack(anchor=tk.W, pady=(10, 0))
        self.regex_var = tk.StringVar()
        self.regex_entry = ttk.Entry(main_frame, textvariable=self.regex_var, width=60)
        self.regex_entry.pack(fill=tk.X, anchor=tk.W, pady=5)

        # --- Przyciski ---
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=10)
        
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
                # Użyj 'after', aby dać GUI chwilę na "złapanie oddechu"
                self.root.after(100, self.start_reading)
            else:
                print(
                    f"BŁĄD Autostartu: Plik presetu nie istnieje: {self.autostart_preset}")

    def create_menu(self):
        menubar = tk.Menu(self.root)
        file_menu = tk.Menu(menubar, tearoff=0)
        
        file_menu.add_command(label="Wybierz nowy preset...", command=self.select_new_preset)
        file_menu.add_command(label="Wybierz obszar dla aktywnego presetu...", command=self.select_area_for_preset)
        file_menu.add_command(label="Ustawienia...",
                              command=self.open_settings_dialog)
        file_menu.add_separator()
        file_menu.add_command(label="Wyjdź", command=self.on_closing)
        
        menubar.add_cascade(label="Plik", menu=file_menu)
        self.root.config(menu=menubar)

    def select_area_for_preset(self):
        """Uruchamia selektor obszaru i nadpisuje plik presetu."""
        preset_path = self.preset_var.get()
        if not preset_path or not os.path.exists(preset_path):
            messagebox.showerror("Błąd", "Wybierz prawidłowy plik presetu z listy, zanim wybierzesz obszar.")
            return

        # Ukryj główne okno
        self.root.withdraw()
        time.sleep(0.5) # Daj systemowi chwilę

        # Zrób pełny zrzut ekranu PRZED otwarciem okna wyboru
        screenshot = None
        try:
            screenshot = _capture_fullscreen_image()
            if not screenshot:
                messagebox.showerror("Błąd", "Nie można było zrobić zrzutu ekranu. Sprawdź 'spectacle'.")
                return

            selector = AreaSelector(self.root, screenshot)
            new_geometry = selector.geometry
        
        except Exception as e:
            print(f"Błąd podczas wyboru obszaru: {e}", file=sys.stderr)
            new_geometry = None
        finally:
            # Pokaż główne okno z powrotem
            self.root.deiconify()
            # Zamknij obraz (ważne)
            if screenshot:
                screenshot.close()

        if new_geometry:
            try:
                # Wczytaj, zmodyfikuj, zapisz
                with open(preset_path, 'r', encoding='utf-8') as f:
                    preset_data = json.load(f)
                
                preset_data['monitor'] = new_geometry
                
                with open(preset_path, 'w', encoding='utf-8') as f:
                    json.dump(preset_data, f, indent=4)
                    
                messagebox.showinfo("Sukces", f"Obszar dla presetu '{os.path.basename(preset_path)}' został zaktualizowany.")
            except Exception as e:
                print(f"BŁĄD: Nie można zapisać presetu {preset_path}: {e}", file=sys.stderr)
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
            'last_regex': r"^[\w\s]+:",
            'subtitle_mode': 'Full Lines',
            'ocr_scale_factor': 1.0,
            'ocr_grayscale': False,
            'ocr_contrast': False
        }

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
        """Zapisuje listę presetów i regex do pliku JSON."""
        if new_preset:
            if new_preset in self.settings['recent_presets']:
                self.settings['recent_presets'].remove(
                    new_preset)  # Przesuń na górę
            self.settings['recent_presets'].insert(0, new_preset)
            # Ogranicz do 10
            self.settings['recent_presets'] = self.settings['recent_presets'][:10]
            
        self.settings['last_regex'] = self.regex_var.get()

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
        self.regex_var.set(self.settings.get('last_regex', r"^[\w\s]+:"))

    def select_new_preset(self):
        """Otwiera dialog wyboru pliku i dodaje go do listy."""
        path = filedialog.askopenfilename(
            title="Wybierz plik presetu",
            filetypes=[("Preset JSON", "*.json"), ("Wszystkie pliki", "*.*")]
        )
        if path:
            self.save_app_config(new_preset=path)
            self.update_gui_from_config()
            self.preset_var.set(path) # Ustaw nowo wybrany jako aktywny

    def start_reading(self):
        config_path = self.preset_var.get()
        regex_pattern = self.regex_var.get()
        
        if not config_path or not os.path.exists(config_path):
            messagebox.showerror("Błąd", "Nie wybrano prawidłowego pliku presetu.")
            return

        # Zapisz obecne ustawienia
        self.save_app_config()

        # Wyczyść flagę stop i kolejkę
        stop_event.clear()
        while not audio_queue.empty():
            try: audio_queue.get_nowait()
            except queue.Empty: break
        
        self.player_thread = PlayerThread(stop_event, audio_queue)
        self.reader_thread = ReaderThread(
            config_path, regex_pattern, self.settings, stop_event, audio_queue)
        
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
        
        # Poczekaj na zakończenie wątków
        if self.reader_thread:
            self.reader_thread.join(timeout=2.0)
        if self.player_thread:
            self.player_thread.join(timeout=3.0) # Player może kończyć grać

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
        
        # Zablokuj menu podczas działania (trochę bardziej skomplikowane)
        # Na razie pomijamy dla prostoty

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

        # 3. Zniszcz okno GUI
        self.root.destroy()

def main():
    # --- Parser argumentów ---
    parser = argparse.ArgumentParser(description="Game Reader dla Wayland.")
    parser.add_argument(
        '--preset',
        type=str,
        help="Ścieżka do pliku presetu (.json) do automatycznego wczytania."
    )
    # Używamy 'nargs' aby zebrać wszystkie pozostałe argumenty jako polecenie gry
    parser.add_argument(
        'game_command',
        nargs=argparse.REMAINDER,
        help="Polecenie uruchomienia gry (np. %command% ze Steam)."
    )
    
    args = parser.parse_args()
    
    autostart_preset = args.preset
    game_command = args.game_command
    
    # Obsługa '--' (częste w Steam, np. --exec %command%)
    if game_command and game_command[0] == '--':
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
