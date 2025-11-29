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