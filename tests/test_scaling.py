import unittest
from unittest.mock import MagicMock
import sys

# Mock dependecies
sys.modules['pyscreenshot'] = MagicMock()
sys.modules['PIL'] = MagicMock()
sys.modules['PIL.Image'] = MagicMock()
sys.modules['PIL.ImageTk'] = MagicMock()
sys.modules['PIL.ImageOps'] = MagicMock()
sys.modules['PIL.ImageEnhance'] = MagicMock()
sys.modules['PIL.ImageFilter'] = MagicMock()
sys.modules['PIL.ImageChops'] = MagicMock()
sys.modules['PIL.ImageStat'] = MagicMock()
sys.modules['mss'] = MagicMock()
sys.modules['pytesseract'] = MagicMock() # FIX: mock pytesseract

# Since ReaderThread imports from app.capture which imports pyscreenshot and mss
# We must ensure they are mocked before import 

from app.reader import ReaderThread    

class TestScaling(unittest.TestCase):
    def setUp(self):
        # We need to mock app.capture.capture_fullscreen since it's imported inside the method
        # We'll use sys.modules to get the module and set the mock
        if 'app.capture' in sys.modules:
            self.capture_module = sys.modules['app.capture']
        else:
            # Should invoke import if not present, but it should be there due to ReaderThread import
            import app.capture
            self.capture_module = app.capture
            
        self.original_capture = getattr(self.capture_module, 'capture_fullscreen', None)

    def tearDown(self):
        if self.original_capture:
            self.capture_module.capture_fullscreen = self.original_capture

    def test_scale_monitor_areas_no_scaling(self):
        # Physical 1080p
        self.capture_module.capture_fullscreen = MagicMock(return_value=MagicMock(size=(1920, 1080)))
        
        reader = ReaderThread(MagicMock(), MagicMock(), MagicMock(), target_resolution=(1920, 1080))
        monitors = [{'left': 100, 'top': 100, 'width': 200, 'height': 200}]
        
        # Same resolution (Preset 1080p -> Physical 1080p)
        scaled = reader._scale_monitor_areas(monitors, "1920x1080")
        self.assertEqual(scaled[0]['left'], 100)
        
    def test_scale_monitor_areas_downscaling(self):
        # Scenario: User made a preset on 4K, now running on 1080p screen.
        # Physical 1080p
        self.capture_module.capture_fullscreen = MagicMock(return_value=MagicMock(size=(1920, 1080)))
        
        reader = ReaderThread(MagicMock(), MagicMock(), MagicMock(), target_resolution=(1920, 1080))
        monitors = [{'left': 200, 'top': 200, 'width': 400, 'height': 400}]
        
        scaled = reader._scale_monitor_areas(monitors, "3840x2160")
        # 4K -> 1080p is factor 0.5
        self.assertEqual(scaled[0]['left'], 100)
        self.assertEqual(scaled[0]['width'], 200)

    def test_scale_monitor_areas_upscaling(self):
        # Scenario: User made a preset on 1080p, now running on 4K screen.
        # Physical 4K
        self.capture_module.capture_fullscreen = MagicMock(return_value=MagicMock(size=(3840, 2160)))
        
        reader = ReaderThread(MagicMock(), MagicMock(), MagicMock(), target_resolution=(3840, 2160))
        monitors = [{'left': 100, 'top': 100, 'width': 200, 'height': 200}]
        
        scaled = reader._scale_monitor_areas(monitors, "1920x1080")
        # 1080p -> 4K is factor 2.0
        self.assertEqual(scaled[0]['left'], 200)
        self.assertEqual(scaled[0]['width'], 400)
        
    def test_logic_flaw_with_screen_resolution_fixed(self):
        """
        Mock capture_fullscreen to return 4K image (True physical resolution).
        Target Resolution is set to 1080p (User preference/misconfiguration).
        Preset is 4K.
        
        Expectation: Coordinates should match PHYSICAL resolution (4K), thus REMAIN 4K (no scaling).
        """
        self.capture_module.capture_fullscreen = MagicMock(return_value=MagicMock(size=(3840, 2160)))
        
        reader = ReaderThread(MagicMock(), MagicMock(), MagicMock(), target_resolution=(1920, 1080))
        
        # Area defined at 4K coords
        monitors = [{'left': 3000, 'top': 2000, 'width': 100, 'height': 100}]
        preset_res = "3840x2160"
        
        scaled = reader._scale_monitor_areas(monitors, preset_res)
        
        # Should NOT scale down to 1080p (factor 0.5) because physical is 4K.
        # It should stay 3000.
        self.assertEqual(scaled[0]['left'], 3000)
        self.assertEqual(scaled[0]['width'], 100)

    def test_capture_fails_fallback_logic(self):
        """
        Mock capture_fullscreen to FAIL (return None).
        Target Resolution is 1080p.
        Preset is 4K.
        
        Old Behavior (Bug): Fallback to Target (1080p) -> Scale 0.5 -> Shift Left/Up.
        New Behavior (Fix): Fallback to Original (4K) -> Scale 1.0 -> Correct Position.
        """
        self.capture_module.capture_fullscreen = MagicMock(return_value=None)
        
        reader = ReaderThread(MagicMock(), MagicMock(), MagicMock(), target_resolution=(1920, 1080))
        
        monitors = [{'left': 3000, 'top': 2000, 'width': 100, 'height': 100}]
        preset_res = "3840x2160"
        
        scaled = reader._scale_monitor_areas(monitors, preset_res)
        
        # Should default to NO SCALING instead of aggressive downscaling
        self.assertEqual(scaled[0]['left'], 3000)
        # Preset (3840x2160) == Physical (3840x2160).
        # So scale should be 1.0. 
        # Left should range 3000.
        
        self.assertEqual(scaled[0]['left'], 3000)
        self.assertEqual(scaled[0]['width'], 100)

    def test_logic_upscaling_with_physical_resolution(self):
        """
        Mock capture_fullscreen to return 4K image.
        Preset is 1080p.
        
        Expectation: Coordinates should UPSCALED to 4K.
        """
        sys.modules['app.capture'].capture_fullscreen = MagicMock(return_value=MagicMock(size=(3840, 2160)))
        
        reader = ReaderThread(MagicMock(), MagicMock(), MagicMock(), target_resolution=(1920, 1080)) # Target res is irrelevant
        
        monitors = [{'left': 100, 'top': 100, 'width': 100, 'height': 100}]
        preset_res = "1920x1080"
        
        scaled = reader._scale_monitor_areas(monitors, preset_res)
        
        # 1080p -> 4K (Double)
        self.assertEqual(scaled[0]['left'], 200)
        self.assertEqual(scaled[0]['width'], 200)
