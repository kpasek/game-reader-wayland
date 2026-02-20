import pytest
from unittest.mock import patch, MagicMock
from PIL import Image
import pyscreenshot
from app.capture import capture_region, capture_fullscreen

def test_capture_fullscreen_fallback():
    with patch('app.capture.SCREENSHOT_BACKEND', 'pyscreenshot'),          patch('pyscreenshot.grab') as mock_grab:
        mock_img = Image.new("RGB", (100, 100))
        mock_grab.return_value = mock_img
        
        img = capture_fullscreen()
        assert img == mock_img

def test_capture_region_mocked():
    region = {'top': 100, 'left': 100, 'width': 200, 'height': 50}
    
    with patch('app.capture.SCREENSHOT_BACKEND', 'pyscreenshot'),          patch('pyscreenshot.grab') as mock_grab:
        mock_img = Image.new("RGB", (200, 50))
        mock_grab.return_value = mock_img
        
        img = capture_region(region)
        assert img == mock_img
