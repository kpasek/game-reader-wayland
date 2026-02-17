# Stałe trybów dopasowania
MATCH_MODE_FULL = "Full Lines"
MATCH_MODE_STARTS = "Starts With"
MATCH_MODE_PARTIAL = "Partial"

import re
from typing import List, Optional, Tuple, Dict, Any
from app.text_processing import clean_text, smart_remove_name
from app.config_manager import ConfigManager


# Note: we expect `matcher_config` passed to matcher functions to be an instance
# of `ConfigManager` (or an object providing the same typed properties). This
# keeps the code typed and avoids dynamic getattr usage.

try:
    from rapidfuzz import fuzz
except ImportError:
    from thefuzz import fuzz

    print("OSTRZEŻENIE: Brak 'rapidfuzz'. Używam wolniejszego 'thefuzz'.")

# Typ pomocniczy: (oryginalna_linia, oczyszczona_linia, indeks_wiersza, dlugosc_oczyszczona)
SubtitleEntry = Tuple[str, str, int, int]


def precompute_subtitles(raw_lines: List[str], min_length: int = 0) -> Tuple[List[SubtitleEntry], Dict[str, int]]:
    """
    Przetwarza listę napisów na format gotowy do szybkiego wyszukiwania.
    """
    processed = []
    exact_map = {}

    for i, line in enumerate(raw_lines):
        cleaned = clean_text(line)
        if len(cleaned) > 0:
            meaningful_content = re.sub(r'[^\w\s]', '', cleaned)

            if len(meaningful_content) < min_length:
                continue

            length = len(cleaned)
            processed.append((line, cleaned, i, length))

            # Optymalizacja: O(1) dla idealnych trafień
            if cleaned not in exact_map:
                exact_map[cleaned] = i

    return processed, exact_map


def find_best_match(ocr_text: str,
                    precomputed_data: Tuple[List[SubtitleEntry], Dict[str, int]],
                    mode: str,
                    last_index: int = -1,
                    matcher_config: Optional[ConfigManager] = None) -> Optional[Tuple[int, int]]:
    """
    Znajduje najlepsze dopasowanie tekstu z OCR w bazie napisów, używając konfiguracji.
    """
    if not ocr_text:
        return None

    # matcher_config should be a ConfigManager-like object; if None we'll
    # construct a default ConfigManager later.

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

    # Expect a ConfigManager-like object; fall back to defaults if None
    if matcher_config is None:
        cm = ConfigManager()
        # Ensure load_preset won't attempt to stat a None path
        cm.preset_path = ""
        matcher_config = cm
    partial_min_len = matcher_config.partial_mode_min_len

    from app.matcher import MATCH_MODE_FULL
    effective_mode = MATCH_MODE_FULL if ocr_len < partial_min_len else mode

    # 1. Szukanie lokalne
    match = _scan_list(ocr_clean, ocr_len, candidates_in_window, effective_mode, matcher_config)
    if match and match[1] >= 100:
        return match

    # 2. Szukanie globalne
    global_match = _scan_list(ocr_clean, ocr_len, candidates_outside, effective_mode, matcher_config)

    # Jeśli znaleziono dopasowanie lokalne i globalne, preferuj lokalne
    if match:
        if global_match and global_match[1] > match[1] + 5:
            return global_match
        return match

    return global_match


def _scan_list(ocr_text: str, ocr_len: int, candidates: List[SubtitleEntry], mode: str, config: ConfigManager) -> \
Optional[Tuple[int, int]]:
    """Wewnętrzna funkcja iterująca po kandydatach i licząca Levenshtein ratio."""
    best_score = 0
    best_original_idx = -1
    best_len_diff = float('inf')

    # Pobieranie parametrów z konfigu
    ratio_limit = config.match_len_diff_ratio
    score_short = config.match_score_short
    score_long = config.match_score_long

    from app.matcher import MATCH_MODE_FULL, MATCH_MODE_STARTS, MATCH_MODE_PARTIAL
    for _, sub_clean, original_idx, sub_len in candidates:
        len_diff = abs(ocr_len - sub_len)

        if mode == MATCH_MODE_STARTS:
            if sub_len < ocr_len - 5:
                continue

            sub_truncated = sub_clean[:ocr_len + 5]
            score = fuzz.ratio(sub_truncated, ocr_text)

        elif mode == MATCH_MODE_PARTIAL:
            if sub_len < ocr_len - 2:  # Minimalna walidacja długości
                continue

            sub_truncated = sub_clean[:ocr_len + 5]
            score_start = fuzz.ratio(sub_truncated, ocr_text)
            score_anywhere = fuzz.partial_ratio(ocr_text, sub_clean)

            # Wybierz lepszy
            score = max(score_start, score_anywhere)
            if score > 100: score = 100
        else:
            if len_diff > max(ocr_len, sub_len) * ratio_limit:
                continue

            score = fuzz.ratio(sub_clean, ocr_text)

        if score > best_score:
            best_score = score
            best_original_idx = original_idx
            best_len_diff = len_diff
            if best_score == 100 and len_diff == 0:
                return best_original_idx, 100

        elif score == best_score:
            if len_diff < best_len_diff:
                best_original_idx = original_idx
                best_len_diff = len_diff

    len_min_threshold = 6
    len_max_threshold = 60

    if ocr_len < len_min_threshold:
        min_score = score_short
    elif ocr_len > len_max_threshold:
        min_score = score_long
    else:
        length_progress = (ocr_len - len_min_threshold) / (len_max_threshold - len_min_threshold)

        score_diff = score_long - score_short
        min_score = score_short + (length_progress * score_diff)

    if best_score >= min_score:
        return best_original_idx, int(best_score)

    return None