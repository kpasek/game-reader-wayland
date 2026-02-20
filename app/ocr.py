import sys
import os
import platform
import tempfile
from typing import Optional, Tuple, List

from app.config_manager import ConfigManager, AreaConfig

try:
    import pytesseract
    from pytesseract import Output
    from PIL import Image, ImageOps, ImageEnhance, ImageFilter, ImageChops
except ImportError:
    print("Brak biblioteki Pillow lub pytesseract.", file=sys.stderr)
    sys.exit(1)

from app.text_processing import smart_remove_name

# Konfiguracja języka OCR
OCR_LANGUAGE = 'pol'
# Znaków na białej liście używamy w psm 6
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

def check_alignment(bbox: Tuple[int, int, int, int], width: int, align_mode: str, column_ratio: float = 0.25) -> bool:
    """
    Sprawdza czy bbox (obszar tekstu) pasuje do zadanego wyrównania poziomego.
    Implementuje logikę 'słupa' o szerokości np. 20%.
    """
    if not align_mode or align_mode not in ["Center", "Left", "Right"]:
        return True

    left, top, right, bottom = bbox
    text_center_x = (left + right) / 2
    text_width = right - left

    if align_mode == "Left":
        c_min = 0
        c_max = width * column_ratio

    elif align_mode == "Center":
        col_w = width * column_ratio
        center_img = width / 2
        c_min = center_img - (col_w / 2)
        c_max = center_img + (col_w / 2)

    elif align_mode == "Right":
        c_min = width * (1 - column_ratio)
        c_max = width

    if c_min <= text_center_x <= c_max:
        return True

    intersect_left = max(left, c_min)
    intersect_right = min(right, c_max)

    if intersect_right > intersect_left:
        overlap = intersect_right - intersect_left

        if overlap >= text_width:
            return True

        zone_width = c_max - c_min
        if overlap >= zone_width:
            return True

        if text_width > 0:
            coverage = overlap / text_width
            if coverage >= 0.5:
                return True

    return False


def preprocess_image(image: Image.Image, config_manager: ConfigManager, area_config: Optional[AreaConfig] = None, override_colors: Optional[List[str]] = None) -> Tuple[Image.Image, bool, Optional[Tuple[int, int, int, int]]]:
    """
    Zwraca krotkę: (przetworzony_obraz, czy_zawiera_tresc, bbox).
    Przetwarza obraz pod kątem OCR w oparciu o jawną konfigurację.
    """
    try:
        # Pobieranie parametrów z area_config lub config_manager
        if area_config:
            thick = int(area_config.text_thickening)
            thresh = int(area_config.brightness_threshold)
            contr = float(area_config.contrast or 0.0)
            # Priorytet: override_colors > area colors
            cols_source = override_colors if override_colors is not None else area_config.colors
            color_tol = int(area_config.color_tolerance)
            show_debug = bool(area_config.show_debug)
        else:
            thick = int(config_manager.text_thickening)
            thresh = int(config_manager.brightness_threshold)
            contr = float(config_manager.contrast)
            cols_source = override_colors if override_colors is not None else config_manager.subtitle_colors
            color_tol = int(config_manager.color_tolerance)
            show_debug = bool(config_manager.show_debug)

        # Parametry globalne
        color_mode = str(config_manager.text_color_mode)
        scale_factor = float(config_manager.ocr_scale_factor)

        if show_debug:
            print(f"Preprocess area: thinning={thick}, threshold={thresh}, contrast={contr}, color_tol={color_tol}, colors={cols_source}")

        has_valid_colors = any(c for c in (cols_source or []) if c)

        if has_valid_colors:
            image = remove_background(image, [c for c in (cols_source or []) if c], tolerance=color_tol)
            if thick > 0:
                filter_size = (int(thick) * 2) + 1
                image = image.filter(ImageFilter.MaxFilter(filter_size))

        if contr != 0 and not has_valid_colors:
            enhancer = ImageEnhance.Contrast(image)
            image = enhancer.enhance(contr + 1.0)

        effective_text_color = "Light" if has_valid_colors else color_mode

        if effective_text_color != "Mixed":
            image = ImageOps.grayscale(image)
        if effective_text_color == "Dark":
            image = ImageOps.invert(image)

        crop_box = None
        try:
            mask = image.point(lambda x: 255 if x > thresh else 0, '1')
            mask = mask.filter(ImageFilter.MaxFilter(3))
            bbox = mask.getbbox()

            if bbox:
                padding = 4
                left, upper, right, lower = bbox
                width, height = image.size
                left = max(0, left - padding)
                upper = max(0, upper - padding)
                right = min(width, right + padding)
                lower = min(height, lower + padding)
                crop_box = (left, upper, right, lower)

                if (right - left) > 10 and (lower - upper) > 10:
                    image = image.crop(crop_box)
                else:
                    crop_box = (0, 0, image.width, image.height)
            else:
                return image, False, (0, 0, image.width, image.height)
        except Exception as e:
            print(f"Błąd przycinania (mask): {e}")
            crop_box = (0, 0, image.width, image.height)

        if abs(scale_factor - 1.0) > 0.05:
            new_w = int(image.width * scale_factor)
            new_h = int(image.height * scale_factor)
            image = image.resize((new_w, new_h), Image.BICUBIC)

        if color_mode != "Mixed":
            image = ImageOps.invert(image)

        return image, True, crop_box

    except Exception as e:
        print(f"Błąd preprocessingu: {e}", file=sys.stderr)
        return image, True, (0, 0, image.width, image.height)

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


def recognize_text(image: Image.Image, config_manager: ConfigManager) -> str:
    """
    Główna funkcja OCR.
    """
    # Use ConfigManager to read behaviour flags
    # note: we keep backward compatibility by consulting preset dict via helper where needed

    try:
        if HAS_CONFIG_FILE:
            config_str = f'--psm 6 "{CONFIG_FILE_PATH}"'
            text = pytesseract.image_to_string(image, lang=OCR_LANGUAGE, config=config_str)
        else:
            text = pytesseract.image_to_string(image, lang=OCR_LANGUAGE, config='--psm 6')

        if not text:
            print(f"OCR: No text recognized.")
            return ""

        text = text.strip().replace('\n', ' ')
        print(f"OCR: Recognized text: '{text}'")
        if config_manager.auto_remove_names:
            text = smart_remove_name(text)
        return text
    except Exception as e:
        print(f"OCR Error: {e}", file=sys.stderr)
        return ""


def remove_background(image: Image.Image, hex_colors: List[str], tolerance: int = 10) -> Image.Image:
    """
    Tworzy maskę: Białe piksele tam, gdzie kolor jest zbliżony do jednego z podanych.
    Reszta czarna. Używa ImageChops dla wydajności.
    """
    if image.mode != 'RGB':
        image = image.convert('RGB')

    # Pusta czarna maska bazowa
    final_mask = Image.new('L', image.size, 0)

    # Przetwarzamy każdy zdefiniowany kolor
    for c in hex_colors:
        if not (isinstance(c, str) and c.startswith('#') and len(c) == 7):
            continue

        try:
            r = int(c[1:3], 16)
            g = int(c[3:5], 16)
            b = int(c[5:7], 16)
        except ValueError:
            continue

        # 1. Tworzymy obraz wypełniony szukanym kolorem
        solid = Image.new('RGB', image.size, (r, g, b))

        # 2. Obliczamy różnicę między screenshotem a kolorem wzorcowym
        diff = ImageChops.difference(image, solid)

        # 3. Spłaszczamy do skali szarości, żeby ocenić ogólną różnicę
        diff_gray = diff.convert('L')

        # 4. Progowanie z tolerancją.
        mask = diff_gray.point(lambda x: 255 if x < tolerance else 0)

        # 5. Dodajemy wynik do maski głównej (logiczne OR - sumowanie światła)
        final_mask = ImageChops.add(final_mask, mask)

    # Zwracamy wynik jako RGB (Białe napisy na czarnym tle)
    return final_mask.convert('RGB')
def find_text_bounds(image: Image.Image, config_str: str = "") -> Optional[Tuple[int, int, int, int]]:
    """
    Zwraca bbox (x, y, w, h) całego wykrytego tekstu na obrazie,
    lub None, jeśli tekst nie został znaleziony.
    """
    try:
        if not config_str:
             pass

        cfg = f"--psm 6 -l {OCR_LANGUAGE}"
        if HAS_CONFIG_FILE:
             cfg += f" {CONFIG_FILE_PATH}"
        
        data = pytesseract.image_to_data(image, output_type=Output.DICT, config=cfg)
        n_boxes = len(data['level'])
        
        min_x, min_y = float('inf'), float('inf')
        max_x, max_y = float('-inf'), float('-inf')
        found = False
        
        for i in range(n_boxes):
            # level 5 to słowa
            if int(data['level'][i]) == 5 and int(data['conf'][i]) > 0: 
                text = data['text'][i].strip()
                if not text: continue
                
                (x, y, w, h) = (data['left'][i], data['top'][i], data['width'][i], data['height'][i])
                min_x = min(min_x, x)
                min_y = min(min_y, y)
                max_x = max(max_x, x + w)
                max_y = max(max_y, y + h)
                found = True
        
        if found:
            return (int(min_x), int(min_y), int(max_x - min_x), int(max_y - min_y))
        return None
    except Exception as e:
        print(f"Błąd find_text_bounds: {e}", file=sys.stderr)
        return None
