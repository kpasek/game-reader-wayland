import json
import os
import re
import sys
import unicodedata

from typing import Any, Dict, List, Optional, Tuple

import pyscreenshot as ImageGrab
import pytesseract

from PIL import Image
from thefuzz import fuzz

OCR_LANGUAGE = 'pol'
MIN_MATCH_THRESHOLD = 75

def normalize_unicode(text):

    text = unicodedata.normalize("NFKC", text)
    return text

def remove_noise(text):
    # Zostawiamy: polskie litery, cyfry, .,:;!?'"()-
    return re.sub(r"[^0-9A-Za-zĄąĆćĘęŁłŃńÓóŚśŹźŻż.,:;!?\"'\(\)\-\s]+", " ", text)

def normalize_spaces(text):
    return re.sub(r"\s+", " ", text).strip()

POLISH_SHORT_WORDS = {"i", "w", "o", "a", "u", "z", "do", "na"}

def remove_short_noise_words(text, min_len=2):
    cleaned = []
    for w in text.split():
        if len(w) < min_len and w.lower() not in POLISH_SHORT_WORDS:
            continue
        cleaned.append(w)
    return " ".join(cleaned)

def similar_char_map(text):
    replacements = {
        "0": "O",
        "1": "I",
        "5": "S",
        "/": "l",
        "|": "l",
        "‘": "'",
        "’": "'",
        "“": '"',
        "”": '"'
    }
    for bad, good in replacements.items():
        text = text.replace(bad, good)
    return text

def _smart_remove_name(text: str) -> str:
    """
    Usuwa imię postaci, jeśli wykryje separator (np. 'Imię - Kwestia').
    Działa lepiej niż sztywny regex dla długich nazw (np. 'Wojownik z klanu - Cześć').
    """
    separators = [":", "-", "—", "–", ";"]

    for sep in separators:
        if sep in text:
            parts = text.split(sep, 1)
            # Jeśli lewa strona (imię) jest krótsza niż 40 znaków, a prawa (tekst) niepusta
            if len(parts) == 2 and len(parts[0]) < 40 and parts[1].strip():
                return parts[1].strip()
    return text

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
        return ImageGrab.grab()

    except Exception as e:
        print(f"BŁĄD: Nieoczekiwany błąd podczas przechwytywania (KDE): {e}", file=sys.stderr)


def capture_screen_region(monitor_config: Dict[str, int]) -> Optional[Image.Image]:
    """Wykonuje zrzut całego ekranu i kadruje go do pożądanego regionu."""
    try:
        left = monitor_config['left']
        top = monitor_config['top']
        width = monitor_config['width']
        height = monitor_config['height']

        crop_box = (left, top, left + width, top + height)
        return ImageGrab.grab(crop_box, False)

    except Exception as e:
        print(
            f"BŁĄD: Błąd podczas przechwytywania regionu: {e}", file=sys.stderr)
        return None


def ocr_and_clean_image(image: Image.Image, regex_pattern: str) -> str:
    """Wykonuje OCR i usuwa tekst pasujący do regex oraz inteligentnie usuwa imiona."""
    try:
        # Dodano config '--psm 6' (zakłada blok tekstu), co często poprawia wyniki w grach
        text = pytesseract.image_to_string(image, lang=OCR_LANGUAGE, config='--psm 6').strip()
        text = text.replace('\n', ' ')

        if not text:
            return ""

        if regex_pattern:
            try:
                text = re.sub(regex_pattern, "", text).strip()
            except re.error as e:
                print(f"OSTRZEŻENIE: Błędny Regex: {e}", file=sys.stderr)

            text = _smart_remove_name(text)

        return text

    except Exception as e:
        print(f"BŁĄD: Błąd podczas OCR: {e}", file=sys.stderr)
        return ""

def _clean(text: str) -> str:
    """Szybkie czyszczenie tekstu z artefaktów OCR (bez dużego kosztu)."""
    if not text:
        return ""
    text = normalize_unicode(text)
    text = similar_char_map(text)
    text = remove_noise(text)
    text = normalize_spaces(text)
    text = remove_short_noise_words(text)
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
    # Większość "napisów" o długości 1 to błędy OCR (szumy, krawędzie).
    # Wyjątkiem są dialogi typu "A?", "No.", ale zazwyczaj mają interpunkcję.
    if len(ocr_text) < 2:
        return None

    if mode == "Partial Lines":
        best_score = 0
        best_index = -1

        ocr_lower = ocr_text.lower()
        ocr_len = len(ocr_lower)

        for i, line in enumerate(subtitles_list):
            if not line:
                continue
            line_lower = line.lower()
            line_len = len(line_lower)

            len_diff = abs(ocr_len - line_len)

            if ocr_len < 5:
                if len_diff > 1:
                    continue
            else:
                if len_diff > ocr_len * 0.8:
                    continue
            if ocr_len < 8:
                score = fuzz.ratio(ocr_lower, line_lower)
            else:
                score = _best_prefix_match(ocr_text, line)

            if score > best_score:
                best_score = score
                best_index = i

                if best_score > 97:
                    break

        if ocr_len < 5:
            threshold = 95
        elif ocr_len < 15:
            threshold = 80
        else:
            threshold = 70

        if best_index >= 0 and best_score >= threshold:
            return best_index, best_score

        return None

    best_score = 0
    best_index = -1

    for i, sub_line in enumerate(subtitles_list):
        sub_line = _clean(sub_line)
        if not sub_line:
            continue

        ocr_len = len(ocr_text)
        sub_len = len(sub_line)
        if sub_len == 0:
            continue
        if ocr_len < sub_len * 0.5 or ocr_len > sub_len * 2.0:
            continue

        if ocr_len < 15:
            score = fuzz.ratio(sub_line, ocr_text)
            min_score = 90
        else:
            score = fuzz.token_set_ratio(sub_line, ocr_text)
            if ocr_len < 30:
                min_score = 82
            else:
                min_score = 75

        if score >= min_score and score > best_score:
            best_score = score
            best_index = i

    if best_index >= 0:
        print(f"Dopasowano (token_set_ratio: {best_score}%): Linia {best_index + 1}")
        return best_index, best_score
    else:
        print(f"Brak dopasowania (Najlepszy wynik: {best_score}%)")
        return None
