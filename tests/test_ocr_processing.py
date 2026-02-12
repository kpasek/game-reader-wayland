import pytest
from unittest.mock import MagicMock, patch
from PIL import Image, ImageDraw
from app.ocr import preprocess_image, check_alignment, remove_background, recognize_text
from app.config_manager import ConfigManager

@pytest.fixture
def config_manager_mock():
    cm = MagicMock(spec=ConfigManager)
    # Default mock preset
    cm.load_preset.return_value = {
        "text_color_mode": "Light",
        "brightness_threshold": 128,
        "text_alignment": "None",
        "ocr_scale_factor": 1.0,
        "contrast": 0,
        "subtitle_colors": [],
        "text_thickening": 0,
        "color_tolerance": 10
    }
    return cm

def create_test_image(text="TEST", size=(200, 50), bg_color="black", text_color="white", pos=(10, 10)):
    image = Image.new("RGB", size, bg_color)
    draw = ImageDraw.Draw(image)
    # Simply draw a rectangle to simulate text brightness
    l, t = pos
    draw.rectangle([l, t, l+50, t+20], fill=text_color)
    return image

def test_check_alignment():
    # bbox format: (left, top, right, bottom)
    width = 100
    
    # Center alignment
    # Center of image is 50. Zone might be e.g. 25% width -> 100*0.25 = 25px wide -> 37.5 to 62.5
    
    # Perfect center box
    bbox_center = (40, 10, 60, 30) # center is 50
    assert check_alignment(bbox_center, width, "Center", 0.25) is True

    # Far left box
    bbox_left = (0, 10, 20, 30) # center is 10
    assert check_alignment(bbox_left, width, "Center", 0.25) is False

    # Left alignment
    assert check_alignment(bbox_left, width, "Left", 0.25) is True
    assert check_alignment(bbox_center, width, "Left", 0.25) is False

def test_preprocess_image_basic(config_manager_mock):
    # White text on black background
    img = create_test_image(bg_color="black", text_color="white")
    
    processed, has_content, bbox = preprocess_image(img, config_manager_mock)
    
    assert has_content is True
    assert bbox is not None
    # Should result in inverted image (black text on white bg) for Tesseract if "Light" mode (default imports often invert things)
    # Let's check logic in source: 
    # if text_color != "Mixed": image = ImageOps.grayscale(image)
    # if text_color == "Dark": image = ImageOps.invert(image)
    # ...
    # mask = image.point(...) -> uses brightness_threshold
    # ...
    # ending: if text_color != "Mixed": image = ImageOps.invert(image)
    
    # So if input is White text (bright), Black BG.
    # Grayscale -> White on Black.
    # text_color is "Light" (default mock).
    # image NOT composed by 1st invert.
    # mask created from White on Black -> detects White.
    # End: Invert -> Black text on White BG.
    
    # Let's check center pixel. It was white (255) -> became black (0).
    # Background was black (0) -> became white (255).
    
    # We drew a rect at 10,10.
    # If crop happened, coordinates shift. 
    # crop_box is returned.
    assert bbox[0] > 0 # Left should be around 10 minus padding
    
def test_preprocess_empty_image(config_manager_mock):
    img = Image.new("RGB", (100, 100), "black")
    processed, has_content, bbox = preprocess_image(img, config_manager_mock)
    
    # If full black lines, mask is empty.
    # Logic returns: image, False, (0,0,w,h)
    assert has_content is False
    assert bbox == (0, 0, 100, 100)

def test_remove_background():
    # Image with Red text on Blue background
    img = Image.new("RGB", (100, 100), "#0000ff") # Blue bg
    draw = ImageDraw.Draw(img)
    draw.rectangle([10, 10, 50, 50], fill="#ff0000") # Red text box
    
    # We want to keep Red.
    hex_colors = ["#ff0000"]
    
    result = remove_background(img, hex_colors, tolerance=10)
    
    # Result should be white text on black background (mask format inside remove_background, then convert to RGB)
    # Wait, remove_background returns RGB: "Białe napisy na czarnym tle" according to docstring.
    
    # Check text area (approx 30,30) - should be white
    r, g, b = result.getpixel((30, 30))
    assert r > 200 and g > 200 and b > 200
    
    # Check bg area (approx 90,90) - should be black
    r, g, b = result.getpixel((90, 90))
    assert r < 50 and g < 50 and b < 50

@patch('app.ocr.pytesseract.image_to_string')
@patch('app.ocr.HAS_CONFIG_FILE', True)
@patch('app.ocr.CONFIG_FILE_PATH', 'dummy_path')
def test_recognize_text(mock_tess, config_manager_mock):
    mock_tess.return_value = "  Test Output  "
    img = Image.new("L", (100, 50), 255)
    
    res = recognize_text(img, config_manager_mock)
    assert res == "Test Output"
    mock_tess.assert_called()

