import pytest
from unittest.mock import patch, MagicMock
from app.capture import capture_region, capture_fullscreen
from PIL import Image

def test_capture_fullscreen_pyscreenshot_fallback():
    # Mocking SCREENSHOT_BACKEND execution path or forcing exception
    with patch('app.capture.SCREENSHOT_BACKEND', 'pyscreenshot'), \
         patch('app.capture.ImageGrab.grab') as mock_grab:
        
        mock_img = Image.new("RGB", (1920, 1080))
        mock_grab.return_value = mock_img
        
        img = capture_fullscreen()
        assert img is not None
        assert img.size == (1920, 1080)
        mock_grab.assert_called_once()

def test_capture_region_mocked():
    region = {'top': 100, 'left': 100, 'width': 200, 'height': 50}
    
    with patch('app.capture.ImageGrab.grab') as mock_grab:
        mock_img = Image.new("RGB", (200, 50))
        mock_grab.return_value = mock_img
        
        # Force backend to fallback to ImageGrab if needed, or default logic
        # Since we can't easily change the global variable imported in module without reload,
        # we assume logic falls through or we patch the specific backend block if possible.
        # But actually, 'app.capture.SCREENSHOT_BACKEND' is evaluated at import time.
        # So we should patch it where it is used.
        
        with patch('app.capture.SCREENSHOT_BACKEND', 'pyscreenshot'):
            img = capture_region(region)
            assert img is not None
            mock_grab.assert_called_with(bbox=(100, 100, 300, 150))
