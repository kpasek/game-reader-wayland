import unittest
from unittest.mock import MagicMock, patch
from PIL import Image
from app.optimizer import SettingsOptimizer
from app.matcher import MATCH_MODE_PARTIAL, MATCH_MODE_FULL

class TestOptimizerExtra(unittest.TestCase):
    def setUp(self):
        self.optimizer = SettingsOptimizer()
        self.image = Image.new('RGB', (100, 50), color=(0, 0, 0))
        self.dummy_db = ["test"]

    @patch('multiprocessing.Pool')
    def test_optimize_with_initial_color(self, mock_pool_cls):
        """Sprawdza czy podany kolor początkowy jest uwzględniany w generowanych kandydatach."""
        # Setup mock pool
        mock_pool = mock_pool_cls.return_value.__enter__.return_value
        # Stage 1 imap
        mock_pool.imap.return_value = iter([(100, (0,0,10,10))])
        # Stage 1 starmap (for _init_worker)
        mock_pool.starmap.return_value = None
        # Stage 2 map (if it runs, but here we have only 1 image)
        mock_pool.map.return_value = []
        
        rough_area = (10, 10, 80, 40)
        target_color = "#123456"
        
        # We also need to mock _evaluate_settings because it's called at the end
        with patch('app.optimizer.SettingsOptimizer._evaluate_settings') as mock_eval:
            mock_eval.return_value = (100, (0,0,10,10))
            self.optimizer.optimize([self.image], rough_area, self.dummy_db, initial_color=target_color)
            
            # Verify if target_color was among candidates passed to imap
            args, kwargs = mock_pool.imap.call_args
            # args[1] is the iterable: [(s, match_mode) for s in candidates]
            found = False
            for s, mode in args[1]:
                if getattr(s, 'colors', []) == [target_color]:
                    found = True
                    break
            self.assertTrue(found, f"Configuration with initial color {target_color} was not evaluated.")

    @patch('multiprocessing.Pool')
    def test_optimize_passes_match_mode(self, mock_pool_cls):
        """Sprawdza czy tryb dopasowania (match_mode) jest przekazywany dalej."""
        # Setup mock pool
        mock_pool = mock_pool_cls.return_value.__enter__.return_value
        mock_pool.imap.return_value = iter([(100, (0,0,10,10))])
        
        rough_area = (10, 10, 80, 40)
        mode = MATCH_MODE_PARTIAL
        
        with patch('app.optimizer.SettingsOptimizer._evaluate_settings') as mock_eval:
            mock_eval.return_value = (100, (0,0,10,10))
            self.optimizer.optimize([self.image], rough_area, self.dummy_db, match_mode=mode)
            
            # Check if match_mode was passed to imap
            args, kwargs = mock_pool.imap.call_args
            for s, m in args[1]:
                self.assertEqual(m, mode)

if __name__ == '__main__':
    unittest.main()
