"""Utilities for scaling area rectangles between canonical 4K and physical resolutions.

Canonical base resolution: 3840x2160 (4K).
All functions accept and return lists of rect dicts: {'left','top','width','height'}.

IMPORTANT: These low-level scaling helpers are implementation details used by
`ConfigManager` to convert between screen (physical) coordinates and the
canonical 4K representation stored in presets. Do NOT call these functions
from other modules; always go through `ConfigManager` (e.g. use
`ConfigManager.set_areas_from_display` or `ConfigManager.get_preset_for_resolution`). Using the scaling helpers
outside `ConfigManager` risks double-scaling or inconsistent conversions.
"""
STANDARD_W = 3840
STANDARD_H = 2160

from typing import List, Dict, Tuple


def scale_rect_to_physical(rect: Dict[str, int], dest_w: int, dest_h: int) -> Dict[str, int]:
    """Scale a canonical-4K rect to physical `dest_w`x`dest_h`.

    WARNING: Intended for use only by `ConfigManager`. Do not call directly
    from UI or other modules; use `ConfigManager.get_preset_for_resolution`.
    """
    if not rect:
        return rect
    sx = dest_w / STANDARD_W
    sy = dest_h / STANDARD_H
    return {
        'left': int(round(rect.get('left', 0) * sx)),
        'top': int(round(rect.get('top', 0) * sy)),
        'width': int(round(rect.get('width', 0) * sx)),
        'height': int(round(rect.get('height', 0) * sy)),
    }


def scale_rect_to_4k(rect: Dict[str, int], src_w: int, src_h: int) -> Dict[str, int]:
    """Scale a rect given in `src_w`x`src_h` (physical) up to canonical 4K.

    WARNING: Intended for use only by `ConfigManager`. Do not call directly
    from UI or other modules; use `ConfigManager.set_areas_from_display` or
    `ConfigManager.set_monitor_from_display`.
    """
    if not rect:
        return rect
    sx = STANDARD_W / src_w if src_w else 1.0
    sy = STANDARD_H / src_h if src_h else 1.0
    return {
        'left': int(round(rect.get('left', 0) * sx)),
        'top': int(round(rect.get('top', 0) * sy)),
        'width': int(round(rect.get('width', 0) * sx)),
        'height': int(round(rect.get('height', 0) * sy)),
    }


def scale_list_to_physical(rects: List[Dict[str, int]], dest_w: int, dest_h: int) -> List[Dict[str, int]]:
    """Map `scale_rect_to_physical` over a list. See that function's warning."""
    return [scale_rect_to_physical(r, dest_w, dest_h) if r else r for r in rects]


def scale_list_to_4k(rects: List[Dict[str, int]], src_w: int, src_h: int) -> List[Dict[str, int]]:
    """Map `scale_rect_to_4k` over a list. See that function's warning."""
    return [scale_rect_to_4k(r, src_w, src_h) if r else r for r in rects]
