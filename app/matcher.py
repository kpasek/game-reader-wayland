from typing import List, Optional, Tuple, Dict

# Próba importu szybkiej biblioteki C++, fallback do Pythona
try:
    from rapidfuzz import fuzz
except ImportError:
    from thefuzz import fuzz

    print("OSTRZEŻENIE: Brak biblioteki 'rapidfuzz'. Zainstaluj ją dla lepszej wydajności!")

from app.text_processing import clean_text, smart_remove_name

# Rozszerzony typ: (oryginał, clean, index, length)
SubtitleEntry = Tuple[str, str, int, int]


def precompute_subtitles(raw_lines: List[str]) -> Tuple[List[SubtitleEntry], Dict[str, int]]:
    """
    Przygotowuje listę do wyszukiwania ORAZ mapę do błyskawicznego dopasowania (hash map).
    Zwraca: (processed_list, exact_match_map)
    """
    processed = []
    exact_map = {}

    for i, line in enumerate(raw_lines):
        cleaned = clean_text(line)
        if len(cleaned) > 0:
            length = len(cleaned)
            # Dodajemy długość do krotki, żeby nie liczyć jej w pętli
            processed.append((line, cleaned, i, length))

            # Dodajemy do mapy dokładnych dopasowań (tylko pierwsze wystąpienie)
            if cleaned not in exact_map:
                exact_map[cleaned] = i

    return processed, exact_map


def find_best_match(ocr_text: str,
                    precomputed_data: Tuple[List[SubtitleEntry], Dict[str, int]],  # Nowy format wejścia
                    mode: str,
                    last_index: int = -1) -> Optional[Tuple[int, int]]:
    if not ocr_text:
        return None

    # Rozpakowanie danych (lista i mapa)
    subtitles_list, exact_map = precomputed_data

    # 1. Przetwarzanie OCR
    ocr_no_name = smart_remove_name(ocr_text)
    ocr_clean = clean_text(ocr_no_name)

    if not ocr_clean:
        return None

    # --- OPTYMALIZACJA 1: Exact Match Lookup (O(1)) ---
    # Jeśli OCR jest idealny (po wyczyszczeniu), znajdujemy go w 0ms.
    if ocr_clean in exact_map:
        return exact_map[ocr_clean], 100

    # --- Wybór trybu ---
    effective_mode = mode
    ocr_len = len(ocr_clean)
    if ocr_len < 20:
        effective_mode = "Full Lines"

    # --- Konfiguracja Okna ---
    WINDOW_BACK = 50
    WINDOW_FWD = 200

    candidates_in_window = []
    candidates_outside = []

    # Iteracja jest szybka, bo to tylko przypisanie referencji
    if last_index >= 0:
        for entry in subtitles_list:
            orig_idx = entry[2]
            if last_index - WINDOW_BACK <= orig_idx <= last_index + WINDOW_FWD:
                candidates_in_window.append(entry)
            else:
                candidates_outside.append(entry)
    else:
        candidates_outside = subtitles_list

    # 1. Szukanie lokalne
    match = _scan_list(ocr_clean, ocr_len, candidates_in_window, effective_mode)
    if match and match[1] >= 95:
        return match

    # 2. Szukanie globalne
    global_match = _scan_list(ocr_clean, ocr_len, candidates_outside, effective_mode)

    if local_match := match:
        if global_match and global_match[1] > local_match[1] + 5:
            return global_match
        return local_match

    return global_match


def _scan_list(ocr_text: str, ocr_len: int, candidates: List[SubtitleEntry], mode: str) -> Optional[Tuple[int, int]]:
    best_score = 0
    best_original_idx = -1
    best_len_diff = float('inf')

    # Używamy cached 'sub_len' z krotki
    for _, sub_clean, original_idx, sub_len in candidates:

        len_diff = abs(ocr_len - sub_len)

        # === TRYB PEŁNY (Full Lines) ===
        if mode == "Full Lines":
            # Limit długości (30%)
            # Mnożenie jest szybsze niż dzielenie
            if len_diff > max(ocr_len, sub_len) * 0.30:
                continue

            # Rapidfuzz ratio jest znacznie szybszy
            score = fuzz.ratio(sub_clean, ocr_text)

        # === TRYB CZĘŚCIOWY (Partial Lines) ===
        elif mode == "Partial Lines":
            if sub_len < ocr_len - 3:
                continue

            score = fuzz.partial_ratio(sub_clean, ocr_text)

            if score > 80 and len_diff > 15:
                if not sub_clean.startswith(ocr_text[:min(ocr_len, 10)]):
                    score -= 10
        else:
            score = 0

        # --- Aktualizacja wyniku ---
        if score > best_score:
            best_score = score
            best_original_idx = original_idx
            best_len_diff = len_diff

            # Wczesne wyjście dla idealnych dopasowań (optymalizacja pętli)
            if best_score == 100 and len_diff == 0:
                return best_original_idx, 100

        elif score == best_score:
            if len_diff < best_len_diff:
                best_original_idx = original_idx
                best_len_diff = len_diff

    min_score = 85
    if ocr_len < 6:
        min_score = 95

    if best_score >= min_score:
        return best_original_idx, int(best_score)

    return None