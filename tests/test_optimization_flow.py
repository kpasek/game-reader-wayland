import unittest
from unittest.mock import MagicMock, patch, sys

# Mock tkinter and PIL before they are imported by the app
mock_tk = MagicMock()
sys.modules['tkinter'] = mock_tk
sys.modules['tkinter.ttk'] = MagicMock()
sys.modules['tkinter.messagebox'] = MagicMock()
sys.modules['tkinter.colorchooser'] = MagicMock()
sys.modules['PIL'] = MagicMock()
sys.modules['PIL.Image'] = MagicMock()
sys.modules['PIL.ImageTk'] = MagicMock()

# Now imports can proceed safely in headless environments
from app.area_manager import AreaManagerWindow
from app.optimization_wizard import OptimizationWizard
from app.processing_window import ProcessingWindow
from app.optimization_result import OptimizationResultWindow

class TestOptimizationFlow(unittest.TestCase):
    def setUp(self):
        self.root = MagicMock()
        self.areas = [{
            "id": 1,
            "type": "continuous",
            "rect": {"left": 0, "top": 0, "width": 100, "height": 100},
            "settings": {}
        }]
        self.subtitle_lines = ["Hello world"]

    def tearDown(self):
        pass

    def test_wizard_start_closes_wizard(self):
        # Test if OptimizationWizard.run calls callback and destroys itself
        mock_callback = MagicMock()
        wiz = OptimizationWizard(self.root, mock_callback)
        wiz.frames = [{'image': MagicMock(), 'rect': (0,0,10,10)}]
        
        # Mock destroy to verify it's called
        wiz.destroy = MagicMock()
        
        wiz._start_opt()
        
        wiz.destroy.assert_called_once()
        mock_callback.assert_called_once()


if __name__ == '__main__':
    unittest.main()
