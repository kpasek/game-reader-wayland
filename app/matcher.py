from typing import List, Optional, Tuple
from thefuzz import fuzz
from app.text_processing import clean_text, smart_remove_name

# Typ pomocniczy: (oryginalny_tekst, wyczyszczony_tekst, oryginalny_index)
SubtitleEntry = Tuple[str, str, int]


def precompute_subtitles(raw_lines: List[str]) -> List[SubtitleEntry]:
    """
    Przygotowuje listę napisów do szybkiego wyszukiwania.
    """
    processed = []
    for i, line in enumerate(raw_lines):
        cleaned = clean_text(line)
        # Ignorujemy puste linie w bazie
        if len(cleaned) > 0:
            processed.append((line, cleaned, i))
    return processed


def find_best_match(ocr_text: str,
                    precomputed_subs: List[SubtitleEntry],
                    mode: str,
                    last_index: int = -1) -> Optional[Tuple[int, int]]:
    if not ocr_text:
        return None

    # 1. Wstępne czyszczenie: usuwamy imię postaci (jeśli jest)
    ocr_no_name = smart_remove_name(ocr_text)

    # 2. Normalizacja tekstu
    ocr_clean = clean_text(ocr_no_name)

    if not ocr_clean:
        return None

    # ====================================================================
    # ZMIANA LOGIKI: Automatyczny wybór trybu na podstawie długości
    # ====================================================================
    # Domyślnie używamy trybu z ustawień, ALE:
    # Jeśli tekst jest krótki (< 20 znaków), ZAWSZE wymuszamy 'Full Lines'.
    # Krótkie teksty (np. "Tak", "Uważaj") nie są dzielone, więc muszą pasować idealnie.
    # To eliminuje dopasowywanie szumu (np. "4", "|") do krótkich słów.

    effective_mode = mode
    ocr_len = len(ocr_clean)

    if ocr_len < 20:
        effective_mode = "Full Lines"

    # ====================================================================

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

    # 1. Szukanie lokalne (priorytetowe)
    match = _scan_list(ocr_clean, candidates_in_window, effective_mode)
    if match and match[1] >= 95:
        return match

    # 2. Szukanie globalne
    global_match = _scan_list(ocr_clean, candidates_outside, effective_mode)

    # Wybór lepszego wyniku
    if local_match := match:
        # Jeśli globalny jest wyraźnie lepszy, bierzemy go
        if global_match and global_match[1] > local_match[1] + 5:
            return global_match
        return local_match

    return global_match


def _scan_list(ocr_text: str, candidates: List[SubtitleEntry], mode: str) -> Optional[Tuple[int, int]]:
    best_score = 0
    best_original_idx = -1
    best_len_diff = float('inf')

    ocr_len = len(ocr_text)

    for _, sub_clean, original_idx in candidates:
        sub_len = len(sub_clean)
        score = 0

        len_diff = abs(ocr_len - sub_len)

        # === TRYB PEŁNY (Full Lines) ===
        # Używany dla ustawienia 'Full Lines' ORAZ dla wszystkich tekstów < 20 znaków
        if mode == "Full Lines":
            # 1. Limit długości: Teksty muszą być zbliżone.
            # Pozwalamy na max 30% różnicy (błędy OCR, spacje).
            if len_diff > max(ocr_len, sub_len) * 0.30:
                continue

            # 2. Strict Ratio: Całość do całości.
            # "f f f" vs "Ale" -> Ratio ~0.
            score = fuzz.ratio(sub_clean, ocr_text)

        # === TRYB CZĘŚCIOWY (Partial Lines) ===
        # Używany tylko dla tekstów >= 20 znaków (jeśli włączony w opcjach)
        elif mode == "Partial Lines":
            # 1. Napis w bazie musi być dłuższy (lub równy) OCR
            # (bo OCR to tylko wycinek)
            if sub_len < ocr_len - 3:
                continue

            score = fuzz.partial_ratio(sub_clean, ocr_text)

            # Penalizacja dopasowań środkowych, jeśli nie pasują kontekstowo
            if score > 80 and len_diff > 15:
                # Jeśli to nie jest początek zdania, obniżamy lekko wynik,
                # żeby preferować pełniejsze dopasowania.
                if not sub_clean.startswith(ocr_text[:min(ocr_len, 10)]):
                    score -= 10

        # --- Wybór najlepszego ---
        if score > best_score:
            best_score = score
            best_original_idx = original_idx
            best_len_diff = len_diff

            if best_score == 100 and len_diff == 0:
                break

                # Rozstrzyganie remisów: preferujemy dopasowanie o bliższej długości
        elif score == best_score:
            if len_diff < best_len_diff:
                best_original_idx = original_idx
                best_len_diff = len_diff

    # --- PROGI AKCEPTACJI ---
    min_score = 85

    # Dla bardzo krótkich tekstów (< 6 znaków) wymagamy niemal idealnego dopasowania
    # (nawet w trybie Full Lines, żeby odróżnić "Tak" od "Tam")
    if ocr_len < 6:
        min_score = 95

    if best_score >= min_score:
        return best_original_idx, int(best_score)

    return None