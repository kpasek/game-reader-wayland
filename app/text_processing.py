import re


def smart_remove_name(text: str) -> str:
    """
    Inteligentnie usuwa imiona z początku linii, np.:
    'Geralt: Witaj.' -> 'Witaj.'
    'V: Nie.' -> 'Nie.'
    """
    if not text:
        return ""

    # Standardowe formaty: "Imię: Dialog" lub "Imię - Dialog"
    match = re.match(r'^[\w\sąćęłńóśźżĄĆĘŁŃÓŚŹŻ]+[:：;_\-]\s*(.+)', text)
    if match:
        return match.group(1)

    return text


def clean_text(text: str) -> str:
    """
    Normalizuje tekst do porównywania.
    Usuwa tagi techniczne <...>, nawiasy (...) i [...].
    """
    if not text:
        return ""

    # 1. USUWANIE TAGÓW I NAWIASÓW
    text = re.sub(r'<[^>]+>|\[[^]]+\]|\([^)]+\)', ' ', text)

    # 2. Usuwanie znaków specjalnych (zostawiamy polskie litery, cyfry i podst. interpunkcję)
    text = re.sub(r'[^\w\sąćęłńóśźżĄĆĘŁŃÓŚŹŻ?!.,]', ' ', text)

    # 3. Redukcja wielokrotnych spacji do jednej
    text = re.sub(r'\s+', ' ', text).strip()

    return text.lower()


def filter_short_words(text: str, min_len: int = 4) -> str:
    """
    Usuwa słowa krótsze niż min_len z wyczyszczonego tekstu.
    Używane do eliminacji szumu OCR, np. 'IA MI' zostaje usunięte.
    """
    if not text:
        return ""

    words = text.split()
    # Zostawiamy tylko te słowa, których długość jest równa lub większa min_len
    filtered_words = [word for word in words if len(word) >= min_len]

    return " ".join(filtered_words)