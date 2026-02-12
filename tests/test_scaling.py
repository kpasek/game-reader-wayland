import unittest
from unittest.mock import MagicMock, patch
import sys

# We should rely on installed dependencies for imports to ensure other tests aren't affected by global mocks.
# Specific dependencies will be mocked in setUp or tests.

from app.reader import ReaderThread

class TestScaling(unittest.TestCase):
    def setUp(self):
        # Mock capture module methods that are used
        self.patcher = patch('app.capture.capture_fullscreen')
        self.mock_capture = self.patcher.start()
        
        # Configure default behavior properly (1080p)
        self.mock_capture.return_value = MagicMock()
        self.mock_capture.return_value.size = (1920, 1080)

    def tearDown(self):
        self.patcher.stop()

    def set_res(self, w, h):
        if w is None:
            self.mock_capture.return_value = None
        else:
            self.mock_capture.return_value = MagicMock()
            self.mock_capture.return_value.size = (w, h)

    def test_scale_monitor_areas_no_scaling(self):
        # Physical 1080p
        self.set_res(1920, 1080)
        
        reader = ReaderThread(MagicMock(), MagicMock(), MagicMock(), target_resolution=(1920, 1080))
        monitors = [{'left': 100, 'top': 100, 'width': 200, 'height': 200}]
        
        # Same resolution (Preset 1080p -> Physical 1080p)
        scaled = reader._scale_monitor_areas(monitors, "1920x1080")
        self.assertEqual(scaled[0]['left'], 100)
        self.assertEqual(scaled[0]['width'], 200)
        
    def test_scale_monitor_areas_downscaling(self):
        # Scenario: User made a preset on 4K, now running on 1080p screen.
        # Physical 1080p
        self.set_res(1920, 1080)
        
        reader = ReaderThread(MagicMock(), MagicMock(), MagicMock(), target_resolution=(1920, 1080))
        monitors = [{'left': 200, 'top': 200, 'width': 400, 'height': 400}]
        
        scaled = reader._scale_monitor_areas(monitors, "3840x2160")
        # 4K -> 1080p is factor 0.5
        self.assertEqual(scaled[0]['left'], 100)
        self.assertEqual(scaled[0]['width'], 200)

    def test_scale_monitor_areas_upscaling(self):
        # Scenario: User made a preset on 1080p, now running on 4K screen.
        # Physical 4K
        self.set_res(3840, 2160)
        
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
        """
        self.set_res(3840, 2160)
        
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
        Old Behavior (Bug): Fallback to Target (1080p) -> Scale 0.5 -> Shift Left/Up.
        New Behavior (Fix): Fallback to Original (4K) -> Scale 1.0 -> Correct Position.
        """
        self.set_res(None, None)
        
        reader = ReaderThread(MagicMock(), MagicMock(), MagicMock(), target_resolution=(1920, 1080))
        
        monitors = [{'left': 3000, 'top': 2000, 'width': 100, 'height': 100}]
        preset_res = "3840x2160"
        
        scaled = reader._scale_monitor_areas(monitors, preset_res)
        
        # Should default to NO SCALING
        self.assertEqual(scaled[0]['left'], 3000)

    def test_hidpi_logical_vs_physical_mismatch(self):
        """
        Scenario: 
        - 4K Physical Screen (Preset created here: 3840x2160)
        - System uses 150% scaling, so Logical Resolution is 2560x1440.
        """
        # Detected resolution is Smaller (Logical)
        self.set_res(2560, 1440)
        
        reader = ReaderThread(MagicMock(), MagicMock(), MagicMock(), target_resolution=(2560, 1440))
        
        # Area defined at 4K coords
        monitors = [{'left': 3000, 'top': 2000, 'width': 100, 'height': 100}]
        preset_res = "3840x2160" # LARGER than detected
        
        scaled = reader._scale_monitor_areas(monitors, preset_res)
        
        # Should NOT scale down to 2560/3840 = 0.66.
        # Should return unscaled (3000) because we trust Preset on HiDPI mismatch.
        self.assertEqual(scaled[0]['left'], 3000)
        self.assertEqual(scaled[0]['width'], 100)

    def test_logic_upscaling_with_physical_resolution(self):
        # Redundant but kept for structure
        self.set_res(3840, 2160)
        reader = ReaderThread(MagicMock(), MagicMock(), MagicMock(), target_resolution=(1920, 1080)) 
        monitors = [{'left': 100, 'top': 100, 'width': 100, 'height': 100}]
        scaled = reader._scale_monitor_areas(monitors, "1920x1080")
        self.assertEqual(scaled[0]['left'], 200)
