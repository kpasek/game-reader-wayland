import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Any, Dict, List, Optional

import pyscreenshot as ImageGrab
import pytesseract

try:
    from PIL import Image
except ImportError:
    print("Błąd: Nie znaleziono biblioteki 'Pillow'. Zainstaluj ją: pip install Pillow", file=sys.stderr)
    sys.exit(1)

try:
    from thefuzz import fuzz
except ImportError:
    print("Błąd: Nie znaleziono biblioteki 'thefuzz'. Zainstaluj ją: pip install thefuzz", file=sys.stderr)
    sys.exit(1)

OCR_LANGUAGE = 'pol'
MIN_MATCH_THRESHOLD = 75
MAX_LEN_DIFF = 0.15  # Maksymalna różnica długości między OCR a linią napisów (15%)

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


def _capture_fullscreen_image() -> Optional[Image.Image]:
    """Wykonuje zrzut całego ekranu (KDE) przy użyciu pliku tymczasowego (w RAM)."""
    temp_file_path = None
    try:
        # ram_disk = '/dev/shm'
        # temp_dir = ram_disk if os.path.isdir(ram_disk) and os.access(ram_disk, os.W_OK) else None

        # with tempfile.NamedTemporaryFile(suffix='.png', delete=False, dir=temp_dir) as tf:
        #     temp_file_path = tf.name
            
        # command = ['spectacle', '-f', '-b', '-n', '-o', temp_file_path]
        # subprocess.run(command, check=True, timeout=2.0, stderr=subprocess.DEVNULL)

        return ImageGrab.grab() # type: ignore

        
        # return Image.open(temp_file_path)

    except Exception as e:
        if isinstance(e, subprocess.TimeoutExpired):
            print("OSTRZEŻENIE: Timeout 'spectacle' (czy ekran jest zablokowany?)", file=sys.stderr)
        else:
            print(f"BŁĄD: Nieoczekiwany błąd podczas przechwytywania (KDE): {e}", file=sys.stderr)
        return None
    finally:
        # Posprzątaj plik tymczasowy
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.remove(temp_file_path)
            except OSError:
                pass


def capture_screen_region(dbus, monitor_config: Dict[str, int]) -> Optional[Image.Image]:
    """Wykonuje zrzut całego ekranu i kadruje go do pożądanego regionu."""
    try:
        left = monitor_config['left']
        top = monitor_config['top']
        width = monitor_config['width']
        height = monitor_config['height']

        crop_box = (left, top, left + width, top + height)
        return dbus.grab(bbox=crop_box) # type: ignore

        # 1. Zrób pełny zrzut ekranu
        with _capture_fullscreen_image() as full_screenshot:  # type: ignore
            if not full_screenshot:
                return None

            # 2. Wykadruj obraz i zwróć jego kopię
            cropped_image = full_screenshot.crop(crop_box)
            return cropped_image.copy()

    except Exception as e:
        print(
            f"BŁĄD: Błąd podczas kadrowania przechwyconego obrazu: {e}", file=sys.stderr)
        return None

def ocr_and_clean_image(image: Image.Image, regex_pattern: str) -> str:
    """Wykonuje OCR i usuwa tekst pasujący do regex."""
    try:
        text = pytesseract.image_to_string(image, lang=OCR_LANGUAGE).strip()
        text = text.replace('\n', ' ')
        
        if not text:
            return ""

        if regex_pattern:
            try:
                text = re.sub(regex_pattern, "", text).strip()
            except re.error as e:
                print(f"OSTRZEŻENIE: Błędny Regex: {e}", file=sys.stderr)
        
        return text

    except Exception as e:
        print(f"BŁĄD: Błąd podczas OCR: {e}", file=sys.stderr)
        return ""


def find_best_match(ocr_text: str, subtitles_list: List[str], mode: str) -> Optional[int]:
    """Znajduje najlepsze dopasowanie dla tekstu OCR w zależności od trybu."""

    if mode == "Partial Lines":
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
        best_score = 0
        best_index = -1

        for i, sub_line in enumerate(subtitles_list):
            length_ratio = min(len(ocr_text), len(sub_line)) / max(len(ocr_text), len(sub_line))
            adjusted_threshold = MIN_MATCH_THRESHOLD + (1 - length_ratio) * 20
            score = fuzz.ratio(ocr_text, sub_line)
            if score < adjusted_threshold:
                continue
            ocr_len = len(ocr_text)
            sub_len = len(sub_line)
            if sub_len < 10 and ocr_len > 20:
                continue
            if abs(len(ocr_text) - len(sub_line)) > 0.5 * max(len(ocr_text), len(sub_line)):
                continue
            if not (sub_len * (1 - MAX_LEN_DIFF) <= ocr_len <= sub_len * (1 + MAX_LEN_DIFF)):
                continue
            if score > best_score:
                best_score = score
                best_index = i

        if best_index >= 0:
            print(f"Dopasowano w trybie pełnym (wynik: {best_score}%): Linia {best_index + 1}")
            return best_index
        else:
            print(
                f"Brak dopasowania w trybie pełnym (Najlepszy wynik: {best_score}%)")
            return None