import sys
import re
import os
import platform
import tempfile
from typing import Optional, Tuple

try:
    import pytesseract
    from pytesseract import Output
    from PIL import Image, ImageOps, ImageEnhance, ImageStat, ImageFilter
except ImportError:
    print("Brak biblioteki Pillow lub pytesseract.", file=sys.stderr)
    sys.exit(1)

from app.text_processing import smart_remove_name

# Konfiguracja języka OCR
OCR_LANGUAGE = 'pol'
WHITELIST_CHARS = "aąbcćdeęfghijklłmnńoóprsśtuwyzźżAĄBCĆDEĘFGHIJKLŁMNŃOÓPRSŚTUWYZŹŻ0123456789.,:;-?!()[] "

CONFIG_FILE_PATH = os.path.join(tempfile.gettempdir(), "lektor_ocr_config.txt")
HAS_CONFIG_FILE = False

try:
    with open(CONFIG_FILE_PATH, "w", encoding="utf-8") as f:
        f.write(f"tessedit_char_whitelist {WHITELIST_CHARS}")
    HAS_CONFIG_FILE = True
except Exception as e:
    print(f"Ostrzeżenie: Nie udało się utworzyć pliku config dla OCR: {e}", file=sys.stderr)

if platform.system() == "Windows":
    path_tesseract = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    path_tessdata = r"C:\Program Files\Tesseract-OCR\tessdata"
    if os.path.exists(path_tesseract):
        pytesseract.pytesseract.tesseract_cmd = path_tesseract
        if os.path.exists(path_tessdata):
            os.environ['TESSDATA_PREFIX'] = path_tessdata


def preprocess_image(image: Image.Image, scale: float = 1.0,
                     invert_colors: bool = False,
                     density_threshold: float = 0.015,
                     brightness_threshold: int = 200) -> Tuple[Image.Image, bool, Optional[Tuple[int, int, int, int]]]:
    """
    Zwraca krotkę: (przetworzony_obraz, czy_zawiera_tresc, bbox).
    bbox to krotka (left, top, right, bottom) względem przeskalowanego obrazka.
    """
    try:
        # Konwersja do skali szarości
        image = ImageOps.grayscale(image)

        # dla czarnych napisów należy odwrócić kolory, aby dało się wyszukać obszar z napisami
        if not invert_colors:
            image = ImageOps.invert(image)

        # Wykrywanie obszaru napisów
        crop_box = None
        try:
            mask = image.point(lambda x: 255 if x > brightness_threshold else 0, '1')
            mask = mask.filter(ImageFilter.MaxFilter(5))

            bbox = mask.getbbox()

            if bbox:
                padding = 4  # Margines
                left, upper, right, lower = bbox
                width, height = image.size

                left = max(0, left - padding)
                upper = max(0, upper - padding)
                right = min(width, right + padding)
                lower = min(height, lower + padding)

                crop_box = (left, upper, right, lower)

                # Jeśli wykryty obszar jest podejrzanie mały (np. szum 1x1px), ignorujemy crop
                if (right - left) > 10 and (lower - upper) > 10:
                    image = image.crop(crop_box)
                else:
                    crop_box = (0, 0, image.width, image.height)
            else:
                return image, False, (0, 0, image.width, image.height)

        except Exception as e:
            print(f"Błąd przycinania (mask): {e}")
            crop_box = (0, 0, image.width, image.height)

        # Skalowanie
        if abs(scale - 1.0) > 0.05:
            new_w = int(image.width * scale)
            new_h = int(image.height * scale)
            image = image.resize((new_w, new_h), Image.BICUBIC)

        image = ImageOps.invert(image)

        # 5. Binaryzacja pod OCR
        thresh = 160
        image = image.point(lambda x: 0 if x < thresh else 255, '1')

        # 6. Sprawdzenie gęstości pikseli
        colors = image.getcolors()
        black_pixels = 0
        if colors:
            for count, value in colors:
                if value == 0:
                    black_pixels = count
                    break

        total_pixels = image.width * image.height
        if total_pixels == 0:
            return image, False, None

        density = black_pixels / total_pixels

        is_cropped = (crop_box[2] - crop_box[0]) < (new_w * 0.9) if 'new_w' in locals() else False

        min_pixels = 30 if is_cropped else 80

        if density < density_threshold and black_pixels < min_pixels:
            # Jeśli gęstość jest mała I mało jest pikseli w ogóle -> odrzuć
            # Ale jeśli mamy dużo czarnych pikseli (duży tekst), a gęstość niska (bo dużo tła zostało) -> przepuść
            if black_pixels < min_pixels:
                return image, False, None

        return image, True, crop_box

    except Exception as e:
        print(f"Błąd preprocessingu: {e}", file=sys.stderr)
        return image, True, (0, 0, image.width, image.height)

def is_image_empty(image: Image.Image, threshold: float) -> bool:
    try:
        if image.mode != 'L' and image.mode != '1':
            stat_img = ImageOps.grayscale(image)
        else:
            stat_img = image

        stat = ImageStat.Stat(stat_img)
        return stat.stddev[0] < threshold
    except Exception:
        return False


# ... (reszta funkcji get_text_bounds i recognize_text bez zmian) ...
def get_text_bounds(image: Image.Image) -> Optional[Tuple[int, int, int, int]]:
    """
    Używa pytesseract.image_to_data, aby znaleźć bounding box wokół faktycznego tekstu.
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
                   auto_remove_names: bool = True, empty_threshold: float = 0.15) -> str:
    """
    Główna funkcja OCR.
    """
    # 1. Optymalizacja: Pomiń puste klatki
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

        if not text: return ""

        text = text.strip().replace('\n', ' ')
        if regex_pattern:
            try:
                text = re.sub(regex_pattern, "", text).strip()
            except:
                pass

        if auto_remove_names:
            text = smart_remove_name(text)

        return text
    except Exception:
        return ""