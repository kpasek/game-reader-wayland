from typing import List, Optional, Tuple
from thefuzz import fuzz
from app.text_processing import clean_text

# Typ pomocniczy: (oryginalny_tekst, wyczyszczony_tekst, oryginalny_index)
SubtitleEntry = Tuple[str, str, int]


def precompute_subtitles(raw_lines: List[str]) -> List[SubtitleEntry]:
    """
    Wykonuje clean_text na wszystkich liniach RAZ przy starcie aplikacji.
    Zwraca listę krotek, aby nie tracić oryginalnych indeksów po filtrowaniu.
    """
    processed = []
    for i, line in enumerate(raw_lines):
        cleaned = clean_text(line)
        # Ignorujemy puste linie, żeby nie marnować cykli CPU w pętli głównej
        if cleaned and len(cleaned) > 1:
            processed.append((line, cleaned, i))
    return processed


def find_best_match(ocr_text: str,
                    precomputed_subs: List[SubtitleEntry],
                    mode: str,
                    last_index: int = -1) -> Optional[Tuple[int, int]]:
    """
    Znajduje najlepsze dopasowanie używając pre-obliczonych danych.
    Priorytetyzuje obszar wokół last_index (optymalizacja czasowa).
    """
    if not ocr_text:
        return None

    ocr_text = clean_text(ocr_text)
    if not ocr_text or len(ocr_text) < 2:
        return None

    ocr_len = len(ocr_text)

    # --- KONFIGURACJA OKNA WYSZUKIWANIA ---
    # Jeśli mamy ostatnie trafienie, szukamy najpierw blisko niego (np. -50 do +150 linii)
    # W grach dialogi idą zazwyczaj do przodu.
    best_score = 0
    best_global_index = -1

    # Podział na listę priorytetową (okno) i resztę
    search_candidates = []

    WINDOW_BACK = 50
    WINDOW_FWD = 200

    # Szybkie wyszukiwanie lokalne (jeśli mamy historię)
    if last_index >= 0:
        # Znajdź zakres w liście precomputed (to nie są te same indeksy co w pliku, bo usunęliśmy puste!)
        # Musimy znaleźć przybliżoną pozycję w liście precomputed.
        # Dla uproszczenia w tym podejściu: iterujemy po wszystkim, ale
        # sprawdzamy warunek odległości wewnątrz pętli, co jest bardzo szybkie.
        pass

    # Zamiast dwóch pętli, zrobimy jedną z inteligentnym "early exit"
    # Jeśli znajdziemy super dopasowanie w oknie lokalnym -> przerywamy.

    candidates_in_window = []
    candidates_outside = []

    for entry in precomputed_subs:
        orig_line, clean_sub, original_idx = entry

        # Sprawdź czy jesteśmy w oknie lokalnym
        is_in_window = False
        if last_index >= 0:
            if last_index - WINDOW_BACK <= original_idx <= last_index + WINDOW_FWD:
                is_in_window = True

        if is_in_window:
            candidates_in_window.append(entry)
        else:
            candidates_outside.append(entry)

    # 1. PRZESZUKANIE LOKALNE (Najbardziej prawdopodobne)
    local_match = _scan_list(ocr_text, candidates_in_window, mode, min_score_threshold=85)

    # Jeśli znaleźliśmy bardzo dobre dopasowanie lokalnie (>90%), ufamy mu i kończymy.
    # To oszczędza przeszukiwanie reszty 60k linii.
    if local_match and local_match[1] >= 90:
        return local_match

    # 2. PRZESZUKANIE GLOBALNE (Fallback)
    # Jeśli lokalnie było słabo, musimy przeszukać resztę (np. skok w fabule, load game)
    global_match = _scan_list(ocr_text, candidates_outside, mode, min_score_threshold=80)

    # Wybieramy lepszy z obu (lokalny mógł znaleźć coś np. 60%, a globalny 95%)
    result = local_match
    if global_match:
        if not result or global_match[1] > result[1]:
            result = global_match

    return result


def _scan_list(ocr_text: str, candidates: List[SubtitleEntry], mode: str, min_score_threshold: int) -> Optional[
    Tuple[int, int]]:
    """Pomocnicza funkcja iterująca po zadanym wycinku listy."""
    best_score = 0
    best_original_idx = -1
    ocr_len = len(ocr_text)

    for _, clean_sub, original_idx in candidates:
        sub_len = len(clean_sub)

        # Heurystyka długości (bardzo szybka)
        if ocr_len < sub_len * 0.4 or ocr_len > sub_len * 2.5:
            continue

        # Wyliczenie Score
        score = 0
        if mode == "Partial Lines":
            # Logika Partial (bez zmian logicznych, tylko optymalizacja)
            if sub_len >= ocr_len:
                fragment = clean_sub[:ocr_len + 15]
                score = fuzz.ratio(ocr_text, fragment)
            else:
                score = fuzz.ratio(ocr_text, clean_sub)

            if ocr_len > 10 and sub_len > ocr_len:
                p_score = fuzz.partial_ratio(ocr_text, clean_sub)
                score = max(score, p_score)
        else:
            # Logika Full Lines
            if ocr_len < 15:
                score = fuzz.ratio(clean_sub, ocr_text)
            else:
                score = fuzz.token_set_ratio(clean_sub, ocr_text)

        if score > best_score:
            best_score = score
            best_original_idx = original_idx

            # Mikro-optymalizacja: Jeśli mamy 100%, nie znajdziemy nic lepszego w tej grupie
            if best_score == 100:
                break

    if best_score >= min_score_threshold:
        return best_original_idx, best_score
    return None