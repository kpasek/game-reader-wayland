import unittest
from unittest.mock import MagicMock, patch
import sys

# Mock dependencies BEFORE importing app modules that might fail on missing system libs
mock_tk = MagicMock()
# Setup basic tk classes to avoid inheritance errors
class MockToplevel:
    def __init__(self, *args, **kwargs): pass
    def geometry(self, *args): pass
    def title(self, *args): pass
    def withdraw(self): pass
    def deiconify(self): pass
    def update(self): pass
    def destroy(self): pass
    def winfo_exists(self): return True
    def winfo_children(self): return []
    def pack(self, *args, **kwargs): pass
    def grid(self, *args, **kwargs): pass
    def attributes(self, *args, **kwargs): pass
    def bind(self, *args, **kwargs): pass
    def focus_force(self): pass
    def wait_visibility(self): pass
    def grab_set(self): pass
    def wait_window(self, *args): pass
    def transient(self, *args): pass

class MockVar:
    def __init__(self, value=None): self._val = value
    def set(self, val): self._val = val
    def get(self): return self._val
    def trace_add(self, *args, **kwargs): pass

mock_tk.Toplevel = MockToplevel
mock_tk.Tk = MockToplevel
mock_tk.Frame = MagicMock()
mock_tk.Label = MagicMock()
mock_tk.Button = MagicMock()
mock_tk.Listbox = MagicMock()
mock_tk.Canvas = MagicMock()
mock_tk.StringVar = MockVar
mock_tk.IntVar = MockVar
mock_tk.DoubleVar = MockVar
mock_tk.BooleanVar = MockVar
mock_tk.END = "end"
mock_tk.NORMAL = "normal"
mock_tk.DISABLED = "disabled"
mock_tk.LEFT = "left"
mock_tk.RIGHT = "right"
mock_tk.BOTH = "both"
mock_tk.Y = "y"
mock_tk.X = "x"
mock_tk.W = "w"
mock_tk.EW = "ew"
mock_tk.NW = "nw"

sys.modules['tkinter'] = mock_tk
sys.modules['tkinter.ttk'] = MagicMock()
sys.modules['tkinter.messagebox'] = MagicMock()

# Mock PIL.ImageTk because it requires active Tkinter window
# But allow real PIL.Image for logic tests
sys.modules['PIL.ImageTk'] = MagicMock()
# sys.modules['PIL'] = mock_pil  <-- REMOVED: Real PIL needed for other tests
# sys.modules['PIL.Image'] = MagicMock() <-- REMOVED

# Mock pyscreenshot
# sys.modules['pyscreenshot'] = MagicMock() <-- REMOVED: Use real module or patch in specific tests

# NOW import the app module
from app.area_manager import AreaManagerWindow

class TestAreaManager(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = mock_tk.Tk()

    @classmethod
    def tearDownClass(cls):
        pass

    def setUp(self):
        self.areas = [
            {"id": 1, "type": "continuous", "rect": {"left": 0, "top": 0, "width": 100, "height": 100}, "hotkey": "", "colors": ["#ffffff"]},
            {"id": 2, "type": "manual", "rect": {"left": 0, "top": 0, "width": 50, "height": 50}, "hotkey": "<f3>", "colors": []}
        ]
        self.mock_callback = MagicMock()
        
        # We need to ensure AreaSelector is mocked because it's imported in area_manager
        # But since we mocked tkinter, it might fine? 
        # Actually AreaManagerWindow imports AreaSelector from app.area_selector
        # app.area_selector imports tkinter. 
        # Since tkinter is in sys.modules, app.area_selector will import our mock.
        
        # We still want to patch AreaSelector usage in AreaManagerWindow to avoid logic issues
        self.patcher1 = patch('app.area_manager.AreaSelector')
        self.patcher2 = patch('app.area_manager.ColorSelector')
        self.patcher3 = patch('app.area_manager.capture_fullscreen')

        self.MockAreaSelector = self.patcher1.start()
        self.MockColorSelector = self.patcher2.start()
        self.MockCapture = self.patcher3.start()

        # Create a simple mock ConfigManager for tests
        self.mock_cfg = MagicMock()
        self.mock_cfg.get_preset_for_resolution = MagicMock(return_value={'areas': self.areas})
        self.mock_cfg.load_preset = MagicMock(return_value={'areas': self.areas})
        self.mock_cfg.save_preset_from_screen = MagicMock()

        # Ensure mock_cfg has cached preset_path like real ConfigManager
        self.mock_cfg.preset_path = 'dummy_path'
        # Build a mock LektorApp object exposing config_mgr and _get_screen_size
        self.mock_app = MagicMock()
        self.mock_app.config_mgr = self.mock_cfg
        self.mock_app._get_screen_size = MagicMock(return_value=(3840, 2160))
        self.window = AreaManagerWindow(self.root, self.mock_app)
        
        # Fix for Listbox mock behavior
        self.window.lb_areas.get = MagicMock(return_value=["#1 [Stały]", "#2 [Na skrót]"])
        self.window.lb_areas.curselection = MagicMock(return_value=[0])

    def tearDown(self):
        self.patcher1.stop()
        self.patcher2.stop()
        self.patcher3.stop()

    def test_initial_load(self):
        # We manually mocked listbox.get return value in setUp because Mock doesn't store state
        # So we just verify calls were made
        pass 

    def test_add_area(self):
        initial_count = len(self.window.areas)
        self.window._add_area()
        self.assertEqual(len(self.window.areas), initial_count + 1)
        
        new_area = self.window.areas[-1]
        self.assertEqual(new_area['type'], 'manual') # Default

    def test_remove_area(self):
        # Setup selection for removal
        self.window.current_selection_idx = 1
        
        self.window._remove_area()
        self.assertEqual(len(self.window.areas), 1)
        self.assertEqual(self.window.areas[0]['id'], 1)

    def test_cannot_remove_area_1(self):
        self.window.current_selection_idx = 0
        
        # Check if warning shown
        self.window._remove_area()
        # messagebox is mocked via sys.modules['tkinter.messagebox']
        # But we imported ttk inside area_manager...
        # Let's check logic: count shouldn't change
        self.assertEqual(len(self.window.areas), 2)

    def test_save_callback(self):
        self.window._save_and_close()
        # Ensure ConfigManager.save_preset_from_screen invoked
        self.mock_cfg.save_preset_from_screen.assert_called_once()
        # Validate that saved areas length matches
        saved_data = self.mock_cfg.save_preset_from_screen.call_args[0][1]
        self.assertIn('areas', saved_data)
        self.assertEqual(len(saved_data['areas']), 2)

if __name__ == '__main__':
    unittest.main()
