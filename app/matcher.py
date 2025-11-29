from typing import List, Optional, Tuple
from thefuzz import fuzz
from app.text_processing import clean_text

SubtitleEntry = Tuple[str, str, int]


def precompute_subtitles(raw_lines: List[str]) -> List[SubtitleEntry]:
    """
    Wykonuje clean_text na wszystkich liniach RAZ przy starcie aplikacji.
    """
    processed = []
    for i, line in enumerate(raw_lines):
        cleaned = clean_text(line)
        if cleaned and len(cleaned) >= 1:  # Akceptujemy nawet krótkie "Tak"
            processed.append((line, cleaned, i))
    return processed


def find_best_match(ocr_text: str,
                    precomputed_subs: List[SubtitleEntry],
                    mode: str,
                    last_index: int = -1) -> Optional[Tuple[int, int]]:
    """
    Znajduje najlepsze dopasowanie używając pre-obliczonych danych.
    """
    if not ocr_text:
        return None

    ocr_text = clean_text(ocr_text)
    if not ocr_text or len(ocr_text) < 2:
        return None

    WINDOW_BACK = 20
    WINDOW_FWD = 150

    candidates_in_window = []
    candidates_outside = []

    if last_index >= 0:
        for entry in precomputed_subs:
            orig_idx = entry[2]
            if last_index - WINDOW_BACK <= orig_idx <= last_index + WINDOW_FWD:
                candidates_in_window.append(entry)
            else:
                candidates_outside.append(entry)
    else:
        # Brak historii - wszystko jest kandydatem
        candidates_outside = precomputed_subs

    # 1. Przeszukanie lokalne (priorytetowe)
    local_match = _scan_list(ocr_text, candidates_in_window, mode, min_score_threshold=85)

    if local_match and local_match[1] >= 90:
        return local_match

    # 2. Przeszukanie globalne (jeśli lokalnie nie znaleziono lub wynik słaby)
    global_match = _scan_list(ocr_text, candidates_outside, mode, min_score_threshold=80)

    # Wybieramy lepszy wynik
    if local_match and global_match:
        return local_match if local_match[1] >= global_match[1] else global_match
    return local_match or global_match


def _scan_list(ocr_text: str, candidates: List[SubtitleEntry], mode: str, min_score_threshold: int) -> Optional[
    Tuple[int, int]]:
    best_score = 0
    best_original_idx = -1

    ocr_len = len(ocr_text)

    for _, clean_sub, original_idx in candidates:
        sub_len = len(clean_sub)

        if mode == "Full Lines":
            if abs(ocr_len - sub_len) > max(ocr_len, sub_len) * 0.4:
                continue
        else:
            if ocr_len > sub_len * 3.0:
                continue

        score = 0

        if mode == "Full Lines":
            score = fuzz.ratio(ocr_text, clean_sub)

        elif mode == "Partial Lines":
            # Logika dla efektu maszyny do pisania (Typewriter effect)
            if sub_len >= ocr_len:
                # Sprawdzamy, jak bardzo OCR pasuje do POCZĄTKU napisu
                prefix_sub = clean_sub[:ocr_len]
                # Dodajemy lekki margines błedu (+1 znak) dla uciętych literek
                prefix_sub_margin = clean_sub[:min(sub_len, ocr_len + 2)]

                s1 = fuzz.ratio(ocr_text, prefix_sub)
                s2 = fuzz.ratio(ocr_text, prefix_sub_margin)
                score = max(s1, s2)

            else:
                score = fuzz.partial_ratio(ocr_text, clean_sub)

        # --- AKTUALIZACJA ---
        if score > best_score:
            best_score = score
            best_original_idx = original_idx

            # Optymalizacja: 100% to 100%, nie szukaj dalej w tej grupie
            if best_score == 100:
                break

    if best_score >= min_score_threshold:
        return best_original_idx, best_score

    return None