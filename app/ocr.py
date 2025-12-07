import sys
import re
import os
import platform
import tempfile
from typing import Optional, Tuple

try:
    import pytesseract
    from pytesseract import Output
    from PIL import Image, ImageOps, ImageEnhance, ImageStat
except ImportError:
    print("Brak biblioteki Pillow lub pytesseract.", file=sys.stderr)
    sys.exit(1)

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


def preprocess_image(image: Image.Image, scale: float = 1.0,
                     grayscale: bool = False, contrast: bool = False) -> Image.Image:
    try:
        # Skalowanie tylko jeśli jest istotna różnica (>5%), oszczędność CPU
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
    """
    Sprawdza, czy obraz ma wystarczającą wariancję (tekst vs tło).
    :param threshold: Próg odchylenia standardowego.
    """
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
    Używa pytesseract.image_to_data, aby znaleźć bounding box wokół faktycznego tekstu.
    Zwraca (left, top, right, bottom) lub None.
    """
    try:
        # Używamy Output.DICT, aby łatwo przetwarzać dane
        data = pytesseract.image_to_data(image, lang=OCR_LANGUAGE, output_type=Output.DICT)

        n_boxes = len(data['text'])
        min_l, min_t = image.width, image.height
        max_r, max_b = 0, 0
        found = False

        for i in range(n_boxes):
            # Ignoruj puste teksty lub bardzo niską pewność (szum)
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
                   auto_remove_names: bool = True, empty_threshold: float = 0.15) -> str:
    """
    Główna funkcja OCR.
    :param empty_threshold: Próg detekcji pustego obrazu. 0.0 wyłącza sprawdzanie.
    """
    # 1. Optymalizacja: Pomiń puste klatki (tylko jeśli threshold > 0)
    if empty_threshold > 0.001:
        if is_image_empty(image, empty_threshold):
            return ""

    # 2. Wykonanie OCR
    try:
        if HAS_CONFIG_FILE:
            config_str = f'--psm 6 "{CONFIG_FILE_PATH}"'
            text = pytesseract.image_to_string(image, lang=OCR_LANGUAGE, config=config_str)
        else:
            text = pytesseract.image_to_string(image, lang=OCR_LANGUAGE, config='--psm 6')

    except Exception:
        # Retry bez configu
        try:
            text = pytesseract.image_to_string(image, lang=OCR_LANGUAGE, config='--psm 6')
        except Exception:
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