import unittest
from app.geometry_utils import calculate_merged_area

class TestAreaCalculation(unittest.TestCase):
    def test_single_rect_with_margin(self):
        # Image 1000x1000
        # Rect: x=100, y=100, w=100, h=100
        # Margin 5% of 100 = 5.
        # Expected: x=95, y=95, w=110, h=110
        rects = [(100, 100, 100, 100)]
        result = calculate_merged_area(rects, 1000, 1000, 0.05)
        self.assertEqual(result, (95, 95, 110, 110))

    def test_two_rects_separate(self):
        # Rect1: (10, 10, 10, 10) -> (10,10,20,20)
        # Rect2: (80, 80, 10, 10) -> (90,90) - Wait, rect is x,y,w,h. r[2] is w.
        # Union Bounds:
        # min_x = 10, max_x = 80+10 = 90. u_w = 80.
        # min_y = 10, max_y = 80+10 = 90. u_h = 80.
        # Margin = 5% of 80 = 4.
        # Final Rect:
        # x1 = 10 - 4 = 6
        # y1 = 10 - 4 = 6
        # x2 = 90 + 4 = 94
        # y2 = 90 + 4 = 94
        # w = 94 - 6 = 88
        # h = 94 - 6 = 88
        rects = [(10, 10, 10, 10), (80, 80, 10, 10)]
        result = calculate_merged_area(rects, 1000, 1000, 0.05)
        self.assertEqual(result, (6, 6, 88, 88))

    def test_clamping_top_left(self):
        # Rect at extreme top-left: (0, 0, 100, 100)
        # Margin = 5% of 100 = 5.
        # x1 = 0 - 5 = -5 -> clamped to 0.
        # y1 = 0 - 5 = -5 -> clamped to 0.
        # x2 = 100 + 5 = 105.
        # y2 = 100 + 5 = 105.
        # w = 105 - 0 = 105.
        # h = 105 - 0 = 105.
        rects = [(0, 0, 100, 100)]
        result = calculate_merged_area(rects, 1000, 1000, 0.05)
        self.assertEqual(result, (0, 0, 105, 105))

    def test_clamping_bottom_right(self):
        # Image 100x100
        # Rect at (50, 50, 50, 50).
        # Margin = 5% of 50 = 2.5 -> 2.
        # x1 = 50 - 2 = 48.
        # y1 = 50 - 2 = 48.
        # x2 = 100 + 2 = 102 -> clamped to 100.
        # y2 = 100 + 2 = 102 -> clamped to 100.
        # w = 100 - 48 = 52.
        # h = 100 - 48 = 52.
        rects = [(50, 50, 50, 50)]
        result = calculate_merged_area(rects, 100, 100, 0.05)
        self.assertEqual(result, (48, 48, 52, 52))
        
    def test_empty_rects(self):
        rects = []
        result = calculate_merged_area(rects, 100, 100)
        self.assertEqual(result, (0, 0, 0, 0))

if __name__ == '__main__':
    unittest.main()
