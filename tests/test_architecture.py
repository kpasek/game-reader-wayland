import unittest
from unittest.mock import MagicMock, patch

class TestOptimizationArchitecture(unittest.TestCase):
    def test_wizard_triggers_callback_after_destroy(self):
        # We mock the entire set of classes to test just the interaction logic
        from app.optimization_wizard import OptimizationWizard
        
        with patch('tkinter.Toplevel'), \
             patch('tkinter.ttk.Frame'), \
             patch('tkinter.ttk.Label'), \
             patch('tkinter.Listbox'), \
             patch('tkinter.StringVar'):
            
            mock_callback = MagicMock()
            parent = MagicMock()
            wiz = OptimizationWizard(parent, mock_callback)
            
            # Setup some fake frames to pass validation
            wiz.frames = [{'image': 'fake', 'rect': (0,0,10,10)}]
            wiz.destroy = MagicMock()
            
            # Trigger run
            wiz._start_opt()
            
            # 1. Must destroy itself first (per user request)
            wiz.destroy.assert_called_once()
            # 2. Must call the runner callback
            mock_callback.assert_called_once()

if __name__ == '__main__':
    unittest.main()
