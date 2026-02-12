import os
import json
import pytest
from unittest.mock import patch, MagicMock
from app.config_manager import ConfigManager, DEFAULT_CONFIG, DEFAULT_PRESET_CONTENT

@pytest.fixture
def mock_config_file(tmp_path):
    config_file = tmp_path / "app_config.json"
    with open(config_file, "w") as f:
        json.dump(DEFAULT_CONFIG, f)
    return config_file

@pytest.fixture
def mock_preset_file(tmp_path):
    preset_file = tmp_path / "lektor.json"
    data = DEFAULT_PRESET_CONTENT.copy()
    data["monitor"] = [{"left": 0, "top": 0, "width": 1920, "height": 1080}]
    with open(preset_file, "w") as f:
        json.dump(data, f)
    return preset_file

@patch("app.config_manager.APP_CONFIG_FILE", new_callable=MagicMock)
def test_load_app_config(mock_config_path, mock_config_file):
    mock_config_path.__str__.return_value = str(mock_config_file)
    # Patch os.path.exists to return true for our temp file
    with patch("os.path.exists", return_value=True), \
         patch("builtins.open", side_effect=open): 
         
        # We need to ensure ConfigManager reads from the right place, 
        # but ConfigManager uses APP_CONFIG_FILE global. 
        # The easiest way is to mock open or just rely on the fact that we patched APP_CONFIG_FILE if it was used directly.
        # But looking at code: `with open(APP_CONFIG_FILE, ...)`
        # If APP_CONFIG_FILE is a Path object, open works.
        
        # Let's try simpler approach: instance creation
        cm = ConfigManager()
        # It should have loaded defaults + file content (which are defaults here)
        assert cm.settings['last_resolution_key'] == '1920x1080'

def test_config_manager_paths_utils():
    cm = ConfigManager()
    base = "/tmp/base"
    
    # Test _to_absolute
    assert cm._to_absolute(base, "file.txt") == "/tmp/base/file.txt"
    assert cm._to_absolute(base, "/abs/path/file.txt") == "/abs/path/file.txt"
    
    # Test _to_relative
    assert cm._to_relative(base, "/tmp/base/file.txt") == "file.txt"
    # Handling paths outside base depends on implementation (os.path.relpath usually handles it with ..)
    relu = cm._to_relative(base, "/tmp/other/file.txt")
    assert ".." in relu or relu.startswith("/")

def test_load_preset(mock_preset_file):
    cm = ConfigManager()
    data = cm.load_preset(str(mock_preset_file))
    
    assert data["resolution"] == "1920x1080"
    assert len(data["monitor"]) == 1
    # Check default keys injection
    assert "subtitle_mode" in data

def test_import_gr_preset(tmp_path):
    cm = ConfigManager()
    
    # Create fake windows export
    win_export = tmp_path / "export.json"
    with open(win_export, "w") as f:
        json.dump({
            "resolution": "1920x1080",
            "monitor": {"left": 0, "top": 0, "width": 1920, "height": 1080},
            "min_line_len": 5
        }, f)
        
    target_preset = tmp_path / "target_lektor.json"
    # Create existing target first
    with open(target_preset, "w") as f:
        json.dump(DEFAULT_PRESET_CONTENT, f)
        
    success = cm.import_gr_preset(str(win_export), str(target_preset))
    assert success is True
    
    # Validate scaling
    # Source: 1920 (W). Target base in code is 3840 (W). Scale = 2.0.
    # Source monitor width 1920 -> Target width 3840.
    
    with open(target_preset, "r") as f:
        new_data = json.load(f)
        
    mon = new_data["monitor"][0]
    assert mon["width"] == 3840
    assert mon["height"] == 2160
    assert new_data["min_line_length"] == 5

def test_ensure_preset_exists(tmp_path):
    cm = ConfigManager()
    path = cm.ensure_preset_exists(str(tmp_path))
    assert os.path.exists(path)
    assert path.endswith("lektor.json")
    
    with open(path, 'r') as f:
        data = json.load(f)
    assert data == DEFAULT_PRESET_CONTENT
