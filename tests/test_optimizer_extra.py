import unittest
from unittest.mock import MagicMock, patch
from PIL import Image
from app.optimizer import SettingsOptimizer
from app.matcher import MATCH_MODE_PARTIAL

class TestOptimizerExtra(unittest.TestCase):
    def setUp(self):
        self.optimizer = SettingsOptimizer()
        self.image = Image.new('RGB', (100, 50), color=(0, 0, 0))
        self.dummy_db = ["test"]

    @patch('app.optimizer.SettingsOptimizer._evaluate_settings')
    def test_optimize_with_initial_color(self, mock_evaluate):
        """Sprawdza czy podany kolor początkowy jest uwzględniany w generowanych kandydatach."""
        # Setup mock to return dummy score so optimization finishes
        mock_evaluate.return_value = (0, (0,0,10,10))
        
        rough_area = (10, 10, 80, 40)
        target_color = "#123456"
        
        self.optimizer.optimize(self.image, rough_area, self.dummy_db, initial_color=target_color)
        
        # Check if any of the settings passed to _evaluate_settings had subtitle_colors == [target_color]
        found = False
        for call_args in mock_evaluate.call_args_list:
            # call_args[0] = (crop, settings, db, mode)
            settings = call_args[0][1]
            if settings.get('subtitle_colors') == [target_color]:
                found = True
                break
        
        self.assertTrue(found, f"Configuration with initial color {target_color} was not evaluated.")

    @patch('app.optimizer.SettingsOptimizer._evaluate_settings')
    def test_optimize_passes_match_mode(self, mock_evaluate):
        """Sprawdza czy tryb dopasowania (match_mode) jest przekazywany dalej."""
        mock_evaluate.return_value = (0, (0,0,10,10))
        rough_area = (10, 10, 80, 40)
        mode = MATCH_MODE_PARTIAL
        
        self.optimizer.optimize(self.image, rough_area, self.dummy_db, match_mode=mode)
        
        # Check if match_mode was passed to evaluate
        # call_args[0][3] is match_mode
        # Sprawdzamy wszystkie wywołania, czy chociaż jedno (powinny wszystkie) ma ten tryb
        # Tutaj bierzemy ostatnie
        self.assertEqual(mock_evaluate.call_args[0][3], mode)

if __name__ == '__main__':
    unittest.main()
