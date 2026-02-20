import pytest
from unittest.mock import MagicMock, patch
from PIL import Image, ImageChops
from app.reader import ReaderThread

@pytest.fixture
def reader_thread():
    cm = MagicMock()
    stop_event = MagicMock()
    audio_queue = MagicMock()
    return ReaderThread(cm, stop_event, audio_queue, target_resolution=(3840, 2160))

def test_images_are_similar(reader_thread):
    img1 = Image.new("RGB", (100, 100), "white")
    img2 = Image.new("RGB", (100, 100), "white")
    
    # Identical images
    assert reader_thread._images_are_similar(img1, img2, similarity=5.0) is True
    
    # Different images
    img3 = Image.new("RGB", (100, 100), "black")
    assert reader_thread._images_are_similar(img1, img3, similarity=5.0) is False
    
    # Slightly different
    img4 = Image.new("RGB", (100, 100), (250, 250, 250)) # close to white
    # Difference is small (5 per channel)
    # Mean difference is 5 per channel. Sum of means = 15.
    # Set similarity > 15 to pass
    assert reader_thread._images_are_similar(img1, img4, similarity=20.0) is True

def test_trigger_area_3(reader_thread):
    reader_thread.trigger_area(3)
    assert 3 in reader_thread.triggered_area_ids
