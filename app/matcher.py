from typing import List, Optional, Tuple
from thefuzz import fuzz
from app.text_processing import clean_text, filter_short_words  # ZMIANA: Dodany import filter_short_words

# Typ pomocniczy: (oryginalny_tekst, wyczyszczony_tekst, oryginalny_index)
SubtitleEntry = Tuple[str, str, int]


def precompute_subtitles(raw_lines: List[str]) -> List[SubtitleEntry]:
    """
    Wykonuje clean_text na wszystkich liniach RAZ przy starcie aplikacji.
    """
    processed = []
    for i, line in enumerate(raw_lines):
        cleaned = clean_text(line)
        if cleaned:
            processed.append((line, cleaned, i))
    return processed


def find_best_match(ocr_text: str,
                    precomputed_subs: List[SubtitleEntry],
                    mode: str,
                    last_index: int = -1) -> Optional[Tuple[int, int]]:
    """
    Znajduje najlepsze dopasowanie używając starej logiki punktacji,
    ale zoptymalizowanego przeszukiwania (okno czasowe).
    """
    if not ocr_text:
        return None

    ocr_text = clean_text(ocr_text)

    # ZMIANA: Filtr szumu - usuwamy krótkie słowa (do 3 znaków) z odczytanego tekstu
    ocr_text = filter_short_words(ocr_text, min_len=4)

    if not ocr_text or len(ocr_text) < 2:
        return None

    # --- KONFIGURACJA OKNA WYSZUKIWANIA ---
    WINDOW_BACK = 20
    WINDOW_FWD = 150

    candidates_in_window = []
    candidates_outside = []

    # Dzielimy kandydatów na priorytetowych (blisko ostatniego dialogu) i resztę
    if last_index >= 0:
        for entry in precomputed_subs:
            orig_idx = entry[2]
            if last_index - WINDOW_BACK <= orig_idx <= last_index + WINDOW_FWD:
                candidates_in_window.append(entry)
            else:
                candidates_outside.append(entry)
    else:
        candidates_outside = precomputed_subs

    # 1. Przeszukanie lokalne (priorytetowe)
    local_match = _scan_list(ocr_text, candidates_in_window, mode)

    # Jeśli lokalnie znaleźliśmy bardzo dobre dopasowanie, kończymy (optymalizacja)
    if local_match and local_match[1] >= 98:
        return local_match

    # 2. Przeszukanie globalne (jeśli lokalnie nie znaleziono lub wynik nie jest idealny)
    global_match = _scan_list(ocr_text, candidates_outside, mode)

    # Wybieramy lepszy wynik
    if local_match and global_match:
        return local_match if local_match[1] >= global_match[1] else global_match

    return local_match or global_match


def _scan_list(ocr_text: str, candidates: List[SubtitleEntry], mode: str) -> Optional[Tuple[int, int]]:
    """
    Iteruje po liście kandydatów i aplikuje logikę punktacji (przywróconą ze starej wersji).
    Wprowadzono filtr długości dla optymalizacji i precyzji oraz mechanizm rozstrzygania remisów.
    """
    best_score = 0
    best_original_idx = -1
    best_len_diff = float('inf')  # Używane do rozstrzygania remisów

    ocr_lower = ocr_text.lower()
    ocr_len = len(ocr_lower)

    for _, clean_sub, original_idx in candidates:
        line_len = len(clean_sub)
        score = 0

        if mode == "Full Lines":
            if not (abs(ocr_len - line_len) <= max(ocr_len, line_len) * 0.30 or abs(ocr_len - line_len) <= 15):
                continue

        elif mode == "Partial Lines":
            # Przy częściowym dopasowaniu, OCR nie może być dłuższy niż napis + mały margines błędu.
            # Jeśli OCR jest dłuższy niż 10% i 5 znaków, odrzucamy (prawdopodobnie szum lub błąd OCR).
            if ocr_len > line_len + 5 and ocr_len > line_len * 1.1:
                continue

        if mode == "Partial Lines":
            if line_len >= ocr_len:
                fragment = clean_sub[:ocr_len + 15]
                prefix_score = fuzz.ratio(ocr_lower, fragment)
            else:
                prefix_score = fuzz.ratio(ocr_lower, clean_sub)

            # 2. Substring score (partial_ratio) dla dłuższych tekstów
            substring_score = 0
            # Poprawione: Sprawdzamy, czy OCR jest > 10, ponieważ partial_ratio jest zbyt luźne dla krótkich tekstów
            if ocr_len > 10 and line_len > ocr_len:
                substring_score = fuzz.partial_ratio(ocr_lower, clean_sub)

            score = max(prefix_score, substring_score)

        else:  # "Full Lines"
            if ocr_len < 15:
                score = fuzz.ratio(clean_sub, ocr_lower)
            else:
                score = fuzz.token_set_ratio(clean_sub, ocr_lower)

        # Zapisywanie najlepszego wyniku i rozstrzyganie remisu
        current_len_diff = abs(line_len - ocr_len)

        if score > best_score:
            best_score = score
            best_original_idx = original_idx
            best_len_diff = current_len_diff

            # Szybkie wyjście przy idealnym dopasowaniu
            if best_score > 98:
                break

        # ZMIANA: Rozstrzyganie remisu na podstawie różnicy długości
        elif score == best_score and score > 0:
            if current_len_diff < best_len_diff:
                best_original_idx = original_idx
                best_len_diff = current_len_diff

    # --- PROGI PUNKTOWE (THRESHOLDS) ---
    if best_original_idx != -1:
        if mode == "Partial Lines":
            threshold = 75
            if ocr_len < 6:
                threshold = 95
            elif ocr_len < 15:
                threshold = 85

            if best_score >= threshold:
                return best_original_idx, best_score

        else:  # Full Lines
            min_score = 75
            if ocr_len < 15:
                min_score = 90

            if best_score >= min_score:
                return best_original_idx, best_score

    return None