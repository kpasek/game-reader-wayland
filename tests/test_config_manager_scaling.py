import json
from app.config_manager import ConfigManager


def test_get_preset_for_resolution_scales(tmp_path):
    cfg = ConfigManager()
    preset = {
        "areas": [
            {"id": 1, "type": "continuous", "rect": {"left": 384, "top": 216, "width": 1920, "height": 540}}
        ]
    }
    p = tmp_path / "test_preset.json"
    with open(p, 'w', encoding='utf-8') as f:
        json.dump(preset, f)

    scaled = cfg.get_preset_for_resolution(str(p), (1920, 1080))
    areas = scaled.get('areas', [])
    assert len(areas) == 1
    r = areas[0]['rect']
    # 4K -> 1920x1080 is half scale
    assert r['left'] == 192
    assert r['top'] == 108
    assert r['width'] == 960
    assert r['height'] == 270
