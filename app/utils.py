import json
import os
import re
import sys
import unicodedata
import platform

from typing import Any, Dict, List, Optional, Tuple

# Biblioteki do zrzutów ekranu
import pyscreenshot as ImageGrab

# Próba importu mss dla szybszego przechwytywania (Windows/X11)
try:
    import mss

    HAS_MSS = True
except ImportError:
    HAS_MSS = False
    print("OSTRZEŻENIE: Brak biblioteki 'mss'. Zainstaluj 'pip install mss' dla lepszej wydajności.", file=sys.stderr)

import pytesseract

from PIL import Image
from thefuzz import fuzz

OCR_LANGUAGE = 'pol'
MIN_MATCH_THRESHOLD = 75


# --- Logika wyboru backendu do zrzutów ekranu ---
def _determine_screenshot_backend():
    """
    Decyduje, której biblioteki użyć.
    MSS jest preferowane dla Windows i Linux (X11).
    Dla Wayland wymuszamy pyscreenshot (kompatybilność).
    """
    if not HAS_MSS:
        return 'pyscreenshot'

    system = platform.system().lower()

    # Windows: MSS jest bardzo szybkie
    if system == 'windows':
        return 'mss'

    # Linux
    if system == 'linux':
        # Sprawdzamy typ sesji (X11 czy Wayland)
        session_type = os.environ.get('XDG_SESSION_TYPE', '').lower()
        if 'wayland' in session_type:
            # MSS na Wayland wymaga specyficznej konfiguracji/uprawnień,
            # bezpieczniej zostać przy pyscreenshot (zazwyczaj używa gnome-screenshot/portal)
            return 'pyscreenshot'
        else:
            # X11
            return 'mss'

    # Inne systemy (macOS itp.) - fallback
    return 'pyscreenshot'


SCREENSHOT_BACKEND = _determine_screenshot_backend()
print(f"INFO: Wybrany backend zrzutów ekranu: {SCREENSHOT_BACKEND}")


def normalize_unicode(text):
    text = unicodedata.normalize("NFKC", text)
    return text


def remove_noise(text):
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
    separators = [":", "-", "—", "–", ";"]
    for sep in separators:
        if sep in text:
            parts = text.split(sep, 1)
            if len(parts) == 2 and len(parts[0]) < 40 and parts[1].strip():
                return parts[1].strip()
    return text


def load_config(filename: str) -> Dict[str, Any]:
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
    """Służy do pobrania podglądu całego ekranu (np. przy wyborze obszaru)."""
    try:
        if SCREENSHOT_BACKEND == 'mss':
            with mss.mss() as sct:
                # monitor 1 to zazwyczaj główny ekran lub "all in one" w mss
                monitor = sct.monitors[1]
                sct_img = sct.grab(monitor)
                return Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
        else:
            return ImageGrab.grab()
    except Exception as e:
        print(f"BŁĄD capture fullscreen ({SCREENSHOT_BACKEND}): {e}", file=sys.stderr)
        # Fallback
        try:
            return ImageGrab.grab()
        except:
            return None


def capture_screen_region(monitor_config: Dict[str, int]) -> Optional[Image.Image]:
    """
    Pobiera wycinek ekranu używając wybranego backendu.
    monitor_config oczekuje kluczy: 'top', 'left', 'width', 'height'.
    """
    try:
        # Konwersja na int (dla bezpieczeństwa)
        top = int(monitor_config.get('top', 0))
        left = int(monitor_config.get('left', 0))
        width = int(monitor_config.get('width', 100))
        height = int(monitor_config.get('height', 100))

        if SCREENSHOT_BACKEND == 'mss':
            with mss.mss() as sct:
                # MSS wymaga słownika {top, left, width, height}
                region = {"top": top, "left": left, "width": width, "height": height}
                sct_img = sct.grab(region)

                # Konwersja MSS (BGRA) -> PIL (RGB)
                # mss.tools.to_png to za dużo narzutu, używamy frombytes
                return Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")

        else:
            # Stara metoda (pyscreenshot / ImageGrab)
            # Wymaga krotki (x1, y1, x2, y2)
            crop_box = (left, top, left + width, top + height)
            return ImageGrab.grab(crop_box, False)

    except Exception as e:
        print(f"BŁĄD capture ({SCREENSHOT_BACKEND}): {e}", file=sys.stderr)
        return None


def ocr_and_clean_image(image: Image.Image, regex_pattern: str) -> str:
    try:
        text = pytesseract.image_to_string(image, lang=OCR_LANGUAGE, config='--psm 6').strip()
        text = text.replace('\n', ' ')
        if not text: return ""
        if regex_pattern:
            try:
                text = re.sub(regex_pattern, "", text).strip()
            except re.error:
                pass
            text = _smart_remove_name(text)
        return text
    except Exception:
        return ""


def _clean(text: str) -> str:
    if not text: return ""
    text = normalize_unicode(text)
    text = similar_char_map(text)
    text = remove_noise(text)
    text = normalize_spaces(text)

    if len(text) > 5:
        text = remove_short_noise_words(text)
    if len(text) < 3 and not text.isalpha():
        return ""

    return text.strip().lower()


def find_best_match(ocr_text: str, subtitles_list: List[str], mode: str) -> Optional[Tuple[int, int]]:
    """Dopasowuje OCR do listy dialogów."""
    if not ocr_text:
        return None

    ocr_text = _clean(ocr_text)
    if not ocr_text or len(ocr_text) < 2:
        return None

    if mode == "Partial Lines":
        best_score = 0
        best_index = -1

        ocr_lower = ocr_text.lower()
        ocr_len = len(ocr_lower)

        for i, line in enumerate(subtitles_list):
            if not line: continue
            line_lower = line.lower()
            line_len = len(line_lower)

            prefix_score = 0
            if line_len >= ocr_len:
                fragment = line_lower[:ocr_len + 15]  # +15 marginesu
                prefix_score = fuzz.ratio(ocr_lower, fragment)
            else:
                prefix_score = fuzz.ratio(ocr_lower, line_lower)

            substring_score = 0
            if ocr_len > 10 and line_len > ocr_len:
                substring_score = fuzz.partial_ratio(ocr_lower, line_lower)

            score = max(prefix_score, substring_score)

            if score > best_score:
                best_score = score
                best_index = i
                if best_score > 98:
                    break

        # Progi akceptacji
        threshold = 75
        if ocr_len < 6:
            threshold = 95
        elif ocr_len < 15:
            threshold = 85

        if best_index >= 0 and best_score >= threshold:
            return best_index, best_score

        return None

    # Tryb Full Lines
    best_score = 0
    best_index = -1

    for i, sub_line in enumerate(subtitles_list):
        sub_line = _clean(sub_line)
        if not sub_line: continue

        ocr_len = len(ocr_text)
        sub_len = len(sub_line)
        if sub_len == 0: continue

        if ocr_len < sub_len * 0.5 or ocr_len > sub_len * 2.0:
            continue

        if ocr_len < 15:
            score = fuzz.ratio(sub_line, ocr_text)
            min_score = 90
        else:
            score = fuzz.token_set_ratio(sub_line, ocr_text)
            min_score = 75

        if score >= min_score and score > best_score:
            best_score = score
            best_index = i

    if best_index >= 0:
        return best_index, best_score

    return None