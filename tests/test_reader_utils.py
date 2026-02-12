import pytest
from unittest.mock import MagicMock
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
    scaled = reader_thread._scale_monitor_areas(monitors, "3840x2160")
    assert scaled[0] == monitors[0]

def test_scale_monitor_areas_scaling(reader_thread):
    # Original 1920x1080 -> Target 3840x2160 (2x)
    monitors = [{'left': 100, 'top': 50, 'width': 200, 'height': 100}]
    scaled = reader_thread._scale_monitor_areas(monitors, "1920x1080")
    
    assert scaled[0]['left'] == 200
    assert scaled[0]['top'] == 100
    assert scaled[0]['width'] == 400
    assert scaled[0]['height'] == 200

def test_scale_monitor_areas_bad_input(reader_thread):
    monitors = [{'left': 10}]
    # Bad resolution string
    res = reader_thread._scale_monitor_areas(monitors, "invalid")
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
    reader_thread.trigger_area_3()
    assert reader_thread.area3_triggered is True
