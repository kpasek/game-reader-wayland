import sys
import os
import unittest
from typing import List, Tuple

# Add the project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.optimizer import SettingsOptimizer

class TestAreaRefinementUnion(unittest.TestCase):
    def setUp(self):
        self.optimizer = SettingsOptimizer()
        self.screen_size = (3840, 2160)
        self.rough_area = (1000, 1500, 1000, 500) # x, y, w, h

    def test_single_bbox(self):
        # relative to rough_area: (left, top, right, bottom)
        bboxes = [(100, 100, 200, 150)] # w=100, h=50
        # abs_l = 1000 + 100 = 1100
        # abs_t = 1500 + 100 = 1600
        # agg_w = 100, agg_h = 50
        # margin_h = 10, margin_v = 2.5
        # final_x = 1100 - 10 = 1090
        # final_y = 1600 - 2 = 1598
        # final_w = 100 + 20 = 120
        # final_h = 50 + 5 = 55
        
        result = self.optimizer._apply_area_refinement(self.screen_size, self.rough_area, bboxes)
        self.assertEqual(result, (1090, 1597, 120, 55)) # int(1597.5) -> 1597 or 1598 depending on rounding/truncation

    def test_multiple_bboxes_union(self):
        # b1: (100, 100, 200, 200) -> union_l=100, union_t=100, union_r=300, union_b=300
        # b2: (150, 150, 300, 250) -> union_l=100, union_t=100, union_r=300, union_b=300
        # wait, max_r = max(200, 300) = 300, max_b = max(200, 250) = 250
        # so union: (100, 100, 300, 250) -> agg_w=200, agg_h=150
        bboxes = [(100, 100, 200, 200), (150, 150, 300, 250)]
        # abs_l = 1100, abs_t = 1600
        # margin_h = 20, margin_v = 7.5
        # final_x = 1100 - 20 = 1080
        # final_y = 1600 - 7 = 1593
        # final_w = 200 + 40 = 240
        # final_h = 150 + 15 = 165
        
        result = self.optimizer._apply_area_refinement(self.screen_size, self.rough_area, bboxes)
        self.assertEqual(result, (1080, 1592, 240, 165)) # 1600 - 7.5 = 1592.5 -> 1592

    def test_no_bboxes(self):
        result = self.optimizer._apply_area_refinement(self.screen_size, self.rough_area, [])
        self.assertEqual(result, self.rough_area)

    def test_constraints_screen_boundary(self):
        # Rough area at top-left
        rough = (10, 10, 100, 100)
        # Bbox covers most of it
        bboxes = [(0, 0, 100, 100)] 
        # abs_l = 10, abs_t = 10, agg_w=100, agg_h=100
        # margin_h = 10, margin_v = 5
        # final_x = 10 - 10 = 0
        # final_y = 10 - 5 = 5
        # final_w = 100 + 20 = 120
        # final_h = 100 + 10 = 110
        # BUT: constrained to rough_area (10, 10, 100, 100)
        # So final_x = max(10, 0) = 10
        # final_y = max(10, 5) = 10
        # final_w = min(120, (10+100)-10) = 100
        result = self.optimizer._apply_area_refinement(self.screen_size, rough, bboxes)
        self.assertEqual(result, (10, 10, 100, 100))

    def test_partial_detections(self):
        # Some frames have no text
        bboxes = [(100, 100, 200, 200), None, (120, 120, 220, 220)]
        # union: (100, 100, 220, 220) -> agg_w=120, agg_h=120
        # abs_l = 1100, abs_t = 1600
        # margin_h = 12, margin_v = 6
        # final_x = 1100 - 12 = 1088
        # final_y = 1600 - 6 = 1594
        # final_w = 120 + 24 = 144
        # final_h = 120 + 12 = 132
        result = self.optimizer._apply_area_refinement(self.screen_size, self.rough_area, bboxes)
        self.assertEqual(result, (1088, 1594, 144, 132))

if __name__ == '__main__':
    unittest.main()
