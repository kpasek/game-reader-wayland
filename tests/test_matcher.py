import pytest
from typing import Dict, Any
from app.matcher import precompute_subtitles, find_best_match, SubtitleEntry, MATCH_MODE_FULL, MATCH_MODE_STARTS, MATCH_MODE_PARTIAL
from app.config_manager import ConfigManager


class DummyConfig:
    def __init__(self, data):
        self.match_score_short = data.get("match_score_short", 90)
        self.match_score_long = data.get("match_score_long", 75)
        self.match_len_diff_ratio = data.get("match_len_diff_ratio", 0.3)
        self.partial_mode_min_len = data.get("partial_mode_min_len", 20)

    def _current_preset(self):
        return self._data

@pytest.fixture
def sample_subtitles():
    return [
        "Witaj w moim świecie.",
        "To jest testowy napis.",
        "Kolejna linia dialogowa.",
        "Bardzo długa linia, która powinna zostać dopasowana nawet przy błędach OCR.",
        "Krótka."
    ]

@pytest.fixture
def precomputed_data(sample_subtitles):
    return precompute_subtitles(sample_subtitles)

def test_precompute_subtitles(sample_subtitles):
    processed, exact_map = precompute_subtitles(sample_subtitles)
    assert len(processed) == 5
    # Check if cleaning works
    assert "witaj w moim świecie" in exact_map

def test_find_best_match_exact(precomputed_data):
    ocr_text = "Witaj w moim świecie"
    match = find_best_match(ocr_text, precomputed_data, MATCH_MODE_FULL)
    assert match is not None
    idx, score = match
    assert idx == 0
    assert score == 100

def test_find_best_match_fuzzy(precomputed_data):
    # Typos: "swiecie" instead of "świecie", "Witaj" -> "Wita"
    ocr_text = "Wita w moim swiecie" 
    match = find_best_match(ocr_text, precomputed_data, MATCH_MODE_FULL, matcher_config=DummyConfig({'match_score_long': 60, 'match_score_short': 60}))
    assert match is not None
    idx, score = match
    assert idx == 0
    assert score > 80

def test_find_best_match_partial_lines(precomputed_data):
    # OCR catches only start
    ocr_text = "Bardzo długa linia"
    # Need to lower partial_mode_min_len because len("Bardzo długa linia") is 18, default threshold is 25
    matcher_cfg = DummyConfig({'partial_mode_min_len': 10})
    match = find_best_match(ocr_text, precomputed_data, MATCH_MODE_PARTIAL, matcher_config=matcher_cfg)
    assert match is not None
    idx, score = match
    assert idx == 3 

def test_no_match(precomputed_data):
    ocr_text = "Kompletnie inny tekst z kosmosu"
    match = find_best_match(ocr_text, precomputed_data, MATCH_MODE_FULL)
    # Should probably match nothing or have very low score which filters it out usually inside wrapper (here it returns tuple if score > threshold inside function logic)
    # The function internal logic has thresholds.
    assert match is None

def test_find_best_match_with_name_removal(precomputed_data):
    ocr_text = "Geralt: To jest testowy napis."
    match = find_best_match(ocr_text, precomputed_data, MATCH_MODE_FULL)
    assert match is not None
    idx, score = match
    assert idx == 1
    assert score == 100
