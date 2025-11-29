import re


def smart_remove_name(text: str) -> str:
    """
    Inteligentnie usuwa imiona z początku linii PRZED czyszczeniem znaków.
    """
    if not text:
        return ""

    pattern = r"^([\w\s'’]{2,25}?)\s*([:;_\-»>|]+)\s*(.+)$"

    match = re.match(pattern, text)
    if match:
        return match.group(3).strip()

    return text


def clean_text(text: str) -> str:
    """
    Normalizuje tekst do porównywania.
    """
    if not text:
        return ""

    # 1. Usuwanie tagów i nawiasów (informacje techniczne)
    text = re.sub(r'<[^>]+>|\[[^]]+\]|\([^)]+\)', ' ', text)

    # 2. Usuwanie znaków specjalnych
    # Zostawiamy litery (polskie też) i cyfry. Usuwamy interpunkcję, bo myli fuzzy match.
    text = re.sub(r'[^\w\sąćęłńóśźżĄĆĘŁŃÓŚŹŻ0-9]', ' ', text)

    # 3. Redukcja spacji i lowercase
    text = re.sub(r'\s+', ' ', text).strip().lower()

    return text


def filter_short_words(text: str, min_len: int = 3) -> str:
    """
    Usuwa krótkie śmieci, ale zachowuje sens.
    """
    if not text:
        return ""

    words = text.split()
    # Zostawiamy słowa >= min_len.
    # Wyjątek: Zostawiamy 'nie', 'no', 'co', 'ty', 'ja' itp. jeśli są poprawne,
    # ale tutaj prościej jest po prostu odsiać 1-2 literowe krzaki z OCR.
    filtered_words = [word for word in words if len(word) >= min_len]

    # Jeśli filtr usunął wszystko (np. "No co"), to przywracamy oryginał
    if not filtered_words and words:
        return text

    return " ".join(filtered_words)