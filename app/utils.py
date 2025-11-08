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

from PIL import Image
from thefuzz import fuzz

from app.dbus_ss import FreedesktopDBusWrapper

OCR_LANGUAGE = 'pol'
MIN_MATCH_THRESHOLD = 75
# MAX_LEN_DIFF = 0.1 # Zastąpione nową logiką

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
    try:
        with FreedesktopDBusWrapper() as dbus:
            ss = dbus.grab()
        return ss

    except Exception as e:
        print(f"BŁĄD: Nieoczekiwany błąd podczas przechwytywania (KDE): {e}", file=sys.stderr)


def capture_screen_region(dbus, monitor_config: Dict[str, int]) -> Optional[Image.Image]:
    """Wykonuje zrzut całego ekranu i kadruje go do pożądanego regionu."""
    try:
        left = monitor_config['left']
        top = monitor_config['top']
        width = monitor_config['width']
        height = monitor_config['height']

        crop_box = (left, top, left + width, top + height)
        return ImageGrab.grab(crop_box, False)
        # return dbus.grab(bbox=crop_box) # type: ignore

    except Exception as e:
        print(
            f"BŁĄD: Błąd podczas przechwytywania regionu: {e}", file=sys.stderr)
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

    if not ocr_text:
        return None

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
        
        TOKEN_SET_THRESHOLD = 90
        
        MIN_LEN_RATIO = 0.8
        MAX_LEN_RATIO = 1.5

        for i, sub_line in enumerate(subtitles_list):
            
            score = fuzz.token_set_ratio(ocr_text, sub_line)
            is_long_enough = len(sub_line) >= len(ocr_text) * MIN_LEN_RATIO
            is_not_too_long = len(ocr_text) <= len(sub_line) * MAX_LEN_RATIO
            
            if score >= TOKEN_SET_THRESHOLD and is_long_enough and is_not_too_long:
                
                if score > best_score:
                    best_score = score
                    best_index = i
                elif score == best_score:
                    if best_index == -1 or abs(len(sub_line) - len(ocr_text)) < abs(len(subtitles_list[best_index]) - len(ocr_text)):
                        best_index = i

        if best_index >= 0:
            print(f"Dopasowano w trybie pełnym (token_set_ratio: {best_score}%): Linia {best_index + 1}")
            return best_index
        else:
            print(
                f"Brak dopasowania w trybie pełnym (Najlepszy wynik: {best_score}%)")
            return None