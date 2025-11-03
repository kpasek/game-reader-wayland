#!/usr/bin/env python3

"""
Game Reader - zamiennik dla Wayland
Autor: AI (Gemini)
Data: 27.10.2025

Wymagania systemowe:
- tesseract-ocr (silnik OCR)
- tesseract-data-pol (lub inny pakiet językowy dla OCR)

Wymagania Python (pip install):
- pillow (PIL)
- pytesseract
- pygame (do odtwarzania audio)
- thefuzz (lub fuzzywuzzy)
"""

import json
import os
import sys
import time
import io
import subprocess
import shutil
import tempfile

from typing import List, Dict, Any, Optional

# --- Importowanie zależności ---
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

# --- Konfiguracja ---
CONFIG_FILE_NAME = 'preset.json'
# Język OCR (musi być zgodny z zainstalowanym pakietem tesseract-data-*)
OCR_LANGUAGE = 'pol'
# Minimalny próg dopasowania tekstu (0-100). Im wyższy, tym dokładniejszy musi być OCR.
MIN_MATCH_THRESHOLD = 85
# Bufor, aby nie odtwarzać w kółko tego samego napisu
LAST_PLAYED_INDEX = -1
LAST_OCR_TEXT = ""

def check_dependencies():
    """Sprawdza, czy wymagane programy systemowe (spectacle, tesseract) są zainstalowane."""
    print("Sprawdzanie zależności systemowych...")
    if not shutil.which("spectacle"):
        print("BŁĄD: Nie znaleziono polecenia 'spectacle'.", file=sys.stderr)
        print("Upewnij się, że 'spectacle' jest zainstalowany i dostępny w PATH.", file=sys.stderr)
        print("Instalacja (np. Debian/Ubuntu): sudo apt install spectacle", file=sys.stderr)
        sys.exit(1)
        
    if not shutil.which("tesseract"):
        print("BŁĄD: Nie znaleziono polecenia 'tesseract'.", file=sys.stderr)
        print("Upewnij się, że 'tesseract-ocr' jest zainstalowany.", file=sys.stderr)
        print(f"Instalacja (np. Debian/Ubuntu): sudo apt install tesseract-ocr tesseract-ocr-{OCR_LANGUAGE}", file=sys.stderr)
        sys.exit(1)
    print("Zależności systemowe OK.")

def load_config(filename: str) -> Dict[str, Any]:
    """Wczytuje plik konfiguracyjny JSON."""
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"BŁĄD: Nie znaleziono pliku konfiguracyjnego: {filename}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError:
        print(f"BŁĄD: Błąd parsowania pliku JSON: {filename}", file=sys.stderr)
        sys.exit(1)

def load_text_file(filepath: str) -> List[str]:
    """Wczytuje plik tekstowy (napisy lub imiona) do listy."""
    if not os.path.exists(filepath):
        print(f"OSTRZEŻENIE: Nie znaleziono pliku: {filepath}", file=sys.stderr)
        return []
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            # Wczytuje linie, usuwa białe znaki z początku/końca i filtruje puste linie
            lines = [line.strip() for line in f if line.strip()]
        return lines
    except Exception as e:
        print(f"BŁĄD: Nie można wczytać pliku {filepath}: {e}", file=sys.stderr)
        return []

def capture_screen_region(monitor_config: Dict[str, int]) -> Optional[Image.Image]:
    """Wykonuje zrzut całego ekranu (KDE) przy użyciu pliku tymczasowego i kadruje go."""
    
    temp_file_path = None
    try:
        left = monitor_config['left']
        top = monitor_config['top']
        width = monitor_config['width']
        height = monitor_config['height']
        
        # Definicja obszaru do wycięcia (bounding box)
        crop_box = (left, top, left + width, top + height)
        
        # 1. Utwórz bezpieczny plik tymczasowy z rozszerzeniem .png
        #    'delete=False' jest ważne, abyśmy mogli sami kontrolować usunięcie
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tf:
            temp_file_path = tf.name
            
        # 2. Wywołanie 'spectacle', aby zapisało zrzut do pliku
        #    Używamy '-f' (fullscreen) zamiast '-m', aby objąć wszystkie monitory
        #    co gwarantuje, że współrzędne (left, top) będą pasować.
        command = ['spectacle', '-f', '-b', '-n', '-o', temp_file_path]
        subprocess.run(command, check=True, timeout=2.0)
        
        # 3. Otwórz obraz z pliku tymczasowego
        #    Używamy 'with', aby mieć pewność, że plik zostanie zamknięty
        with Image.open(temp_file_path) as full_screenshot:
            # 4. Wykadruj obraz i zwróć jego kopię
            cropped_image = full_screenshot.crop(crop_box)
            # Zwracamy kopię, ponieważ oryginalny obraz (full_screenshot)
            # zostanie zamknięty po wyjściu z bloku 'with'
            return cropped_image.copy()

    except FileNotFoundError:
        print("BŁĄD: Nie znaleziono polecenia 'spectacle'.", file=sys.stderr)
        print("Upewnij się, że jest zainstalowane.", file=sys.stderr)
        return None
    except subprocess.CalledProcessError as e:
        print(f"BŁĄD: 'spectacle' zakończył działanie z błędem: {e}", file=sys.stderr)
    except subprocess.TimeoutExpired:
        print("BŁĄD: Przekroczono limit czasu dla 'spectacle'.", file=sys.stderr)
    except Exception as e:
        print(f"BŁĄD: Nieoczekiwany błąd podczas przechwytywania (KDE): {e}", file=sys.stderr)
        return None
    finally:
        # 5. Zawsze sprzątaj po sobie - usuń plik tymczasowy
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.remove(temp_file_path)
            except OSError as e:
                print(f"OSTRZEŻENIE: Nie można usunąć pliku tymczasowego {temp_file_path}: {e}", file=sys.stderr)
    
    return None

def ocr_and_clean_image(
    image: Image.Image, 
    names_list: List[str], 
    remove_names_enabled: bool
) -> str:
    """Wykonuje OCR na obrazie i opcjonalnie usuwa imiona postaci."""
    try:
        # Użyj Tesseract do odczytania tekstu
        text = pytesseract.image_to_string(image, lang=OCR_LANGUAGE).strip()
        
        # Zastąp znaki nowej linii spacjami, bo napisy bywają wieloliniowe
        text = text.replace('\n', ' ')
        
        if not text:
            return ""

        # Logika usuwania imion (jeśli włączone)
        if remove_names_enabled and names_list:
            text_lower = text.lower()
            for name in names_list:
                # Sprawdzamy format "IMIĘ: Treść napisu"
                name_prefix = name.lower() + ":"
                if text_lower.startswith(name_prefix):
                    # Znajdź pozycję dwukropka w oryginalnym tekście
                    colon_pos = text.find(':')
                    if colon_pos != -1:
                        # Zwróć tekst po dwukropku
                        return text[colon_pos + 1:].strip()
        
        return text

    except Exception as e:
        print(f"BŁĄD: Błąd podczas OCR: {e}", file=sys.stderr)
        return ""

def find_best_match(ocr_text: str, subtitles_list: List[str]) -> Optional[int]:
    """Znajduje najlepsze dopasowanie dla tekstu OCR w liście napisów."""
    global LAST_OCR_TEXT
    
    # Prosty bufor, aby nie przetwarzać w kółko tego samego tekstu
    if ocr_text == LAST_OCR_TEXT:
        return None
    LAST_OCR_TEXT = ocr_text

    print(f"\nOCR odczytał: '{ocr_text}'")
    
    best_score = 0
    best_index = -1

    # Używamy 'token_set_ratio' - jest dobry na drobne błędy OCR i brakujące słowa
    for i, sub_line in enumerate(subtitles_list):
        score = fuzz.token_set_ratio(ocr_text, sub_line)
        
        if score > best_score:
            best_score = score
            best_index = i

    if best_score >= MIN_MATCH_THRESHOLD:
        print(f"Dopasowano (wynik: {best_score}%): Linia {best_index + 1}: '{subtitles_list[best_index]}'")
        return best_index
    else:
        print(f"Brak wystarczającego dopasowania (Najlepszy wynik: {best_score}%)")
        return None

def play_audio(line_index: int, audio_dir: str, subtitles_list: List[str]):
    """Odtwarza plik audio odpowiadający danemu indeksowi linii."""
    global LAST_PLAYED_INDEX
    
    # Nie odtwarzaj ponownie tej samej linii
    if line_index == LAST_PLAYED_INDEX:
        return
        
    LAST_PLAYED_INDEX = line_index
    
    # Numer linii to indeks + 1
    line_number = line_index + 1
    
    # Budowanie nazwy pliku zgodnie ze specyfikacją
    file_name = f"output1 ({line_number}).ogg"
    file_path = os.path.join(audio_dir, file_name)
    
    if not os.path.exists(file_path):
        print(f"OSTRZEŻENIE: Nie znaleziono pliku audio: {file_path}", file=sys.stderr)
        return

    try:
        # Przerwij poprzedni dźwięk, jeśli jeszcze gra
        if pygame.mixer.music.get_busy():
            pygame.mixer.music.stop()
            
        pygame.mixer.music.load(file_path)
        pygame.mixer.music.play()
        print(f"Odtwarzam: {file_name}")
    except Exception as e:
        print(f"BŁĄD: Nie można odtworzyć pliku audio {file_path}: {e}", file=sys.stderr)

def main():
    """Główna funkcja programu."""
    global LAST_PLAYED_INDEX, LAST_OCR_TEXT

    check_dependencies()
    
    print(f"Wczytuję konfigurację z: {CONFIG_FILE_NAME}...")
    config = load_config(CONFIG_FILE_NAME)
    
    print(f"Wczytuję napisy z: {config['text_file_path']}...")
    subtitles = load_text_file(config['text_file_path'])
    if not subtitles:
        print("BŁĄD: Plik napisów jest pusty lub nie istnieje. Zamykanie.", file=sys.stderr)
        sys.exit(1)
        
    print(f"Wczytuję imiona z: {config['names_file_path']}...")
    names = load_text_file(config['names_file_path'])
    if not names:
        print("OSTRZEŻENIE: Brak pliku imion. Usuwanie imion może nie działać poprawnie.")

    # Inicjalizacja miksera audio (pygame)
    try:
        pygame.mixer.init()
    except Exception as e:
        print(f"BŁĄD: Nie można zainicjować pygame.mixer: {e}", file=sys.stderr)
        print("Upewnij się, że masz poprawnie skonfigurowane sterowniki audio.", file=sys.stderr)
        sys.exit(1)

    # Ustawienia z pliku konfiguracyjnego
    # Zakładamy, że używamy 'monitor', gdy 'USE_CENTER_LINE_1' jest true
    if not config.get('USE_CENTER_LINE_1', False):
        print("BŁĄD: 'USE_CENTER_LINE_1' jest ustawione na 'false' w konfiguracji.", file=sys.stderr)
        print("Ten skrypt wspiera tylko główny monitor (monitor / USE_CENTER_LINE_1).", file=sys.stderr)
        sys.exit(1)
        
    monitor_config = config['monitor']
    capture_interval = config.get('CAPTURE_INTERVAL', 0.5)
    remove_names = config.get('ENABLE_REMOVE_CHARACTER_NAME', False)
    audio_dir = config['audio_dir']

    print("\n--- Uruchomiono Game Reader (Wayland) ---")
    print(f"Monitorowany region: {monitor_config}")
    print(f"Interwał przechwytywania: {capture_interval}s")
    print(f"Usuwanie imion: {remove_names}")
    print("Naciśnij Ctrl+C aby zakończyć.")

    try:
        while True:
            # 1. Przechwyć region ekranu
            image = capture_screen_region(monitor_config)
            if not image:
                time.sleep(capture_interval)
                continue

            # 2. Wykonaj OCR i wyczyść tekst
            ocr_text = ocr_and_clean_image(image, names, remove_names)
            if not ocr_text:
                # Jeśli nic nie odczytano, zresetuj bufor
                LAST_OCR_TEXT = ""
                time.sleep(capture_interval)
                continue
            
            # 3. Znajdź najlepsze dopasowanie
            best_match_index = find_best_match(ocr_text, subtitles)

            # 4. Jeśli znaleziono nowy, pasujący napis - odtwórz audio
            if best_match_index is not None:
                play_audio(best_match_index, audio_dir, subtitles)

            # 5. Poczekaj przed następnym sprawdzeniem
            time.sleep(capture_interval)

    except KeyboardInterrupt:
        print("\nZamykanie programu...")
    finally:
        pygame.mixer.quit()
        print("Zakończono.")

if __name__ == "__main__":
    main()