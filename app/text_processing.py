import re
import unicodedata

# Słowa krótsze niż 3 litery, które są poprawne w j. polskim (nie usuwamy ich jako szumu)
POLISH_SHORT_WORDS = {"i", "w", "o", "a", "u", "z", "do", "na", "to", "co", "że", "się"}


def normalize_unicode(text: str) -> str:
    """Normalizuje znaki unicode (np. łączenie ogonków)."""
    return unicodedata.normalize("NFKC", text)


def map_similar_chars(text: str) -> str:
    """Zamienia znaki często mylone przez OCR (np. 0 -> O, | -> I)."""
    replacements = {
        "0": "O", "1": "I", "5": "S", "/": "l", "|": "l",
        "‘": "'", "’": "'", "“": '"', "”": '"'
    }
    for bad, good in replacements.items():
        text = text.replace(bad, good)
    return text


def remove_noise(text: str) -> str:
    """Usuwa znaki niebędące literami, cyframi ani podstawową interpunkcją."""
    # Zostawiamy polskie znaki, cyfry i podstawowe znaki przystankowe
    return re.sub(r"[^0-9A-Za-zĄąĆćĘęŁłŃńÓóŚśŹźŻż.,:;!?\"'\(\)\-\s]+", " ", text)


def remove_short_noise_words(text: str, min_len: int = 2) -> str:
    """Usuwa krótkie 'śmieciowe' słowa, które nie są poprawnymi spójnikami."""
    cleaned = []
    for w in text.split():
        # Jeśli słowo jest krótkie, ale jest na liście wyjątków -> zostaw je
        if len(w) < min_len and w.lower() not in POLISH_SHORT_WORDS:
            continue
        cleaned.append(w)
    return " ".join(cleaned)


def clean_text(text: str) -> str:
    """Główna funkcja czyszcząca tekst z OCR przed dopasowaniem."""
    if not text:
        return ""
    text = normalize_unicode(text)
    text = map_similar_chars(text)
    text = remove_noise(text)
    text = re.sub(r"\s+", " ", text).strip()  # Normalizacja spacji

    # Jeśli tekst jest długi, warto wyciąć losowe 1-2 literowe śmieci
    if len(text) > 5:
        text = remove_short_noise_words(text)

    # Odrzucamy bardzo krótkie bełkoty (chyba że to 'Tak', 'Nie' itp.)
    if len(text) < 3 and not text.isalpha():
        return ""

    return text.strip().lower()


def smart_remove_name(text: str) -> str:
    """
    Próbuje usunąć imię postacie na początku linii, jeśli OCR nie wyłapał dwukropka.
    Np. 'Geralt Co tam?' -> 'Co tam?'
    """
    separators = [":", "-", "—", "–", ";"]
    for sep in separators:
        if sep in text:
            parts = text.split(sep, 1)
            # Warunek: lewa część to prawdopodobnie imię (krótka), prawa to dialog
            if len(parts) == 2 and len(parts[0]) < 40 and parts[1].strip():
                return parts[1].strip()
    return text