import re
from typing import List

# Lista krótkich słów, które są poprawne w języku polskim i nie powinny być usuwane jako szum.
VALID_SHORT_WORDS = {
    'a', 'i', 'o', 'u', 'w', 'z',
    'az', 'aż', 'ba', 'bo', 'by', 'ci', 'co', 'da', 'do', 'go', 'ha', 'he', 'hm',
    'ile', 'im', 'iz', 'iż', 'ja', 'je', 'ku', 'ma', 'me', 'mi', 'mu', 'my',
    'na', 'ni', 'no', 'np', 'od', 'oj', 'on', 'ot', 'oz', 'oż', 'pa', 'po',
    'są', 'se', 'si', 'su', 'ta', 'te', 'to', 'tu', 'ty', 'ud', 'ul', 'ut',
    'we', 'wy', 'wu', 'za', 'ze', 'że', 'ół'
}

# --- Wyrażenia regularne ---
# Wykrywanie prefiksu imienia, np. "Geralt: Witaj" lub "Geralt - Witaj"
RE_NAME_PREFIX = re.compile(r"^([\w\s'’]{2,25}?)\s*([:;_\-»>|]+)\s*(.+)$")
# Usuwanie tagów HTML/XML oraz nawiasów kwadratowych i okrągłych
RE_TAGS = re.compile(r'<[^>]+>|\[[^]]+\]|\([^)]+\)')
# Dozwolone znaki (litery polskie, cyfry, podstawowe znaki). Reszta zamieniana na spacje.
RE_ALLOWED_CHARS = re.compile(r'[^\w\sąćęłńóśźżĄĆĘŁŃÓŚŹŻ0-9]')
# Redukcja wielokrotnych spacji
RE_SPACES = re.compile(r'\s+')


def smart_remove_name(text: str) -> str:
    """
    Usuwa imię postaci mówiącej z początku tekstu, jeśli pasuje do wzorca.
    Np. zamienia "Geralt: Cześć" na "Cześć".

    :param text: Surowy tekst z OCR.
    :return: Tekst bez prefiksu imienia.
    """
    if not text:
        return ""

    match = RE_NAME_PREFIX.match(text)
    if match:
        return match.group(3).strip()
    return text


def clean_text(text: str) -> str:
    """
    Główna funkcja czyszcząca tekst przed dopasowaniem.
    Usuwa znaki specjalne, tagi, nadmiarowe spacje i zamienia na małe litery.
    Filtruje również bardzo krótkie "słowa-śmieci", które nie są na liście wyjątków.

    :param text: Tekst wejściowy.
    :return: Oczyszczony, znormalizowany ciąg znaków.
    """
    if not text:
        return ""

    # 1. Usuwanie tagów i nawiasów
    text = RE_TAGS.sub(' ', text)

    # 2. Usuwanie znaków niedozwolonych
    text = RE_ALLOWED_CHARS.sub(' ', text)

    # 3. Normalizacja (lowercase + spacje)
    text = RE_SPACES.sub(' ', text).strip().lower()

    if not text:
        return ""

    # 4. Inteligentne usuwanie szumu (krótkich zlepków liter)
    words = text.split()

    # Optymalizacja: jeśli wszystkie słowa są długie, zwracamy od razu
    if all(len(w) > 2 for w in words):
        return text

    cleaned_words = []
    for word in words:
        if len(word) > 2 or word in VALID_SHORT_WORDS:
            cleaned_words.append(word)

    if not cleaned_words:
        return ""

    return " ".join(cleaned_words)