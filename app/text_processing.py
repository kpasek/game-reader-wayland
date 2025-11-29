import re

# Lista poprawnych krótkich słów
VALID_SHORT_WORDS = {
    'a', 'i', 'o', 'u', 'w', 'z',
    'az', 'aż', 'ba', 'bo', 'by', 'ci', 'co', 'da', 'do', 'go', 'ha', 'he', 'hm',
    'ile', 'im', 'iz', 'iż', 'ja', 'je', 'ku', 'ma', 'me', 'mi', 'mu', 'my',
    'na', 'ni', 'no', 'np', 'od', 'oj', 'on', 'ot', 'oz', 'oż', 'pa', 'po',
    'są', 'se', 'si', 'su', 'ta', 'te', 'to', 'tu', 'ty', 'ud', 'ul', 'ut',
    'we', 'wy', 'wu', 'za', 'ze', 'że', 'ół'
}

# --- PREKOMPILOWANE WYRAŻENIA REGULARNE (Dla wydajności) ---
# Wzór na imiona (So'lek - Dialog)
RE_NAME_PREFIX = re.compile(r"^([\w\s'’]{2,25}?)\s*([:;_\-»>|]+)\s*(.+)$")

# Tagi techniczne <...> [..] (...)
RE_TAGS = re.compile(r'<[^>]+>|\[[^]]+\]|\([^)]+\)')

# Znaki dozwolone (reszta usuwana)
RE_ALLOWED_CHARS = re.compile(r'[^\w\sąćęłńóśźżĄĆĘŁŃÓŚŹŻ0-9]')

# Wielokrotne spacje
RE_SPACES = re.compile(r'\s+')


def smart_remove_name(text: str) -> str:
    if not text:
        return ""

    match = RE_NAME_PREFIX.match(text)
    if match:
        return match.group(3).strip()
    return text


def clean_text(text: str) -> str:
    if not text:
        return ""

    # 1. Usuwanie tagów
    text = RE_TAGS.sub(' ', text)

    # 2. Usuwanie znaków specjalnych
    text = RE_ALLOWED_CHARS.sub(' ', text)

    # 3. Lowercase i redukcja spacji
    text = RE_SPACES.sub(' ', text).strip().lower()

    if not text:
        return ""

    # 4. Inteligentne usuwanie szumu (zostawiamy to w Pythonie, bo regex tu nie pomoże)
    words = text.split()

    # Szybka ścieżka: jeśli słowa są długie, nie iterujemy po liście wyjątków
    # (optymalizacja dla większości przypadków)
    if all(len(w) > 2 for w in words):
        return text

    cleaned_words = []
    for word in words:
        if len(word) > 2 or word in VALID_SHORT_WORDS:
            cleaned_words.append(word)

    if not cleaned_words:
        return ""

    return " ".join(cleaned_words)