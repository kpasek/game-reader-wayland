"""Utilities for scaling area rectangles between canonical 4K and physical resolutions.

Canonical base resolution: 3840x2160 (4K).
All functions accept and return lists of rect dicts: {'left','top','width','height'}.
"""
STANDARD_W = 3840
STANDARD_H = 2160

from typing import List, Dict, Tuple


def scale_rect_to_physical(rect: Dict[str, int], dest_w: int, dest_h: int) -> Dict[str, int]:
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
    return [scale_rect_to_physical(r, dest_w, dest_h) if r else r for r in rects]


def scale_list_to_4k(rects: List[Dict[str, int]], src_w: int, src_h: int) -> List[Dict[str, int]]:
    return [scale_rect_to_4k(r, src_w, src_h) if r else r for r in rects]
