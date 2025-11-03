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
import argparse
from typing import Deque, List, Dict, Any, Optional
from collections import deque

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
    from PIL import Image, ImageOps, ImageEnhance
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

from pydub import AudioSegment

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

# ==============================================================================
# KLASA WĄTKU ODTWARZACZA (PLAYER THREAD) - ZMODYFIKOWANA
# ==============================================================================

class PlayerThread(threading.Thread):
    """Wątek, który obsługuje odtwarzanie audio z kolejki z dynamiczną prędkością."""
    def __init__(self):
        super().__init__(daemon=True)
        self.name = "PlayerThread"
        print("Inicjalizacja wątku odtwarzacza...")

    def run(self):
        pygame.mixer.init()
        print("Odtwarzacz audio uruchomiony.")
        
        while not stop_event.is_set():
            try:
                # Czekaj na element w kolejce
                file_path = audio_queue.get(timeout=0.5)
            except queue.Empty:
                continue

            if not os.path.exists(file_path):
                print(f"OSTRZEŻENIE: Nie znaleziono pliku audio: {file_path}", file=sys.stderr)
                audio_queue.task_done()
                continue
            
            try:
                # 1. Sprawdź rozmiar kolejki (PRZED pobraniem elementu)
                queue_size = audio_queue.qsize()

                if queue_size >= 3:
                    speed = 1.3
                elif queue_size == 2:
                    speed = 1.2
                elif queue_size == 1:
                    speed = 1.1
                else:
                    speed = 1.0

                print(
                    f"Odtwarzam: {os.path.basename(file_path)} (Kolejka: {queue_size}, Prędkość: {speed}x)")

                # 2. Załaduj dźwięk przez pydub
                sound = AudioSegment.from_ogg(file_path)

                # 3. Przyspiesz, jeśli trzeba
                if speed > 1.0:
                    sound = sound.speedup(playback_speed=speed)

                # 4. Wyeksportuj do bufora w pamięci RAM
                # Używamy formatu 'wav', ponieważ jest szybszy do załadowania
                # dla pygame i nie wymaga ponownej kompresji.
                with io.BytesIO() as temp_wav:
                    sound.export(temp_wav, format="wav")
                    temp_wav.seek(0)  # Przewiń na początek pliku w pamięci

                    # 5. Załaduj z bufora i odtwórz
                    pygame.mixer.music.load(temp_wav)
                    pygame.mixer.music.play()
                
                # 6. Czekaj na koniec odtwarzania
                while pygame.mixer.music.get_busy() and not stop_event.is_set():
                    time.sleep(0.1)
                    
            except Exception as e:
                print(
                    f"BŁĄD: Nie można przetworzyć/odtworzyć pliku {file_path}: {e}", file=sys.stderr)
            finally:
                audio_queue.task_done()
        
        pygame.mixer.quit()
        print("Odtwarzacz audio zatrzymany.")
# ==============================================================================
# KLASA WĄTKU CZYTELNIKA (READER THREAD)
# ==============================================================================

class ReaderThread(threading.Thread):
    """Wątek, który wykonuje OCR i dodaje napisy do kolejki."""

    # ZMODYFIKOWANE
    def __init__(self, config_path: str, regex_pattern: str, app_settings: Dict[str, Any]):
        super().__init__(daemon=True)
        self.name = "ReaderThread"
        print(f"Inicjalizacja wątku czytelnika z presetem: {config_path}")

        self.config_path = config_path
        self.regex_pattern = regex_pattern
        self.app_settings = app_settings  # <-- NOWE
        self.subtitle_mode = app_settings.get('subtitle_mode', 'Full Lines')

        self.recent_indices: Deque[int] = deque(maxlen=5)  # Bufor 5 ostatnich
        self.last_ocr_text = ""

        # Pobierz ustawienia OCR
        self.ocr_scale = self.app_settings.get('ocr_scale_factor', 1.0)
        self.ocr_grayscale = self.app_settings.get('ocr_grayscale', False)
        self.ocr_contrast = self.app_settings.get('ocr_contrast', False)

    def preprocess_image(self, image: Image.Image) -> Image.Image:
        """Stosuje skalowanie, skalę szarości i kontrast do obrazu przed OCR."""
        try:
            # 1. Skalowanie (jeśli trzeba)
            if self.ocr_scale < 1.0:
                new_width = int(image.width * self.ocr_scale)
                new_height = int(image.height * self.ocr_scale)
                image = image.resize(
                    (new_width, new_height), Image.LANCZOS)  # type: ignore

            # 2. Skala szarości
            if self.ocr_grayscale:
                image = ImageOps.grayscale(image)

            # 3. Kontrast
            if self.ocr_contrast:
                # Ustawienie na 2.0 mocno podbija kontrast
                enhancer = ImageEnhance.Contrast(image)
                image = enhancer.enhance(2.0)

            return image
        except Exception as e:
            print(
                f"BŁĄD: Błąd podczas preprocessingu obrazu: {e}", file=sys.stderr)
            return image  # Zwróć oryginał w razie błędu

    def run(self):
        try:
            print("Wątek czytelnika uruchomiony.")

            config = load_config(self.config_path)
            subtitles = load_text_file(config['text_file_path'])
            if not subtitles:
                print("BŁĄD: Plik napisów jest pusty lub nie istnieje. Zatrzymuję wątek.", file=sys.stderr)
                return

            monitor_config = config['monitor']
            capture_interval = config.get('CAPTURE_INTERVAL', 0.5)
            audio_dir = config['audio_dir']

            print(
                f"Czytelnik rozpoczyna pętlę (Tryb: {self.subtitle_mode}, Bufor: {self.recent_indices.maxlen})...")
            while not stop_event.is_set():
                start_time = time.monotonic()

                image = capture_screen_region(monitor_config)
                if not image:
                    time.sleep(capture_interval)
                    continue

                # 2. NOWY KROK: Preprocessing obrazu
                processed_image = self.preprocess_image(image)

                # 3. OCR
                ocr_text = ocr_and_clean_image(
                    processed_image, self.regex_pattern)

                # ... reszta logiki (kroki 3, 4, 5, 6 z poprzedniej wersji) ...
                if not ocr_text:
                    self.last_ocr_text = ""
                    time.sleep(capture_interval)
                    continue

                if ocr_text == self.last_ocr_text:
                    time.sleep(capture_interval)
                    continue
                self.last_ocr_text = ocr_text
                
                print(f"\nOCR odczytał: '{ocr_text}'")

                best_match_index = find_best_match(
                    ocr_text, subtitles, self.subtitle_mode)

                if best_match_index is not None and best_match_index not in self.recent_indices:  # ZMODYFIKOWANE
                    print(f"Dopasowano (Indeks: {best_match_index}). Dodaję do kolejki.")

                    self.recent_indices.append(
                        best_match_index)  # ZMODYFIKOWANE
                    
                    line_number = best_match_index + 1
                    file_name = f"output1 ({line_number}).ogg"
                    file_path = os.path.join(audio_dir, file_name)

                    audio_queue.put(file_path)

                elapsed = time.monotonic() - start_time
                wait_time = max(0, capture_interval - elapsed)
                time.sleep(wait_time)

        except Exception as e:
            print(f"KRYTYCZNY BŁĄD w wątku czytelnika: {e}", file=sys.stderr)
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
    """Wykonuje zrzut całego ekranu (KDE) przy użyciu pliku tymczasowego (w RAM) i kadruje go."""

    temp_file_path = None
    try:
        left = monitor_config['left']
        top = monitor_config['top']
        width = monitor_config['width']
        height = monitor_config['height']
        
        crop_box = (left, top, left + width, top + height)
        
        # NOWA LOGIKA: Użyj /dev/shm (RAM dysk) jeśli to możliwe
        ram_disk = '/dev/shm'
        temp_dir = ram_disk if os.path.isdir(
            ram_disk) and os.access(ram_disk, os.W_OK) else None

        with tempfile.NamedTemporaryFile(suffix='.png', delete=False, dir=temp_dir) as tf:
            temp_file_path = tf.name
            
        command = ['spectacle', '-f', '-b', '-n', '-o', temp_file_path]
        subprocess.run(command, check=True, timeout=2.0,
                       stderr=subprocess.DEVNULL)  # Dodano stderr=DEVNULL
        
        with Image.open(temp_file_path) as full_screenshot:
            cropped_image = full_screenshot.crop(crop_box)
            return cropped_image.copy()

    except Exception as e:
        # Pomiń błędy timeout, zdarzają się, gdy ekran jest zablokowany
        if isinstance(e, subprocess.TimeoutExpired):
            print(
                "OSTRZEŻENIE: Timeout 'spectacle' (czy ekran jest zablokowany?)", file=sys.stderr)
        else:
            print(
                f"BŁĄD: Nieoczekiwany błąd podczas przechwytywania (KDE): {e}", file=sys.stderr)
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


def find_best_match(ocr_text: str, subtitles_list: List[str], mode: str) -> Optional[int]:
    """Znajduje najlepsze dopasowanie dla tekstu OCR w zależności od trybu."""

    # ... (kod dla "Partial Lines" pozostaje bez zmian) ...
    if mode == "Partial Lines":
        # ... (bez zmian) ...
        threshold = 95 if len(ocr_text) < 15 else 90

        matches = []
        for i, line in enumerate(subtitles_list):
            if len(line) >= len(ocr_text):
                score = fuzz.partial_ratio(ocr_text, line)
                if score >= threshold:
                    matches.append((i, score))

        if len(matches) == 1:
            index, score = matches[0]
            print(f"Dopasowano częściowo (wynik: {score}%): Linia {index + 1}")
            return index
        elif len(matches) > 1:
            print(
                f"Znaleziono {len(matches)} częściowych dopasowań. Czekam na więcej tekstu.")
            return None
        else:
            print(f"Brak dopasowania częściowego (Próg: {threshold}%)")
            return None

    else:
        # TRYB PEŁNY (domyślny) - ZMODYFIKOWANY
        best_score = 0
        best_index = -1

        for i, sub_line in enumerate(subtitles_list):
            score = fuzz.token_set_ratio(ocr_text, sub_line)
            if score > best_score:
                best_score = score
                best_index = i

        if best_score >= MIN_MATCH_THRESHOLD:
            # NOWA WERYFIKACJA: Sprawdź stosunek długości
            ocr_len = len(ocr_text)
            sub_len = len(subtitles_list[best_index])

            # Jeśli tekst OCR jest o ponad 40% krótszy niż linia napisów,
            # to prawdopodobnie złe dopasowanie (np. "Gotowi" pasujące do "Jesteśmy gotowi...")
            # Ignoruj dla bardzo krótkich linii
            if ocr_len < (sub_len * 0.6) and sub_len > 20:
                print(
                    f"Odrzucono dopasowanie (wynik: {best_score}%): Tekst OCR ('{ocr_text}') za krótki w stosunku do linii ({best_index+1}).")
                return None

            print(
                f"Dopasowano w trybie pełnym (wynik: {best_score}%): Linia {best_index + 1}")
            return best_index
        else:
            print(
                f"Brak dopasowania w trybie pełnym (Najlepszy wynik: {best_score}%)")
            return None
# ==============================================================================
# KLASA OKNA USTAWIEŃ
# ==============================================================================


class SettingsDialog(tk.Toplevel):
    """Okno dialogowe do edycji ustawień aplikacji."""

    def __init__(self, parent, settings: Dict[str, Any]):
        super().__init__(parent)
        self.transient(parent)
        self.title("Ustawienia")

        self.settings = settings
        self.result = None

        # Zmienne Tkinter
        self.subtitle_mode_var = tk.StringVar(
            value=self.settings.get('subtitle_mode', 'Full Lines'))
        self.ocr_scale_var = tk.DoubleVar(
            value=self.settings.get('ocr_scale_factor', 1.0))
        self.ocr_grayscale_var = tk.BooleanVar(
            value=self.settings.get('ocr_grayscale', False))
        self.ocr_contrast_var = tk.BooleanVar(
            value=self.settings.get('ocr_contrast', False))

        frame = ttk.Frame(self, padding="10")
        frame.pack(fill=tk.BOTH, expand=True)

        # --- Grupa Trybu Napisów ---
        mode_group = ttk.LabelFrame(
            frame, text="Tryb dopasowania napisów", padding="10")
        mode_group.pack(fill=tk.X, pady=5)
        # ... (Radiobuttony bez zmian) ...
        ttk.Radiobutton(
            mode_group, text="Pełne linie", value="Full Lines", variable=self.subtitle_mode_var
        ).pack(anchor=tk.W)
        ttk.Radiobutton(
            mode_group, text="Częściowe linie (eksperymentalne)", value="Partial Lines", variable=self.subtitle_mode_var
        ).pack(anchor=tk.W)

        # --- NOWA GRUPA: Ustawienia OCR ---
        ocr_group = ttk.LabelFrame(
            frame, text="Wydajność i Preprocessing OCR", padding="10")
        ocr_group.pack(fill=tk.X, pady=5)

        # Skalowanie
        scale_frame = ttk.Frame(ocr_group)
        scale_frame.pack(fill=tk.X)
        ttk.Label(scale_frame, text="Skala obrazu:").pack(side=tk.LEFT)
        scale_combo = ttk.Combobox(
            scale_frame,
            textvariable=self.ocr_scale_var,
            values=[1.0, 0.75, 0.5],  # 100%, 75%, 50% # type: ignore
            state="readonly",
            width=5
        )
        scale_combo.pack(side=tk.LEFT, padx=5)
        ttk.Label(scale_frame, text="(mniejsza = szybszy OCR, niższa jakość)").pack(
            side=tk.LEFT)

        # Checkboxy
        ttk.Checkbutton(
            ocr_group, text="Konwertuj do skali szarości", variable=self.ocr_grayscale_var
        ).pack(anchor=tk.W, pady=(5, 0))

        ttk.Checkbutton(
            ocr_group, text="Zwiększ kontrast (może pomóc z dziwnymi czcionkami)", variable=self.ocr_contrast_var
        ).pack(anchor=tk.W)

        # --- Przyciski Zapisz/Anuluj ---
        button_frame = ttk.Frame(frame)
        button_frame.pack(fill=tk.X, side=tk.BOTTOM, pady=(10, 0))
        # ... (Przyciski bez zmian) ...
        ttk.Button(button_frame, text="Anuluj",
                   command=self.destroy).pack(side=tk.RIGHT, padx=5)
        ttk.Button(button_frame, text="Zapisz",
                   command=self.save_and_close).pack(side=tk.RIGHT)

        self.geometry("450x380")  # Zwiększono wysokość
        self.grab_set()
        self.wait_window()

    def save_and_close(self):
        """Aktualizuje słownik ustawień i zamyka okno."""
        self.settings['subtitle_mode'] = self.subtitle_mode_var.get()
        self.settings['ocr_scale_factor'] = self.ocr_scale_var.get()
        self.settings['ocr_grayscale'] = self.ocr_grayscale_var.get()
        self.settings['ocr_contrast'] = self.ocr_contrast_var.get()

        self.result = self.settings
        self.destroy()
# ==============================================================================
# KLASA WYBORU OBSZARU
# ==============================================================================


class AreaSelector(tk.Toplevel):
    """Półprzezroczyste okno do zaznaczania obszaru na ekranie."""

    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent
        self.geometry = None  # (x, y, w, h)

        # Zmienne do rysowania
        self.start_x = None
        self.start_y = None
        self.rect = None

        # Konfiguracja okna
        self.attributes('-fullscreen', True)
        self.attributes('-alpha', 0.2)  # Lekko widoczne tło
        self.attributes('-topmost', True)  # Zawsze na wierzchu

        # Ustawienie "przeklikiwalności" (tylko Linux/X11, może nie działać na Wayland)
        # Niestety, Wayland jest tu trudny. Ale na KDE powinno działać.

        # Płótno do rysowania
        self.canvas = tk.Canvas(self, cursor="cross", bg="black")
        self.canvas.pack(fill=tk.BOTH, expand=True)

        # Powiązania myszy
        self.canvas.bind("<ButtonPress-1>", self.on_mouse_down)
        self.canvas.bind("<B1-Motion>", self.on_mouse_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_mouse_up)

        # Powiązanie klawisza Escape
        self.bind("<Escape>", lambda e: self.destroy())

        print("Gotowy do wyboru obszaru. Naciśnij Esc aby anulować.")
        self.grab_set()
        self.wait_window()

    def on_mouse_down(self, event):
        self.start_x = event.x_root
        self.start_y = event.y_root
        if self.rect:
            self.canvas.delete(self.rect)
        self.rect = self.canvas.create_rectangle(
            self.start_x, self.start_y, self.start_x, self.start_y, outline='red', width=2)

    def on_mouse_drag(self, event):
        cur_x, cur_y = (event.x_root, event.y_root)
        self.canvas.coords(self.rect, self.start_x, self.start_y, cur_x, cur_y)  # type: ignore

    def on_mouse_up(self, event):
        end_x, end_y = (event.x_root, event.y_root)

        # Popraw współrzędne (zawsze od lewego-górnego do prawego-dolnego)
        x = min(self.start_x, end_x)  # type: ignore
        y = min(self.start_y, end_y)  # type: ignore
        w = abs(self.start_x - end_x)
        h = abs(self.start_y - end_y)

        if w > 10 and h > 10:  # Minimalny rozmiar
            self.geometry = {'top': y, 'left': x, 'width': w, 'height': h}
            print(f"Wybrano geometrię: {self.geometry}")
        else:
            print("Wybór anulowany (za mały obszar).")
            self.geometry = None

        self.grab_release()
        self.destroy()

# ==============================================================================
# KLASA APLIKACJI GUI (TKINTER)
# ==============================================================================

class GameReaderApp:
    def __init__(self, root: tk.Tk, autostart_preset: Optional[str], game_command: Optional[List[str]]):        
        self.root = root
        self.root.title("Game Reader (Wayland)")
        self.root.geometry("500x200")
        
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
        self.settings = self.load_app_config()  # ZMODYFIKOWANE
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
            messagebox.showerror(
                "Błąd", "Wybierz prawidłowy plik presetu z listy, zanim wybierzesz obszar.")
            return

        # Ukryj główne okno, aby nie przeszkadzało
        self.root.withdraw()
        time.sleep(0.5)  # Daj systemowi chwilę na ukrycie okna

        try:
            selector = AreaSelector(self.root)
            new_geometry = selector.geometry  # Pobierz wynik (None lub dict)
        finally:
            # Pokaż główne okno z powrotem
            self.root.deiconify()

        if new_geometry:
            try:
                # Wczytaj, zmodyfikuj, zapisz
                with open(preset_path, 'r', encoding='utf-8') as f:
                    preset_data = json.load(f)

                # Nadpisz sekcję 'monitor'
                preset_data['monitor'] = new_geometry

                with open(preset_path, 'w', encoding='utf-8') as f:
                    json.dump(preset_data, f, indent=4)

                messagebox.showinfo(
                    "Sukces", f"Obszar dla presetu '{os.path.basename(preset_path)}' został zaktualizowany.")
            except Exception as e:
                print(
                    f"BŁĄD: Nie można zapisać presetu {preset_path}: {e}", file=sys.stderr)
                messagebox.showerror(
                    "Błąd zapisu", f"Nie można było zapisać pliku presetu: {e}")
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
        
        # Uruchom wątki
        self.player_thread = PlayerThread()
        # Przekaż CAŁY słownik ustawień do wątku czytelnika
        self.reader_thread = ReaderThread(
            config_path, regex_pattern, self.settings)  # <-- ZMODYFIKOWANE
        
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

# ==============================================================================
# GŁÓWNA FUNKCJA URUCHOMIENIOWA
# ==============================================================================

# ==============================================================================
# GŁÓWNA FUNKCJA URUCHOMIENIOWA (NOWA)
# ==============================================================================

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
        
    # --- Sprawdzenie zależności ---
    if not check_dependencies():
        print("\nNie spełniono zależności. Zamykanie.", file=sys.stderr)
        try:
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror("Błąd zależności", "Nie znaleziono wymaganych programów (np. spectacle, tesseract).\nZainstaluj je i spróbuj ponownie.\n\nSzczegóły znajdziesz w konsoli.")
            root.destroy()
        except tk.TclError:
            pass
        sys.exit(1)

    # --- Uruchomienie GUI ---
    print("Uruchamianie aplikacji GUI...")
    root = tk.Tk()
    app = GameReaderApp(root, autostart_preset, game_command)
    root.mainloop()

if __name__ == "__main__":
    main()

if __name__ == "__main__":
    main()