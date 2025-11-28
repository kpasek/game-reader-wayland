import sys
import re

try:
    import pytesseract
    from PIL import Image, ImageOps, ImageEnhance
except ImportError:
    print("Brak biblioteki Pillow lub pytesseract.", file=sys.stderr)
    sys.exit(1)

from app.text_processing import smart_remove_name

# Konfiguracja języka OCR (można zmienić na 'eng' lub 'pol+eng')
OCR_LANGUAGE = 'pol'


def preprocess_image(image: Image.Image, scale: float = 1.0,
                     grayscale: bool = False, contrast: bool = False) -> Image.Image:
    """
    Przygotowuje obraz do OCR (skalowanie, odbarwianie, kontrast).
    """
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


def recognize_text(image: Image.Image, regex_pattern: str = "") -> str:
    """
    Wykonuje OCR na obrazie i wstępnie filtruje wynik regexem.
    """
    try:
        # psm 6: Zakładamy jednolity blok tekstu
        text = pytesseract.image_to_string(image, lang=OCR_LANGUAGE, config='--psm 6').strip()
        text = text.replace('\n', ' ')

        if not text:
            return ""

        # Usunięcie pasujących fragmentów (np. imion zdefiniowanych w regexie)
        if regex_pattern:
            try:
                text = re.sub(regex_pattern, "", text).strip()
            except re.error:
                pass

        # Dodatkowe inteligentne usuwanie imion (po dwukropkach itp.)
        text = smart_remove_name(text)

        return text
    except Exception:
        return ""