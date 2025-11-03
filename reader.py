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
import io
import subprocess
import shutil
import tempfile
import threading
import queue
import re
from typing import List, Dict, Any, Optional

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

# --- Importowanie zależności (jak poprzednio) ---
try:
    from PIL import Image
except ImportError:
    print("Błąd: Nie znaleziono biblioteki 'Pillow'. Zainstaluj ją: pip install Pillow", file=sys.stderr)
    sys.exit(1)

try:
    import pytesseract
except ImportError:
    print("Błąd: Nie znaleziono biblioteki 'pytesseract'. Zainstaluj ją: pip install pytesseract", file=sys.stderr)
    sys.exit(1)

try:
    import pygame
except ImportError:
    print("Błąd: Nie znaleziono biblioteki 'pygame'. Zainstaluj ją: pip install pygame", file=sys.stderr)
    sys.exit(1)

try:
    from thefuzz import fuzz
except ImportError:
    print("Błąd: Nie znaleziono biblioteki 'thefuzz'. Zainstaluj ją: pip install thefuzz", file=sys.stderr)
    sys.exit(1)

# --- Konfiguracja globalna ---
OCR_LANGUAGE = 'pol'
MIN_MATCH_THRESHOLD = 85
APP_CONFIG_FILE = 'app_config.json'

# --- Komponenty wielowątkowe ---
# Kolejka na ścieżki do plików audio
audio_queue = queue.Queue()
# Sygnał do zatrzymania wątków
stop_event = threading.Event()

# ==============================================================================
# KLASA WĄTKU ODTWARZACZA (PLAYER THREAD)
# ==============================================================================

class PlayerThread(threading.Thread):
    """Wątek, który obsługuje odtwarzanie audio z kolejki."""
    def __init__(self):
        super().__init__(daemon=True)
        self.name = "PlayerThread"
        print("Inicjalizacja wątku odtwarzacza...")

    def run(self):
        pygame.mixer.init()
        print("Odtwarzacz audio uruchomiony.")
        
        while not stop_event.is_set():
            try:
                # Czekaj na element w kolejce (z timeoutem, by móc sprawdzić stop_event)
                file_path = audio_queue.get(timeout=0.5)
            except queue.Empty:
                continue

            if not os.path.exists(file_path):
                print(f"OSTRZEŻENIE: Nie znaleziono pliku audio: {file_path}", file=sys.stderr)
                audio_queue.task_done()
                continue
            
            try:
                print(f"Odtwarzam z kolejki: {os.path.basename(file_path)}")
                pygame.mixer.music.load(file_path)
                pygame.mixer.music.play()
                
                # Czekaj, aż muzyka skończy grać (bez blokowania)
                while pygame.mixer.music.get_busy() and not stop_event.is_set():
                    time.sleep(0.1)
                    
            except Exception as e:
                print(f"BŁĄD: Nie można odtworzyć pliku audio {file_path}: {e}", file=sys.stderr)
            finally:
                audio_queue.task_done()
        
        pygame.mixer.quit()
        print("Odtwarzacz audio zatrzymany.")

# ==============================================================================
# KLASA WĄTKU CZYTELNIKA (READER THREAD)
# ==============================================================================

class ReaderThread(threading.Thread):
    """Wątek, który wykonuje OCR i dodaje napisy do kolejki."""
    def __init__(self, config_path: str, regex_pattern: str):
        super().__init__(daemon=True)
        self.name = "ReaderThread"
        self.config_path = config_path
        self.regex_pattern = regex_pattern
        self.last_added_index = -1
        self.last_ocr_text = ""
        print(f"Inicjalizacja wątku czytelnika z presetem: {config_path}")

    def run(self):
        try:
            print("Wątek czytelnika uruchomiony.")
            
            # 1. Wczytaj konfigurację
            config = load_config(self.config_path)
            subtitles = load_text_file(config['text_file_path'])
            if not subtitles:
                print("BŁĄD: Plik napisów jest pusty lub nie istnieje. Zatrzymuję wątek.", file=sys.stderr)
                return

            monitor_config = config['monitor']
            capture_interval = config.get('CAPTURE_INTERVAL', 0.5)
            audio_dir = config['audio_dir']

            print("Czytelnik rozpoczyna pętlę monitorowania...")
            while not stop_event.is_set():
                start_time = time.monotonic()
                
                # 2. Przechwyć i zrób OCR
                image = capture_screen_region(monitor_config)
                if not image:
                    time.sleep(capture_interval)
                    continue

                ocr_text = ocr_and_clean_image(image, self.regex_pattern)
                if not ocr_text:
                    self.last_ocr_text = ""
                    time.sleep(capture_interval)
                    continue
                
                # 3. Sprawdź, czy to ten sam tekst co ostatnio (bufor)
                if ocr_text == self.last_ocr_text:
                    time.sleep(capture_interval)
                    continue
                self.last_ocr_text = ocr_text
                
                print(f"\nOCR odczytał: '{ocr_text}'")

                # 4. Znajdź dopasowanie
                best_match_index = find_best_match(ocr_text, subtitles)

                # 5. Jeśli znaleziono i jest *unikalne* - dodaj do kolejki
                if best_match_index is not None and best_match_index != self.last_added_index:
                    print(f"Dopasowano (Indeks: {best_match_index}). Dodaję do kolejki.")
                    self.last_added_index = best_match_index
                    
                    line_number = best_match_index + 1
                    file_name = f"output1 ({line_number}).ogg"
                    file_path = os.path.join(audio_dir, file_name)
                    
                    # Dodaj ścieżkę do kolejki audio
                    audio_queue.put(file_path)
                
                # 6. Odczekaj resztę interwału
                elapsed = time.monotonic() - start_time
                wait_time = max(0, capture_interval - elapsed)
                time.sleep(wait_time)

        except Exception as e:
            print(f"KRYTYCZNY BŁĄD w wątku czytelnika: {e}", file=sys.stderr)
            # W prawdziwej aplikacji można by tu użyć callbacku do GUI, by poinformować użytkownika
        finally:
            print("Wątek czytelnika zatrzymany.")

# ==============================================================================
# FUNKCJE POMOCNICZE (Z POPRZEDNIEJ WERSJI + MODYFIKACJE)
# ==============================================================================

def check_dependencies():
    """Sprawdza 'spectacle' (dla KDE)."""
    print("Sprawdzanie zależności systemowych...")
    if not shutil.which("spectacle"):
        print("BŁĄD: Nie znaleziono polecenia 'spectacle'.", file=sys.stderr)
        print("Ten skrypt jest skonfigurowany dla KDE. Upewnij się, że 'spectacle' jest zainstalowane.", file=sys.stderr)
        return False
        
    if not shutil.which("tesseract"):
        print("BŁĄD: Nie znaleziono polecenia 'tesseract'.", file=sys.stderr)
        return False
        
    print("Zależności systemowe OK.")
    return True

def load_config(filename: str) -> Dict[str, Any]:
    """Wczytuje plik konfiguracyjny JSON."""
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"BŁĄD: Nie znaleziono pliku konfiguracyjnego: {filename}", file=sys.stderr)
        raise
    except json.JSONDecodeError:
        print(f"BŁĄD: Błąd parsowania pliku JSON: {filename}", file=sys.stderr)
        raise

def load_text_file(filepath: str) -> List[str]:
    """Wczytuje plik tekstowy (napisy) do listy."""
    if not os.path.exists(filepath):
        print(f"BŁĄD: Nie znaleziono pliku: {filepath}", file=sys.stderr)
        return []
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            lines = [line.strip() for line in f if line.strip()]
        return lines
    except Exception as e:
        print(f"BŁĄD: Nie można wczytać pliku {filepath}: {e}", file=sys.stderr)
        return []

def capture_screen_region(monitor_config: Dict[str, int]) -> Optional[Image.Image]:
    """Wykonuje zrzut całego ekranu (KDE - spectacle) i kadruje go."""
    temp_file_path = None
    try:
        left = monitor_config['left']
        top = monitor_config['top']
        width = monitor_config['width']
        height = monitor_config['height']
        
        crop_box = (left, top, left + width, top + height)
        
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tf:
            temp_file_path = tf.name
            
        command = ['spectacle', '-f', '-b', '-n', '-o', temp_file_path]
        subprocess.run(command, check=True, timeout=2.0)
        
        with Image.open(temp_file_path) as full_screenshot:
            cropped_image = full_screenshot.crop(crop_box)
            return cropped_image.copy()

    except Exception as e:
        print(f"BŁĄD: Nieoczekiwany błąd podczas przechwytywania (KDE): {e}", file=sys.stderr)
        return None
    finally:
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.remove(temp_file_path)
            except OSError:
                pass

def ocr_and_clean_image(image: Image.Image, regex_pattern: str) -> str:
    """Wykonuje OCR i usuwa tekst pasujący do regex."""
    try:
        text = pytesseract.image_to_string(image, lang=OCR_LANGUAGE).strip()
        text = text.replace('\n', ' ')
        
        if not text:
            return ""

        # NOWA Logika: Usuwanie za pomocą regex
        if regex_pattern:
            try:
                # Zamień wszystko, co pasuje do regexa, na pusty string
                text = re.sub(regex_pattern, "", text).strip()
            except re.error as e:
                print(f"OSTRZEŻENIE: Błędny Regex: {e}", file=sys.stderr)
        
        return text

    except Exception as e:
        print(f"BŁĄD: Błąd podczas OCR: {e}", file=sys.stderr)
        return ""

def find_best_match(ocr_text: str, subtitles_list: List[str]) -> Optional[int]:
    """Znajduje najlepsze dopasowanie dla tekstu OCR."""
    best_score = 0
    best_index = -1

    for i, sub_line in enumerate(subtitles_list):
        score = fuzz.token_set_ratio(ocr_text, sub_line)
        if score > best_score:
            best_score = score
            best_index = i

    if best_score >= MIN_MATCH_THRESHOLD:
        print(f"Dopasowano (wynik: {best_score}%): Linia {best_index + 1}")
        return best_index
    else:
        print(f"Brak dopasowania (Najlepszy wynik: {best_score}%)")
        return None

# ==============================================================================
# KLASA APLIKACJI GUI (TKINTER)
# ==============================================================================

class GameReaderApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Game Reader (Wayland)")
        self.root.geometry("500x200")
        
        self.recent_presets = []
        self.last_regex = r"^[\w\s]+:" # Domyślny regex: usuwa "IMIĘ: "
        
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
        self.load_app_config()
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def create_menu(self):
        menubar = tk.Menu(self.root)
        file_menu = tk.Menu(menubar, tearoff=0)
        
        file_menu.add_command(label="Wybierz nowy preset...", command=self.select_new_preset)
        file_menu.add_separator()
        file_menu.add_command(label="Wyjdź", command=self.on_closing)
        
        menubar.add_cascade(label="Plik", menu=file_menu)
        self.root.config(menu=menubar)

    def load_app_config(self):
        """Wczytuje ostatnio używane presety i regex z pliku JSON."""
        try:
            with open(APP_CONFIG_FILE, 'r', encoding='utf-8') as f:
                config = json.load(f)
                self.recent_presets = config.get('recent_presets', [])
                self.last_regex = config.get('last_regex', r"^[\w\s]+:")
        except FileNotFoundError:
            print("Plik app_config.json nie znaleziony, tworzę domyślny.")
        except json.JSONDecodeError:
            print("Błąd odczytu app_config.json, używam domyślnych.")
            
        self.update_gui_from_config()

    def save_app_config(self, new_preset: Optional[str] = None):
        """Zapisuje listę presetów i regex do pliku JSON."""
        if new_preset:
            if new_preset in self.recent_presets:
                self.recent_presets.remove(new_preset) # Przesuń na górę
            self.recent_presets.insert(0, new_preset)
            self.recent_presets = self.recent_presets[:10] # Ogranicz do 10
            
        self.last_regex = self.regex_var.get()
            
        config = {
            'recent_presets': self.recent_presets,
            'last_regex': self.last_regex
        }
        
        try:
            with open(APP_CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2)
        except Exception as e:
            print(f"Błąd zapisu app_config.json: {e}", file=sys.stderr)

    def update_gui_from_config(self):
        """Aktualizuje Combobox i pole Regex na podstawie wczytanej konfiguracji."""
        self.preset_combo['values'] = self.recent_presets
        if self.recent_presets:
            self.preset_var.set(self.recent_presets[0])
        self.regex_var.set(self.last_regex)

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

        # Zapisz obecne ustawienia jako domyślne na następny raz
        self.save_app_config()

        # Wyczyść flagę stop i kolejkę
        stop_event.clear()
        while not audio_queue.empty():
            try: audio_queue.get_nowait()
            except queue.Empty: break
        
        # Uruchom wątki
        self.player_thread = PlayerThread()
        self.reader_thread = ReaderThread(config_path, regex_pattern)
        
        self.player_thread.start()
        self.reader_thread.start()
        
        self.toggle_ui_state(running=True)

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
        if self.reader_thread and self.reader_thread.is_alive():
            print("Zamykanie - zatrzymywanie wątków...")
            self.stop_reading()
        self.root.destroy()

# ==============================================================================
# GŁÓWNA FUNKCJA URUCHOMIENIOWA
# ==============================================================================

def main():
    if not check_dependencies():
        print("\nNie spełniono zależności. Zamykanie.", file=sys.stderr)
        # Pokaż błąd także w okienku, jeśli tkinter jest dostępny
        try:
            root = tk.Tk()
            root.withdraw() # Ukryj główne okno
            messagebox.showerror("Błąd zależności", "Nie znaleziono wymaganych programów (np. spectacle, tesseract).\nZainstaluj je i spróbuj ponownie.\n\nSzczegóły znajdziesz w konsoli.")
            root.destroy()
        except tk.TclError:
            pass # Nie można nawet uruchomić tkinter
        sys.exit(1)

    print("Uruchamianie aplikacji GUI...")
    root = tk.Tk()
    app = GameReaderApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()