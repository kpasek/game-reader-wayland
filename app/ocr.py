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
elif platform.system() == "Linux":
    local_tesseract_path = os.path.abspath(os.path.join("lib", "tesseract", "tesseract"))
    if os.path.exists(local_tesseract_path):
        pytesseract.pytesseract.tesseract_cmd = local_tesseract_path

def check_alignment(bbox: Tuple[int, int, int, int], width: int, align_mode: str) -> bool:
    """
    Sprawdza czy bbox (obszar tekstu) pasuje do zadanego wyrównania poziomego.
    Implementuje logikę 'słupa' o szerokości np. 20%.
    """
    if not align_mode or align_mode not in ["Center", "Left", "Right"]:
        return True

    left, top, right, bottom = bbox

    if align_mode == "Center":
        col_w = width * 0.15
        center = width / 2
        c_min = center - (col_w / 2)
        c_max = center + (col_w / 2)
    elif align_mode == "Left":
        c_min = 0
        c_max = width * 0.3
    elif align_mode == "Right":
        c_min = width * 0.07
        c_max = width
    else:
        return True

    # --- Logika Walidacji ---
    if left >= c_min and right <= c_max:
        return True

    if left < c_min and right > c_max:
        return True

    intersect_left = max(left, c_min)
    intersect_right = min(right, c_max)

    if intersect_right > intersect_left:
        overlap = intersect_right - intersect_left
        text_width = right - left

        if text_width > 0:
            coverage = overlap / text_width
            if coverage >= 0.8:
                return True

    return False


def preprocess_image(image: Image.Image, scale: float = 1.0,
                     invert_colors: bool = False,
                     density_threshold: float = 0.015,
                     brightness_threshold: int = 200,
                     align_mode: str = "Center") -> Tuple[Image.Image, bool, Optional[Tuple[int, int, int, int]]]:
    """
    Zwraca krotkę: (przetworzony_obraz, czy_zawiera_tresc, bbox).
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
            # Progowanie jasności
            mask = image.point(lambda x: 255 if x > brightness_threshold else 0, '1')

            # Dylatacja (łączenie liter)
            mask = mask.filter(ImageFilter.MaxFilter(5))

            bbox = mask.getbbox()

            if bbox:
                if not check_alignment(bbox, image.width, align_mode):
                    return image, False, None

                padding = 4
                left, upper, right, lower = bbox
                width, height = image.size

                left = max(0, left - padding)
                upper = max(0, upper - padding)
                right = min(width, right + padding)
                lower = min(height, lower + padding)

                crop_box = (left, upper, right, lower)

                # Warunek minimalnego sensownego rozmiaru
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

        is_cropped = (crop_box[2] - crop_box[0]) < (image.width * 0.9) if 'new_w' in locals() else False
        min_pixels = 30 if is_cropped else 80

        if density < density_threshold and black_pixels < min_pixels:
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
    except Exception as e:
        print(f"OCR Error: {e}", file=sys.stderr)
        return ""