import re

VALID_SHORT_WORDS = {
    'a', 'i', 'o', 'u', 'w', 'z',
    'az', 'aż', 'ba', 'bo', 'by', 'ci', 'co', 'da', 'do', 'go', 'ha', 'he', 'hm',
    'ile', 'im', 'iz', 'iż', 'ja', 'je', 'ku', 'ma', 'me', 'mi', 'mu', 'my',
    'na', 'ni', 'no', 'np', 'od', 'oj', 'on', 'ot', 'oz', 'oż', 'pa', 'po',
    'są', 'se', 'si', 'su', 'ta', 'te', 'to', 'tu', 'ty', 'ud', 'ul', 'ut',
    'we', 'wy', 'wu', 'za', 'ze', 'że', 'ół'
}

# --- Wyrażenia regularne ---
RE_NAME_PREFIX = re.compile(r"^([\w\s'’]{2,25}?)\s*([:;_\-»>|]+)\s*(.+)$")
RE_TAGS = re.compile(r'<[^>]+>|\[[^]]+\]|\([^)]+\)')
RE_ALLOWED_CHARS = re.compile(r'[^\w\sąćęłńóśźżĄĆĘŁŃÓŚŹŻ0-9]')
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
    Usuwa tagi, znaki spec., normalizuje spacje i usuwa słowa <= 2 znaki.
    """
    if not text:
        return ""

    # 1. Usuwanie tagów i nawiasów
    text = RE_TAGS.sub(' ', text)

    # 2. Usuwanie znaków niedozwolonych
    text = RE_ALLOWED_CHARS.sub(' ', text)

    # 3. Normalizacja
    text = RE_SPACES.sub(' ', text).strip().lower()

    if not text:
        return ""

    # 4. Rygorystyczne usuwanie krótkich słów (szumu)
    words = text.split()
    cleaned_words = [w for w in words if len(w) > 2]

    if not cleaned_words:
        return ""

    return " ".join(cleaned_words)