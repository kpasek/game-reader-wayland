import re


def smart_remove_name(text: str) -> str:
    """
    Usuwa imiona postaci i separatory z początku linii.
    """
    if not text:
        return ""

    # Regex łapie: Imię (2-25 znaków) + Separator (np. :, -, >) + Reszta
    pattern = r"^([\w\s'’]{2,25}?)\s*([:;_\-»>|]+)\s*(.+)$"

    match = re.match(pattern, text)
    if match:
        return match.group(3).strip()

    return text


def clean_text(text: str) -> str:
    """
    Normalizuje tekst: lowercase, usuwa znaki specjalne (zostawia litery i cyfry).
    """
    if not text:
        return ""

    # 1. Usuwanie tagów technicznych
    text = re.sub(r'<[^>]+>|\[[^]]+\]|\([^)]+\)', ' ', text)

    # 2. Zostawiamy tylko litery (wszystkie języki wspierane przez \w) i cyfry
    # Usuwamy interpunkcję, bo ona myli fuzzy match przy krótkich tekstach
    text = re.sub(r'[^\w\sąćęłńóśźżĄĆĘŁŃÓŚŹŻ0-9]', ' ', text)

    # 3. Redukcja spacji
    text = re.sub(r'\s+', ' ', text).strip().lower()

    return text


def filter_short_words(text: str, min_len: int = 3) -> str:
    """
    BEZKOMPROMISOWE FILTROWANIE SZUMU.
    Usuwa wszystkie słowa krótsze niż min_len (domyślnie 3).
    Jeśli po filtracji nic nie zostanie -> zwraca pusty ciąg.
    """
    if not text:
        return ""

    words = text.split()
    # Zostawiamy TYLKO słowa, które mają 3 lub więcej znaków.
    # Eliminujemy "to", "co", "no", "a", "w" itp., bo generują false-positive.
    filtered_words = [word for word in words if len(word) >= min_len]

    # Jeśli lista jest pusta, zwracamy pusty string.
    # To sygnał dla matchera, żeby w ogóle nie szukał.
    return " ".join(filtered_words)