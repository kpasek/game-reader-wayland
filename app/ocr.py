import sys
import re
import os
import platform

try:
    import pytesseract
    from PIL import Image, ImageOps, ImageEnhance
except ImportError:
    print("Brak biblioteki Pillow lub pytesseract.", file=sys.stderr)
    sys.exit(1)

from app.text_processing import smart_remove_name, clean_text

# Konfiguracja języka OCR
OCR_LANGUAGE = 'pol'

# --- KONFIGURACJA WINDOWS ---
if platform.system() == "Windows":
    path_tesseract = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    path_tessdata = r"C:\Program Files\Tesseract-OCR\tessdata"

    if os.path.exists(path_tesseract):
        pytesseract.pytesseract.tesseract_cmd = path_tesseract
        if os.path.exists(path_tessdata):
            os.environ['TESSDATA_PREFIX'] = path_tessdata
        else:
            print(f"BŁĄD KRYTYCZNY: Nie znaleziono folderu tessdata pod: {path_tessdata}", file=sys.stderr)
    else:
        print(f"UWAGA: Nie znaleziono tesseract.exe pod {path_tesseract}. OCR nie zadziała.", file=sys.stderr)


# ----------------------------


def preprocess_image(image: Image.Image, scale: float = 1.0,
                     grayscale: bool = False, contrast: bool = False) -> Image.Image:
    try:
        if scale != 1.0:
            new_w = int(image.width * scale)
            new_h = int(image.height * scale)
            image = image.resize((new_w, new_h), Image.LANCZOS)

        if grayscale:
            image = ImageOps.grayscale(image)

        if contrast:
            enhancer = ImageEnhance.Contrast(image)
            image = enhancer.enhance(2.0)

        return image
    except Exception as e:
        print(f"Błąd preprocessingu obrazu: {e}", file=sys.stderr)
        return image


def recognize_text(image: Image.Image, regex_pattern: str = "", auto_remove_names: bool = True) -> str:
    """
    Wykonuje OCR na obrazie i wstępnie filtruje wynik.
    :param auto_remove_names: Jeśli True, uruchamia smart_remove_name (wycina 'Geralt:').
    """
    try:
        # psm 6: Zakładamy jednolity blok tekstu
        text = pytesseract.image_to_string(image, lang=OCR_LANGUAGE, config='--psm 6').strip()
        text = text.replace('\n', ' ')

        if not text:
            return ""

        # Regex (np. usuwanie konkretnych słów zdefiniowanych w GUI)
        if regex_pattern:
            try:
                text = re.sub(regex_pattern, "", text).strip()
            except re.error:
                pass

        # Inteligentne usuwanie imion (niezależnie od regexa)
        if auto_remove_names:
            text = smart_remove_name(text)

        # Ostateczne czyszczenie ze śmieci (<split>, nawiasy itp)
        # To wywoływane jest zazwyczaj w matcherze, ale tutaj można wstępnie oczyścić do logów
        # Zostawiamy 'raw' text do matchera, który używa swojego clean_text

        return text
    except Exception as e:
        print(f"BŁĄD OCR: {e}", file=sys.stderr)
        return ""