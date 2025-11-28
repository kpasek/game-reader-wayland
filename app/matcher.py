from typing import List, Optional, Tuple
from thefuzz import fuzz
from app.text_processing import clean_text


def find_best_match(ocr_text: str, subtitles_list: List[str], mode: str) -> Optional[Tuple[int, int]]:
    """
    Znajduje najlepsze dopasowanie tekstu z OCR do listy napisów.
    Zwraca krotkę (index, score) lub None.

    Logika dopasowywania pozostała niezmieniona zgodnie z życzeniem.
    """
    if not ocr_text:
        return None

    ocr_text = clean_text(ocr_text)
    if not ocr_text or len(ocr_text) < 2:
        return None

    # --- TRYB 1: Częściowe dopasowanie (eksperymentalne) ---
    if mode == "Partial Lines":
        best_score = 0
        best_index = -1
        ocr_lower = ocr_text.lower()
        ocr_len = len(ocr_lower)

        for i, line in enumerate(subtitles_list):
            if not line: continue
            line_lower = line.lower()
            line_len = len(line_lower)

            prefix_score = 0
            if line_len >= ocr_len:
                fragment = line_lower[:ocr_len + 15]
                prefix_score = fuzz.ratio(ocr_lower, fragment)
            else:
                prefix_score = fuzz.ratio(ocr_lower, line_lower)

            substring_score = 0
            if ocr_len > 10 and line_len > ocr_len:
                substring_score = fuzz.partial_ratio(ocr_lower, line_lower)

            score = max(prefix_score, substring_score)

            if score > best_score:
                best_score = score
                best_index = i
                if best_score > 98: break

        threshold = 75
        if ocr_len < 6:
            threshold = 95
        elif ocr_len < 15:
            threshold = 85

        if best_index >= 0 and best_score >= threshold:
            return best_index, best_score
        return None

    # --- TRYB 2: Pełne linie (Domyślny) ---
    best_score = 0
    best_index = -1

    for i, sub_line in enumerate(subtitles_list):
        clean_sub = clean_text(sub_line)
        if not clean_sub: continue

        ocr_len = len(ocr_text)
        sub_len = len(clean_sub)

        # Heurystyka długości - jeśli różnica jest drastyczna, pomiń
        if ocr_len < sub_len * 0.5 or ocr_len > sub_len * 2.0:
            continue

        if ocr_len < 15:
            score = fuzz.ratio(clean_sub, ocr_text)
            min_score = 90
        else:
            score = fuzz.token_set_ratio(clean_sub, ocr_text)
            min_score = 75

        if score >= min_score and score > best_score:
            best_score = score
            best_index = i

    if best_index >= 0:
        return best_index, best_score

    return None