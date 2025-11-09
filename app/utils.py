import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Any, Dict, List, Optional, Tuple

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

def _clean(text: str) -> str:
    """Szybkie czyszczenie tekstu z artefaktów OCR (bez dużego kosztu)."""
    if not text:
        return ""
    # usuń numerki, interpunkcję, podwójne spacje
    text = re.sub(r"^[\d\W_]+", "", text)        # leading liczby i znaki
    text = re.sub(r"[^0-9A-Za-zÀ-žąćęłńóśżźĄĆĘŁŃÓŚŻŹ\s]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip().lower()


def _best_prefix_match(ocr_text: str, line: str, max_shift: int = 8) -> int:
    """Zwraca najlepszy wynik dopasowania OCR do początku linii (szybko)."""
    ocr_len = len(ocr_text)
    if not line or ocr_len == 0:
        return 0

    best_score = 0

    for shift in range(0, min(max_shift, max(1, len(line) - ocr_len)) + 1):
        fragment = line[shift:shift + ocr_len + 3]  # +3 żeby uwzględnić różnice końcowe
        score = fuzz.ratio(ocr_text, fragment)
        if score > best_score:
            best_score = score
    return best_score


def find_best_match(ocr_text: str, subtitles_list: List[str], mode: str) -> Optional[Tuple[int, int]]:
    """Szybka wersja dopasowania OCR do dialogu. Zwraca (index, score) lub None."""
    if not ocr_text:
        return None

    ocr_text = _clean(ocr_text)
    if not ocr_text:
        return None

    if mode == "Partial Lines":
        best_score = 0
        best_index = -1
        threshold = 90 if len(ocr_text) < 20 else 75

        for i, line in enumerate(subtitles_list):
            if not line:
                continue

            # if len(line) * 0.7 > len(ocr_text):
            #     continue

            score = _best_prefix_match(ocr_text, line)
            if score > best_score:
                best_score = score
                best_index = i

        if best_index >= 0 and best_score >= threshold:
            print(f"Dopasowano fragment (prefix): Linia {best_index + 1}, wynik: {best_score}%")
            return best_index, best_score
        else:
            print(f"Brak dopasowania fragmentu (najlepszy: {best_score}%)")
            return None

    # --- Tryb pełny ---
    best_score = 0
    best_index = -1

    for i, sub_line in enumerate(subtitles_list):
        sub_line = _clean(sub_line)
        if not sub_line:
            continue

        # szybki filtr długości
        ocr_len = len(ocr_text)
        sub_len = len(sub_line)
        if sub_len == 0:
            continue
        if ocr_len < sub_len * 0.5 or ocr_len > sub_len * 2.0:
            continue

        # Logika dopasowania:
        # Dla bardzo krótkich tekstów (np. "Tak", "OK") 'ratio' jest bezpieczniejsze,
        # bo 'token_set_ratio' da 100% dla "Tak" vs "Nie tak".
        # Dla dłuższych, 'token_set_ratio' jest lepsze, bo ignoruje kolejność
        # i drobne błędy OCR (np. "Cześć Adam" vs "Adam cześć").
        if ocr_len < 15:
            score = fuzz.ratio(sub_line, ocr_text)
            min_score = 90  # Musi być prawie identyczne
        else:
            score = fuzz.token_set_ratio(sub_line, ocr_text)
            if ocr_len < 30:
                min_score = 82  # Średni próg
            else:
                min_score = 75  # Standardowy próg

        if score >= min_score and score > best_score:
            best_score = score
            best_index = i

    if best_index >= 0:
        print(f"Dopasowano (token_set_ratio: {best_score}%): Linia {best_index + 1}")
        return best_index, best_score
    else:
        print(f"Brak dopasowania (Najlepszy wynik: {best_score}%)")
        return None
