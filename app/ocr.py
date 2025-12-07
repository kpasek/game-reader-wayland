import sys
import re
import os
import platform
import tempfile
import numpy as np
from typing import Optional, Tuple

try:
    import pytesseract
    from pytesseract import Output
    from PIL import Image, ImageOps, ImageEnhance, ImageStat
except ImportError:
    print("Brak biblioteki Pillow lub pytesseract.", file=sys.stderr)
    sys.exit(1)

EASYOCR_READER = None

from app.text_processing import smart_remove_name

# Konfiguracja języka OCR
OCR_LANGUAGE = 'pol'

# Znakowy whitelist (bezpieczny dla shlex/cmd)
WHITELIST_CHARS = "aąbcćdeęfghijklłmnńoóprsśtuwyzźżAĄBCĆDEĘFGHIJKLŁMNŃOÓPRSŚTUWYZŹŻ0123456789.,:;-?!()[] "

# --- TWORZENIE PLIKU KONFIGURACYJNEGO TESSERACTA ---
CONFIG_FILE_PATH = os.path.join(tempfile.gettempdir(), "lektor_ocr_config.txt")
HAS_CONFIG_FILE = False

try:
    with open(CONFIG_FILE_PATH, "w", encoding="utf-8") as f:
        f.write(f"tessedit_char_whitelist {WHITELIST_CHARS}")
    HAS_CONFIG_FILE = True
except Exception as e:
    print(f"Ostrzeżenie: Nie udało się utworzyć pliku config dla OCR: {e}", file=sys.stderr)
# ---------------------------------------------------

# --- KONFIGURACJA WINDOWS ---
if platform.system() == "Windows":
    path_tesseract = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    path_tessdata = r"C:\Program Files\Tesseract-OCR\tessdata"

    if os.path.exists(path_tesseract):
        pytesseract.pytesseract.tesseract_cmd = path_tesseract
        if os.path.exists(path_tessdata):
            os.environ['TESSDATA_PREFIX'] = path_tessdata


# ----------------------------

def _get_easyocr_reader():
    """Inicjalizuje EasyOCR tylko wtedy, gdy jest potrzebny (Lazy Loading)."""
    global EASYOCR_READER
    if EASYOCR_READER is None:
        try:
            import easyocr
            print("Inicjalizacja EasyOCR... (może chwilę potrwać)", file=sys.stderr)
            EASYOCR_READER = easyocr.Reader(['pl'], gpu=True)
        except ImportError:
            print("Błąd: Brak biblioteki easyocr. Zainstaluj ją przez pip.", file=sys.stderr)
            return None
        except Exception as e:
            print(f"Błąd inicjalizacji EasyOCR: {e}", file=sys.stderr)
            return None
    return EASYOCR_READER


def preprocess_image(image: Image.Image, scale: float = 1.0,
                     grayscale: bool = False, contrast: bool = False) -> Image.Image:
    try:
        if abs(scale - 1.0) > 0.05:
            new_w = int(image.width * scale)
            new_h = int(image.height * scale)
            image = image.resize((new_w, new_h), Image.BICUBIC)

        if grayscale:
            image = ImageOps.grayscale(image)

        if contrast:
            enhancer = ImageEnhance.Contrast(image)
            image = enhancer.enhance(2.0)

        return image
    except Exception as e:
        print(f"Błąd preprocessingu obrazu: {e}", file=sys.stderr)
        return image


def is_image_empty(image: Image.Image, threshold: float) -> bool:
    try:
        if image.mode != 'L':
            stat_img = ImageOps.grayscale(image)
        else:
            stat_img = image

        stat = ImageStat.Stat(stat_img)
        return stat.stddev[0] < threshold
    except Exception:
        return False


def get_text_bounds(image: Image.Image) -> Optional[Tuple[int, int, int, int]]:
    """
    Funkcja pomocnicza do wycinania tekstu (używana przy ponownym skanowaniu).
    Na razie zostawiamy implementację opartą na Tesseract, ponieważ jest szybka.
    """
    try:
        data = pytesseract.image_to_data(image, lang=OCR_LANGUAGE, output_type=Output.DICT)
        n_boxes = len(data['text'])
        min_l, min_t = image.width, image.height
        max_r, max_b = 0, 0
        found = False

        for i in range(n_boxes):
            if int(data['conf'][i]) > 10 and data['text'][i].strip():
                (x, y, w, h) = (data['left'][i], data['top'][i], data['width'][i], data['height'][i])
                min_l = min(min_l, x)
                min_t = min(min_t, y)
                max_r = max(max_r, x + w)
                max_b = max(max_b, y + h)
                found = True

        if found:
            return (min_l, min_t, max_r, max_b)
        return None
    except Exception:
        return None


def recognize_text(image: Image.Image, regex_pattern: str = "",
                   auto_remove_names: bool = True, empty_threshold: float = 0.15,
                   engine: str = "Tesseract") -> str:
    """
    Główna funkcja OCR z obsługą wyboru silnika.
    """
    # 1. Optymalizacja: Pomiń puste klatki
    if empty_threshold > 0.001:
        if is_image_empty(image, empty_threshold):
            return ""

    text = ""

    # 2. Wykonanie OCR w zależności od silnika
    try:
        if engine == "EasyOCR":
            reader = _get_easyocr_reader()
            if reader:
                # EasyOCR wymaga tablicy numpy
                image_np = np.array(image)
                # detail=0 zwraca sam tekst jako listę stringów
                results = reader.readtext(image_np, detail=0, paragraph=True)
                text = " ".join(results)
        else:
            # Fallback to Tesseract
            if HAS_CONFIG_FILE:
                config_str = f'--psm 6 "{CONFIG_FILE_PATH}"'
                text = pytesseract.image_to_string(image, lang=OCR_LANGUAGE, config=config_str)
            else:
                text = pytesseract.image_to_string(image, lang=OCR_LANGUAGE, config='--psm 6')

    except Exception as e:
        print(f"Błąd OCR ({engine}): {e}")
        return ""

    # 3. Czyszczenie wyniku
    try:
        if not text:
            return ""

        text = text.strip().replace('\n', ' ')

        if regex_pattern:
            try:
                text = re.sub(regex_pattern, "", text).strip()
            except re.error:
                pass

        if auto_remove_names:
            text = smart_remove_name(text)

        return text
    except Exception:
        return text