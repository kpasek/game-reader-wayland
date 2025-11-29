from typing import List, Optional, Tuple
from thefuzz import fuzz
from app.text_processing import clean_text, smart_remove_name

SubtitleEntry = Tuple[str, str, int]


def precompute_subtitles(raw_lines: List[str]) -> List[SubtitleEntry]:
    processed = []
    for i, line in enumerate(raw_lines):
        # Tutaj też używamy clean_text z inteligentnym filtrem
        cleaned = clean_text(line)
        if len(cleaned) > 0:
            processed.append((line, cleaned, i))
    return processed


def find_best_match(ocr_text: str,
                    precomputed_subs: List[SubtitleEntry],
                    mode: str,
                    last_index: int = -1) -> Optional[Tuple[int, int]]:
    if not ocr_text:
        return None

    # 1. Usuń imię
    ocr_no_name = smart_remove_name(ocr_text)

    # 2. Wyczyść tekst (inteligentne usuwanie szumu h, M, 4)
    ocr_clean = clean_text(ocr_no_name)

    if not ocr_clean:
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

    # 1. Szukanie lokalne
    match = _scan_list(ocr_clean, candidates_in_window, mode)
    if match and match[1] >= 95:
        return match

    # 2. Szukanie globalne
    global_match = _scan_list(ocr_clean, candidates_outside, mode)

    # Wybór lepszego
    if local_match := match:
        # Jeśli globalny jest ZNACZNIE lepszy, bierzemy go.
        # W przeciwnym razie ufamy lokalnemu (mniejsze ryzyko skoku w losowe miejsce).
        if global_match and global_match[1] > local_match[1] + 5:
            return global_match
        return local_match

    return global_match


def _scan_list(ocr_text: str, candidates: List[SubtitleEntry], mode: str) -> Optional[Tuple[int, int]]:
    best_score = 0
    best_original_idx = -1
    best_len_diff = float('inf')  # Do rozstrzygania remisów

    ocr_len = len(ocr_text)

    for _, sub_clean, original_idx in candidates:
        sub_len = len(sub_clean)
        score = 0

        # Obliczamy różnicę długości
        len_diff = abs(ocr_len - sub_len)

        # === TRYB PEŁNY (Full Lines) ===
        if mode == "Full Lines":
            # 1. Limit długości: max 30% różnicy
            if len_diff > max(ocr_len, sub_len) * 0.30:
                continue

            score = fuzz.ratio(sub_clean, ocr_text)

        # === TRYB CZĘŚCIOWY (Partial Lines) ===
        elif mode == "Partial Lines":
            # 1. Napis musi być dłuższy (lub równy) od OCR
            if sub_len < ocr_len - 2:  # -2 margines błędu
                continue

            score = fuzz.partial_ratio(sub_clean, ocr_text)

            # Penalizacja dopasowania krótkiego OCR do długiego napisu w środku
            # Np. OCR="Tak" vs Sub="O, tak, oczywiście". Partial da 100%.
            # Jeśli nie pasuje idealnie długością, odejmujemy punkty, chyba że to początek zdania.
            if score > 80 and len_diff > 10:
                # Sprawdzamy czy to początek (najczęstszy przypadek ucinania)
                if not sub_clean.startswith(ocr_text[:min(ocr_len, 10)]):
                    # Jeśli to środek zdania, zmniejszamy pewność
                    score -= 10

        # --- LOGIKA WYBORU NAJLEPSZEGO ---
        if score > best_score:
            best_score = score
            best_original_idx = original_idx
            best_len_diff = len_diff

            if best_score == 100 and len_diff == 0:
                break  # Ideał

        # Rozstrzyganie remisów (lub bardzo bliskich wyników)
        # Preferujemy wynik, który ma mniejszą różnicę długości (bardziej precyzyjny)
        elif score == best_score:
            if len_diff < best_len_diff:
                best_original_idx = original_idx
                best_len_diff = len_diff

    # --- PROGI AKCEPTACJI ---
    # Obniżone do 85, bo tekst jest teraz czystszy
    min_score = 85

    # Dla bardzo krótkich tekstów (< 6 znaków) nadal wymagamy wysokiej precyzji,
    # żeby nie mylić "Tak" z "Tam".
    if ocr_len < 6:
        min_score = 93

    if best_score >= min_score:
        return best_original_idx, int(best_score)

    return None