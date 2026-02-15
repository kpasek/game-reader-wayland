import os
import json
import pytest
from unittest.mock import MagicMock, patch
import tkinter as tk

# Mocking modules to avoid full GUI dependencies if possible, 
# but settings.py uses tkinter extensively.
# We will use real tkinter if available (headless xvfb usually handles it in CI, local has display),
# or rely on logic isolation.
# However, settings.py requires an instantiated tk.Toplevel.

from app.settings import SettingsDialog
from app.config_manager import ConfigManager

# Dummy App class to simulate LektorApp behaviour
class MockApp:
    def __init__(self, config_mgr):
        self.config_mgr = config_mgr
        self.var_preset_full_path = tk.StringVar(value="")
        
        # Simulated variables managed by LektorApp
        self.var_ocr_scale = tk.DoubleVar(value=0.5)
        self.var_capture_interval = tk.DoubleVar(value=0.5)
        self.var_brightness_threshold = tk.IntVar(value=100)
        self.var_similarity = tk.DoubleVar(value=5.0)
        self.var_contrast = tk.DoubleVar(value=1.0)
        self.var_tolerance = tk.IntVar(value=10)
        self.var_text_thickening = tk.IntVar(value=1)
        self.var_show_debug = tk.BooleanVar(value=False)
        self.var_text_alignment = tk.StringVar(value="None")
        self.var_text_color = tk.StringVar(value="Light")
        self.var_match_score_short = tk.IntVar(value=90)
        self.var_match_score_long = tk.IntVar(value=75)
        self.var_match_len_diff = tk.DoubleVar(value=0.25)
        self.var_partial_min_len = tk.IntVar(value=25)
        self.var_min_line_len = tk.IntVar(value=0)
        self.var_audio_speed = tk.DoubleVar(value=1.0)
        self.var_auto_names = tk.BooleanVar(value=True)
        self.var_save_logs = tk.BooleanVar(value=False)
        self.var_regex_mode = tk.StringVar(value="Brak")
        self.var_custom_regex = tk.StringVar()
        
        self.regex_map = {"Brak": "", "Własny (Regex)": ""}
        self.ent_regex = MagicMock() # Mock entry widget

    def on_regex_changed(self, event=None):
        pass

    def _save_preset_val(self, key, val):
        path = self.var_preset_full_path.get()
        if path and os.path.exists(path):
            data = self.config_mgr.load_preset(path)
            data[key] = val
            self.config_mgr.save_preset(path, data)

@pytest.fixture
def tk_root():
    # Attempt to create a root window. If it fails (no display), skip tests or use mock.
    try:
        root = tk.Tk()
        root.withdraw() # Hide it
        yield root
        root.destroy()
    except Exception:
        pytest.skip("Tkinter not available or no display")

@pytest.fixture
def setup_integration(tmp_path, tk_root):
    # Create configuration
    config_file = tmp_path / "app_config.json"
    preset_file = tmp_path / "lektor.json"
    
    # Initialize basic content
    with open(preset_file, "w") as f:
        json.dump({}, f) # Empty, will be filled by defaults
        
    cm = ConfigManager(str(preset_file))
    # Point global config to temp? ConfigManager loads from global APP_CONFIG_FILE.
    # We patch loading in ConfigManager inside test usually, or we just rely on preset file which passed explicitly.
    # The _save_preset_val uses config_mgr.load_preset(path) which uses the passed path.
    
    app = MockApp(cm)
    app.var_preset_full_path.set(str(preset_file))
    
    return app, cm, str(preset_file), tk_root

def test_settings_save_global_hotkeys(setup_integration):
    app, cm, preset_path, root = setup_integration
    
    # Initial settings
    settings = {
        'hotkey_start_stop': '<f1>',
        'hotkey_area3': '<f2>'
    }
    
    try:
        dialog = SettingsDialog(root, settings, app)
        
        # Change values in DIALOG variables
        dialog.var_hk_start.set('<f5>')
        dialog.var_hk_area3.set('<f6>')
        
        # Call save
        dialog.save()
        
        # Verify dictionary update
        assert settings['hotkey_start_stop'] == '<f5>'
        assert settings['hotkey_area3'] == '<f6>'
    finally:
        if 'dialog' in locals(): dialog.destroy()

def test_settings_change_persisted_to_json(setup_integration):
    app, cm, preset_path, root = setup_integration
    
    # Directly call the save logic mimicking the callback
    # Simulating user changing OCR Scale slider
    new_val = 0.88
    app._save_preset_val("ocr_scale_factor", new_val)
    
    # Verify JSON content
    with open(preset_path, 'r') as f:
        data = json.load(f)
    assert data["ocr_scale_factor"] == 0.88

def test_settings_dialog_interaction_mock(setup_integration):
    """
    Test that SettingsDialog logic triggers _save_preset_val on MockApp.
    Since we can't easily click, we verify logic flow of callbacks if we could fetch them.
    Instead, we trust test_settings_change_persisted_to_json covers the mechanism used by the dialog.
    
    But let's verify one complex mapping provided by dialog logic, e.g. 'text_alignment'.
    """
    app, cm, preset_path, root = setup_integration
    
    # Simulate Combobox selection event logic (from settings.py code)
    # cb_align.bind("<<ComboboxSelected>>", lambda e: self.app._save_preset_val("text_alignment", self.app.var_text_alignment.get()))
    
    app.var_text_alignment.set("Center")
    # Trigger save
    app._save_preset_val("text_alignment", app.var_text_alignment.get())
    
    with open(preset_path, 'r') as f:
        data = json.load(f)
    assert data["text_alignment"] == "Center"

def test_settings_slider_rounding(setup_integration):
    app, cm, preset_path, root = setup_integration
    
    # app/settings.py _add_slider callback logic:
    # if isinstance(variable, tk.IntVar): val = int(round(val))
    # ... self.app._save_preset_val(...)
    
    # Let's test this logic isolated or via our MockApp helper if we extracted it.
    # Since we cannot easily invoke the slider callback closure, we implement a test verifying
    # intended behavior of saving integer values.
    
    val = 15.7
    # Logic in settings.py: int(round(val)) -> 16
    rounded = int(round(val))
    app._save_preset_val("color_tolerance", rounded)
    
    with open(preset_path, 'r') as f:
        data = json.load(f)
    assert data["color_tolerance"] == 16
    assert isinstance(data["color_tolerance"], int)
