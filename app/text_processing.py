import re

# Lista poprawnych krótkich słów w języku polskim (1-2 litery).
# Wszystkie inne tokeny 1-2 literowe (np. "h", "4", "xy") będą usuwane jako szum.
VALID_SHORT_WORDS = {
    'a', 'i', 'o', 'u', 'w', 'z',
    'az', 'aż', 'ba', 'bo', 'by', 'ci', 'co', 'da', 'do', 'go', 'ha', 'he', 'hm',
    'ile', 'im', 'iz', 'iż', 'ja', 'je', 'ku', 'ma', 'me', 'mi', 'mu', 'my',
    'na', 'ni', 'no', 'np', 'od', 'oj', 'on', 'ot', 'oz', 'oż', 'pa', 'po',
    'są', 'se', 'si', 'su', 'ta', 'te', 'to', 'tu', 'ty', 'ud', 'ul', 'ut',
    'we', 'wy', 'wu', 'za', 'ze', 'że', 'ół'
}


def smart_remove_name(text: str) -> str:
    """
    Usuwa imiona postaci i separatory z początku linii.
    """
    if not text:
        return ""

    # Regex łapie: Imię (2-25 znaków) + Separator (np. :, -, >) + Reszta
    # Dodano obsługę wielu separatorów OCR
    pattern = r"^([\w\s'’]{2,25}?)\s*([:;_\-»>|]+)\s*(.+)$"
    match = re.match(pattern, text)
    if match:
        return match.group(3).strip()

    return text


def clean_text(text: str) -> str:
    """
    Normalizuje tekst i usuwa śmieciowe tokeny.
    """
    if not text:
        return ""

    # 1. Usuwanie tagów technicznych
    text = re.sub(r'<[^>]+>|\[[^]]+\]|\([^)]+\)', ' ', text)

    # 2. Zostawiamy litery, cyfry i spacje. Usuwamy interpunkcję.
    text = re.sub(r'[^\w\sąćęłńóśźżĄĆĘŁŃÓŚŹŻ0-9]', ' ', text)

    # 3. Lowercase i wstępna redukcja spacji
    text = re.sub(r'\s+', ' ', text).strip().lower()

    if not text:
        return ""

    # 4. INTELIGENTNE USUWANIE SZUMU
    # Dzielimy na słowa i sprawdzamy każde z osobna
    words = text.split()
    cleaned_words = []

    for word in words:
        # Jeśli słowo ma więcej niż 2 litery -> zostawiamy
        if len(word) > 2:
            cleaned_words.append(word)
        # Jeśli ma 1-2 litery, sprawdzamy czy jest na białej liście
        elif word in VALID_SHORT_WORDS:
            cleaned_words.append(word)
        # Jeśli to cyfry, traktujemy jako szum (chyba że to rok 2077, ale w dialogach rzadkie)
        # W dialogach rzadko występują samotne cyfry bez kontekstu
        else:
            continue

            # Jeśli po czyszczeniu nic nie zostało, zwracamy pusty string
    if not cleaned_words:
        return ""

    return " ".join(cleaned_words)


def filter_short_words(text: str, min_len: int = 3) -> str:
    """
    Stara funkcja dla kompatybilności - teraz clean_text robi większość roboty.
    Można jej użyć do bardzo agresywnego filtrowania w razie potrzeby.
    """
    return clean_text(text)