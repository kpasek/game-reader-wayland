import pytest
from app.text_processing import clean_text, smart_remove_name

def test_clean_text_basic():
    assert clean_text("  Hello World  ") == "hello world"
    assert clean_text("Test..,,!!") == "test"

def test_clean_text_removes_tags():
    assert clean_text("Tekst [z] tagami <br>") == "tekst tagami"

def test_clean_text_removes_short_words_except_valid():
    # "a" and "i" are in VALID_SHORT_WORDS (usually)
    # "z" is in VALID_SHORT_WORDS
    # "b" is not
    # Actually, let's verify VALID_SHORT_WORDS in app/text_processing.py content previously read.
    # It contains 'a', 'i', 'o', 'u', 'w', 'z', 'az', 'aż', 'ba', 'bo', ...
    
    assert clean_text("To być albo nie być") == "to być albo nie być"  # all valid
    assert clean_text("Ala ma kota a kot ma ale") == "ala ma kota a kot ma ale"
    
    # Random short noise
    assert clean_text("x y z") == "z" # 'x','y' likely not in valid set, 'z' is.

def test_smart_remove_name():
    assert smart_remove_name("Geralt: Witaj") == "Witaj"
    assert smart_remove_name("Vesemir: Uważaj!") == "Uważaj!"
    assert smart_remove_name("Johnny >> Co tam?") == "Co tam?"
    assert smart_remove_name("System - Error") == "Error"
    assert smart_remove_name("Zwykłe zdanie bez dwukropka") == "Zwykłe zdanie bez dwukropka"
    assert smart_remove_name("") == ""
