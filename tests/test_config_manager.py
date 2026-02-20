import os
import json
import pytest
from unittest.mock import patch, MagicMock
from app.config_manager import ConfigManager, DEFAULT_CONFIG, DEFAULT_PRESET_CONTENT, PresetConfig, AreaConfig

@pytest.fixture
def mock_config_file(tmp_path):
    config_file = tmp_path / 'app_config.json'
    with open(config_file, 'w') as f:
        json.dump(DEFAULT_CONFIG, f)
    return config_file

@pytest.fixture
def mock_preset_file(tmp_path):
    preset_file = tmp_path / 'lektor.json'
    data = DEFAULT_PRESET_CONTENT.copy()
    data['areas'] = [{'id': 1, 'type': 'continuous', 'rect': {'left': 0, 'top': 0, 'width': 100, 'height': 100}}]
    with open(preset_file, 'w') as f:
        json.dump(data, f)
    return preset_file

@patch('app.config_manager.APP_CONFIG_FILE', new_callable=MagicMock)
def test_load_app_config(mock_config_path, mock_config_file):
    mock_config_path.__str__.return_value = str(mock_config_file)
    with patch('os.path.exists', return_value=True),          patch('builtins.open', side_effect=open): 
        cm = ConfigManager()
        assert cm.settings['last_resolution_key'] == '1920x1080'

def test_load_preset(mock_preset_file):
    cm = ConfigManager()
    preset = cm.load_preset(str(mock_preset_file))
    
    assert isinstance(preset, PresetConfig)
    assert len(preset.areas) == 1
    assert preset.areas[0].id == 1
    assert preset.subtitle_mode == 'Full Lines'

def test_config_manager_properties(mock_preset_file):
    cm = ConfigManager(str(mock_preset_file))
    # Test property access
    assert cm.subtitle_mode == 'Full Lines'
    cm.subtitle_mode = 'Partial'
    assert cm.subtitle_mode == 'Partial'
    
    # Reload and check
    cm2 = ConfigManager(str(mock_preset_file))
    assert cm2.subtitle_mode == 'Partial'

def test_ensure_preset_exists(tmp_path):
    cm = ConfigManager()
    path = cm.ensure_preset_exists(str(tmp_path))
    assert os.path.exists(path)
    assert path.endswith('lektor.json')
