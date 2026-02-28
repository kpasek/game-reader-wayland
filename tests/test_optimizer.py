import unittest
from unittest.mock import MagicMock, patch
from PIL import Image
from app.optimizer import SettingsOptimizer, OptimizerConfigManager

class TestSettingsOptimizer(unittest.TestCase):

    def setUp(self):
        self.optimizer = SettingsOptimizer()
        self.dummy_db = [
            "Hello World",
            "This is a test subtitle",
            "Another line of text",
            "Geralt: What are you doing?"
        ]
        # Create a dummy image
        self.image = Image.new('RGB', (100, 50), color=(0, 0, 0))

    def test_optimizer_config_manager(self):
        """Test czy mock config managera zwraca to co mu podamy."""
        from app.config_manager import PresetConfig
        preset = PresetConfig(audio_speed=9.99)
        mgr = OptimizerConfigManager(preset)
        self.assertEqual(mgr.load_preset().audio_speed, 9.99)

    @patch('app.optimizer.preprocess_image')
    @patch('app.optimizer.recognize_text')
    def test_optimize_flow(self, mock_recognize, mock_preprocess):
        """Testuje główny przepływ funkcji optimize bez odpalania prawdziwego Tesseracta."""
        
        # Setup mocków
        # 1. Preprocess zawsze zwraca sukces
        # bbox = (0, 0, 50, 20)
        mock_preprocess.return_value = (self.image, True, (0, 0, 50, 20))
        
        # 2. Recognize zwraca tekst, który jest w bazie
        mock_recognize.return_value = "This is a test subtitle"
        
        rough_area = (10, 10, 80, 40)
        
        result = self.optimizer.optimize(self.image, rough_area, self.dummy_db)
        
        # Oczekujemy, że znajdzie 100% dopasowania
        self.assertGreaterEqual(result['score'], 90)
        self.assertIn('settings', result)
        self.assertIn('optimized_area', result)
        
        # Sprawdź czy algorytm przeliczył obszar (powinien być mniejszy niż rough_area)
        opt_area = result['optimized_area']
        self.assertEqual(opt_area, (10, 10, 60, 22))
    @patch('app.optimizer.preprocess_image')
    @patch('app.optimizer.recognize_text')
    def test_optimize_no_match(self, mock_recognize, mock_preprocess):
        """Testuje sytuację gdy OCR zwraca śmieci."""
        
        mock_preprocess.return_value = (self.image, True, (0,0,100,50))
        mock_recognize.return_value = "&*^%$#@" # Śmieci
        
        rough_area = (0, 0, 100, 50)
        
        result = self.optimizer.optimize(self.image, rough_area, self.dummy_db)
        
        # Wynik powinien być słaby
        self.assertLess(result['score'], 50)

    def test_invalid_area(self):
        """Testuje zabezpieczenie przed błędnym obszarem."""
        bad_area = (0, 0, 0, 0)
        result = self.optimizer.optimize([self.image], bad_area, self.dummy_db)
        self.assertIn("error", result)

if __name__ == '__main__':
    unittest.main()
