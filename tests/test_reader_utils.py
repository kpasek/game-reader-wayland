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

def test_scale_monitor_areas_no_change(reader_thread):
    monitors = [{'left': 0, 'top': 0, 'width': 3840, 'height': 2160}]
    # Original is same as target
    # patch capture_fullscreen to avoid MagicMock unpacking error if mocked globally,
    # or to control return value.
    with patch('app.capture.capture_fullscreen', return_value=None):
        scaled = reader_thread._scale_monitor_areas(monitors)
    assert scaled[0] == monitors[0]

def test_scale_monitor_areas_scaling(reader_thread):
    # Niezależnie od rozdzielczości, funkcja nie skaluje (wejście == wyjście)
    monitors = [{'left': 100, 'top': 50, 'width': 200, 'height': 100}]
    mock_img = MagicMock()
    mock_img.size = (3840, 2160)
    with patch('app.capture.capture_fullscreen', return_value=mock_img):
        scaled = reader_thread._scale_monitor_areas(monitors)
    assert scaled == monitors

def test_scale_monitor_areas_bad_input(reader_thread):
    monitors = [{'left': 10}]
    # Bad resolution string
    with patch('app.capture.capture_fullscreen', return_value=None):
        res = reader_thread._scale_monitor_areas(monitors)
    assert res == monitors

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
