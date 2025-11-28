import sys
import platform
import os
from typing import Optional, Dict

try:
    import mss
    HAS_MSS = True
except ImportError:
    HAS_MSS = False

import pyscreenshot as ImageGrab
from PIL import Image


def _determine_backend() -> str:
    """
    Automatycznie dobiera najlepszy backend do zrzutów ekranu.
    Preferuje MSS (szybkość), chyba że wykryje Wayland (kompatybilność).
    """
    if not HAS_MSS:
        return 'pyscreenshot'

    system = platform.system().lower()
    if system == 'windows':
        return 'mss'
    if system == 'linux':
        session_type = os.environ.get('XDG_SESSION_TYPE', '').lower()
        # Na Wayland MSS wymaga specjalnych uprawnień, bezpieczniej użyć fallbacku
        if 'wayland' in session_type:
            return 'pyscreenshot'
        return 'mss'
    return 'pyscreenshot'


SCREENSHOT_BACKEND = _determine_backend()


def capture_fullscreen() -> Optional[Image.Image]:
    """
    Pobiera zrzut całego ekranu (np. do wyboru obszaru).
    """
    try:
        if SCREENSHOT_BACKEND == 'mss':
            with mss.mss() as sct:
                # Monitor 1 to zazwyczaj "virtual screen" obejmujący wszystko
                monitor = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
                sct_img = sct.grab(monitor)
                return Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
        else:
            return ImageGrab.grab()
    except Exception as e:
        print(f"BŁĄD (capture_fullscreen - {SCREENSHOT_BACKEND}): {e}", file=sys.stderr)
        # Fallback
        try:
            return ImageGrab.grab()
        except Exception:
            return None


def capture_region(region: Dict[str, int]) -> Optional[Image.Image]:
    """
    Pobiera wycinek ekranu zdefiniowany przez słownik region.
    Wymagane klucze: 'top', 'left', 'width', 'height'.
    """
    try:
        top = int(region.get('top', 0))
        left = int(region.get('left', 0))
        width = int(region.get('width', 100))
        height = int(region.get('height', 100))

        if SCREENSHOT_BACKEND == 'mss':
            with mss.mss() as sct:
                # MSS przyjmuje słownik
                rect = {"top": top, "left": left, "width": width, "height": height}
                sct_img = sct.grab(rect)
                return Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
        else:
            # ImageGrab przyjmuje bbox (x1, y1, x2, y2)
            bbox = (left, top, left + width, top + height)
            return ImageGrab.grab(bbox, backend='shutil_subprocess') # Force backend safe for threads often
    except Exception as e:
        print(f"BŁĄD (capture_region - {SCREENSHOT_BACKEND}): {e}", file=sys.stderr)
        return None