import unittest
from app.scale_utils import scale_rect_to_physical, scale_rect_to_4k, scale_list_to_physical, scale_list_to_4k

class TestScalingUtils(unittest.TestCase):
    def test_scale_rect_to_physical(self):
        # 4K (3840x2160) to 1080p (1920x1080) -> factor 0.5
        rect = {'left': 100, 'top': 200, 'width': 1000, 'height': 500}
        scaled = scale_rect_to_physical(rect, 1920, 1080)
        self.assertEqual(scaled['left'], 50)
        self.assertEqual(scaled['top'], 100)
        self.assertEqual(scaled['width'], 500)
        self.assertEqual(scaled['height'], 250)

    def test_scale_rect_to_4k(self):
        # 1080p to 4K -> factor 2.0
        rect = {'left': 50, 'top': 100, 'width': 500, 'height': 250}
        scaled = scale_rect_to_4k(rect, 1920, 1080)
        self.assertEqual(scaled['left'], 100)
        self.assertEqual(scaled['top'], 200)
        self.assertEqual(scaled['width'], 1000)
        self.assertEqual(scaled['height'], 500)

    def test_rounding(self):
        # Test if rounding works correctly (not just floor)
        # 3840 / 1366 = 2.811...
        # 100 * (1366 / 3840) = 100 * 0.3557 = 35.57 -> 36
        rect = {'left': 100, 'top': 100, 'width': 100, 'height': 100}
        scaled = scale_rect_to_physical(rect, 1366, 768)
        self.assertEqual(scaled['left'], 36)

    def test_list_scaling(self):
        rects = [
            {'left': 100, 'top': 100, 'width': 100, 'height': 100},
            None,
            {'left': 200, 'top': 200, 'width': 200, 'height': 200}
        ]
        scaled = scale_list_to_physical(rects, 1920, 1080)
        self.assertEqual(len(scaled), 3)
        self.assertEqual(scaled[0]['left'], 50)
        self.assertIsNone(scaled[1])
