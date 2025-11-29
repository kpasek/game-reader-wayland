from typing import List, Optional, Tuple
from thefuzz import fuzz
from app.text_processing import clean_text, filter_short_words, smart_remove_name

# Typ pomocniczy: (oryginalny_tekst, wyczyszczony_tekst, oryginalny_index)
SubtitleEntry = Tuple[str, str, int]


def precompute_subtitles(raw_lines: List[str]) -> List[SubtitleEntry]:
    processed = []
    for i, line in enumerate(raw_lines):
        # W bazie napisów też możemy filtrować, ale lepiej mieć pełny kontekst,
        # więc tutaj robimy tylko clean_text.
        cleaned = clean_text(line)
        if len(cleaned) > 1:
            processed.append((line, cleaned, i))
    return processed


def find_best_match(ocr_text: str,
                    precomputed_subs: List[SubtitleEntry],
                    mode: str,
                    last_index: int = -1) -> Optional[Tuple[int, int]]:
    if not ocr_text:
        return None

    # 1. Usuń imię (np. "Geralt: ")
    ocr_no_name = smart_remove_name(ocr_text)

    # 2. Wyczyść znaki specjalne
    ocr_clean = clean_text(ocr_no_name)

    # 3. AGRESYWNE FILTROWANIE SZUMU
    # Usuwamy wszystko co ma mniej niż 3 znaki.
    # Np. "Co to?" -> "" (pusty string) -> Funkcja zwróci None
    ocr_filtered = filter_short_words(ocr_clean, min_len=3)

    # BEZPIECZNIK: Jeśli po usunięciu krótkich słów nic nie zostało,
    # albo zostało bardzo mało (np. 1-2 znaki, które jakoś przeszły), to nie szukamy.
    if not ocr_filtered or len(ocr_filtered) < 3:
        return None

    # --- OKNO WYSZUKIWANIA ---
    WINDOW_BACK = 50
    WINDOW_FWD = 200

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
        candidates_outside = precomputed_subs

    # 1. Szukamy lokalnie
    match = _scan_list(ocr_filtered, candidates_in_window, mode)
    if match and match[1] >= 95:
        return match

    # 2. Jeśli słabo, szukamy globalnie (z priorytetem dla wyniku lokalnego przy remisie)
    global_match = _scan_list(ocr_filtered, candidates_outside, mode)

    if local_match := match:
        if global_match and global_match[1] > local_match[1] + 5:
            return global_match
        return local_match

    return global_match


def _scan_list(ocr_text: str, candidates: List[SubtitleEntry], mode: str) -> Optional[Tuple[int, int]]:
    best_score = 0
    best_original_idx = -1

    ocr_len = len(ocr_text)

    for _, sub_clean, original_idx in candidates:
        # Uwaga: sub_clean w bazie ma wciąż krótkie słowa.
        # To OK, bo 'token_set_ratio' i 'partial_ratio' sobie poradzą,
        # wiedząc że w ocr_text ich brakuje.

        sub_len = len(sub_clean)
        score = 0

        # === TRYB PEŁNY (Full Lines) ===
        if mode == "Full Lines":
            # Optymalizacja: OCR (po wycięciu szumu) nie może być drastycznie dłuższy od napisu
            if ocr_len > sub_len * 1.5:
                continue

            # Jeśli różnica długości jest duża (bo usunęliśmy krótkie słowa z OCR),
            # używamy token_set_ratio, który świetnie radzi sobie z brakującymi słowami.
            # Np. Sub: "Ale o co chodzi" vs OCR: "chodzi" (bo reszta wycięta)
            score = fuzz.token_set_ratio(sub_clean, ocr_text)

        # === TRYB CZĘŚCIOWY (Partial Lines) ===
        elif mode == "Partial Lines":
            # OCR musi być krótszy od napisu (fragment)
            if sub_len < ocr_len:
                continue

            # Partial ratio sprawdza czy OCR zawiera się w napisie
            score = fuzz.partial_ratio(sub_clean, ocr_text)

            # Penalizacja krótkich dopasowań w długich zdaniach (anty-false-positive)
            if score > 80 and ocr_len < 5 and sub_len > 30:
                score -= 30

        if score > best_score:
            best_score = score
            best_original_idx = original_idx
            if best_score == 100: break

    # --- PROGI AKCEPTACJI ---
    min_score = 80

    # Skoro wycięliśmy krótkie słowa, to co zostało musi pasować bardzo dobrze.
    if ocr_len < 6:
        min_score = 92

    if best_score >= min_score:
        return best_original_idx, int(best_score)

    return None