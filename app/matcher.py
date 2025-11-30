from typing import List, Optional, Tuple, Dict
from app.text_processing import clean_text, smart_remove_name

try:
    from rapidfuzz import fuzz
except ImportError:
    from thefuzz import fuzz

    print("OSTRZEŻENIE: Brak 'rapidfuzz'. Używam wolniejszego 'thefuzz'.")

# Typ pomocniczy: (oryginalna_linia, oczyszczona_linia, indeks_wiersza, dlugosc_oczyszczona)
SubtitleEntry = Tuple[str, str, int, int]


def precompute_subtitles(raw_lines: List[str]) -> Tuple[List[SubtitleEntry], Dict[str, int]]:
    """
    Przetwarza listę napisów na format gotowy do szybkiego wyszukiwania.
    Tworzy również mapę skrótów (hash map) dla idealnych dopasowań.

    :param raw_lines: Lista surowych linii z pliku tekstowego.
    :return: Krotka (lista_przetworzona, mapa_idealnych_dopasowan).
    """
    processed = []
    exact_map = {}

    for i, line in enumerate(raw_lines):
        cleaned = clean_text(line)
        if len(cleaned) > 0:
            length = len(cleaned)
            processed.append((line, cleaned, i, length))

            # Optymalizacja: O(1) dla idealnych trafień
            if cleaned not in exact_map:
                exact_map[cleaned] = i

    return processed, exact_map


def find_best_match(ocr_text: str,
                    precomputed_data: Tuple[List[SubtitleEntry], Dict[str, int]],
                    mode: str,
                    last_index: int = -1) -> Optional[Tuple[int, int]]:
    """
    Znajduje najlepsze dopasowanie tekstu z OCR w bazie napisów.

    Strategia:
    1. Sprawdzenie idealnego dopasowania (słownik).
    2. Wyszukiwanie lokalne (w pobliżu ostatnio znalezionej linii).
    3. Wyszukiwanie globalne (cały plik) - jeśli lokalne zawiodło.

    :param ocr_text: Tekst rozpoznany przez OCR.
    :param precomputed_data: Dane zwrócone przez precompute_subtitles.
    :param mode: Tryb dopasowania ('Full Lines' lub 'Partial Lines').
    :param last_index: Indeks ostatnio znalezionej linii (dla kontekstu).
    :return: Krotka (indeks_linii, pewność_dopasowania_%) lub None.
    """
    if not ocr_text:
        return None

    subtitles_list, exact_map = precomputed_data

    # Wstępne czyszczenie OCR
    ocr_no_name = smart_remove_name(ocr_text)
    ocr_clean = clean_text(ocr_no_name)

    if not ocr_clean:
        return None

    # Szybka ścieżka: Exact Match
    if ocr_clean in exact_map:
        return exact_map[ocr_clean], 100

    # Ustalanie okna wyszukiwania
    WINDOW_BACK = 50
    WINDOW_FWD = 200
    candidates_in_window = []
    candidates_outside = []

    if last_index >= 0:
        for entry in subtitles_list:
            orig_idx = entry[2]
            if last_index - WINDOW_BACK <= orig_idx <= last_index + WINDOW_FWD:
                candidates_in_window.append(entry)
            else:
                candidates_outside.append(entry)
    else:
        candidates_outside = subtitles_list

    ocr_len = len(ocr_clean)

    # Wymuś 'Full Lines' dla bardzo krótkich tekstów, aby uniknąć fałszywych dopasowań
    effective_mode = "Full Lines" if ocr_len < 20 else mode

    # 1. Szukanie lokalne
    match = _scan_list(ocr_clean, ocr_len, candidates_in_window, effective_mode)
    if match and match[1] >= 95:
        return match

    # 2. Szukanie globalne
    global_match = _scan_list(ocr_clean, ocr_len, candidates_outside, effective_mode)

    # Jeśli znaleziono dopasowanie lokalne i globalne, preferuj lokalne, chyba że globalne jest znacznie pewniejsze
    if match:
        if global_match and global_match[1] > match[1] + 5:
            return global_match
        return match

    return global_match


def _scan_list(ocr_text: str, ocr_len: int, candidates: List[SubtitleEntry], mode: str) -> Optional[Tuple[int, int]]:
    """Wewnętrzna funkcja iterująca po kandydatach i licząca Levenshtein ratio."""
    best_score = 0
    best_original_idx = -1
    best_len_diff = float('inf')

    for _, sub_clean, original_idx, sub_len in candidates:
        len_diff = abs(ocr_len - sub_len)

        if mode == "Full Lines":
            # Jeśli różnica długości jest duża (>30%), pomijamy (optymalizacja)
            if len_diff > max(ocr_len, sub_len) * 0.30:
                continue
            score = fuzz.ratio(sub_clean, ocr_text)

        elif mode == "Partial Lines":
            if sub_len < ocr_len - 3:
                continue
            score = fuzz.partial_ratio(sub_clean, ocr_text)
            # Kara za brak zgodności początku przy dużej różnicy długości
            if score > 80 and len_diff > 15:
                if not sub_clean.startswith(ocr_text[:min(ocr_len, 10)]):
                    score -= 10
        else:
            score = 0

        if score > best_score:
            best_score = score
            best_original_idx = original_idx
            best_len_diff = len_diff
            if best_score == 100 and len_diff == 0:
                return best_original_idx, 100

        elif score == best_score:
            # Przy równym wyniku wybierz ten o zbliżonej długości
            if len_diff < best_len_diff:
                best_original_idx = original_idx
                best_len_diff = len_diff

    # Progi akceptacji
    min_score = 95 if ocr_len < 6 else 85

    if best_score >= min_score:
        return best_original_idx, int(best_score)

    return None