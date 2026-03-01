import sys
import platform
import os
import time
import atexit
import logging
import json
from typing import Optional, Dict

import mss
import numpy as np
from PIL import Image
from pipewire_capture import (
    PortalCapture,
    CaptureStream,
    is_available as pw_is_available,
)

logger = logging.getLogger(__name__)


def _is_wayland() -> bool:
    if platform.system().lower() != 'linux':
        return False
    return 'wayland' in os.environ.get('XDG_SESSION_TYPE', '').lower()


# ---------------------------------------------------------------------------
# Backend: PipeWire (GNOME, Gamescope, inne Wayland)
# Streaming, ~0ms per frame po inicjalizacji.
# ---------------------------------------------------------------------------

class PipewireWaylandCapture:
    """
    Backend oparty o PipeWire + xdg-desktop-portal (pipewire-capture).

    Portal (okno wyboru ekranu) wyświetla się tylko raz przy starcie.
    CaptureStream działa w tle, get_frame() zwraca aktualną klatkę.
    """

    def __init__(self, capture_interval: float = 0.1) -> None:
        if not pw_is_available():
            raise RuntimeError("PipeWire capture nie jest dostępne w tym środowisku.")

        self._portal = PortalCapture()
        self._session = None
        self._stream = None

        session = self._portal.select_window()
        if session is None:
            raise RuntimeError("Wybór okna został anulowany w portalu.")

        self._session = session
        self._width = session.width
        self._height = session.height

        self._stream = CaptureStream(
            session.fd,
            session.node_id,
            session.width,
            session.height,
            capture_interval=capture_interval,
        )
        self._stream.start()

    def _get_latest_frame_array(self, timeout: float = 0.5):
        """Pobiera najnowszą klatkę jako numpy array (H, W, 3) RGB."""
        if getattr(self._stream, "window_invalid", False):
            raise RuntimeError("Okno przechwytywane przez PipeWire zostało zamknięte.")

        start = time.time()
        frame = None
        while time.time() - start < timeout and frame is None:
            frame = self._stream.get_frame()
            if frame is None:
                time.sleep(0.01)

        if frame is None:
            raise RuntimeError("Brak dostępnej ramki z PipeWire w zadanym czasie.")

        arr = np.array(frame)  # BGRA: (H, W, 4)
        if arr.ndim != 3 or arr.shape[2] < 3:
            raise RuntimeError(f"Nieoczekiwany kształt ramki: {arr.shape}")

        # BGRA -> RGB
        rgb_arr = arr[:, :, [2, 1, 0]]
        return rgb_arr

    def grab_fullscreen(self) -> Image.Image:
        arr = self._get_latest_frame_array()
        return Image.fromarray(arr, mode="RGB")

    def grab_region(self, left: int, top: int, width: int, height: int) -> Image.Image:
        arr = self._get_latest_frame_array()
        h, w = arr.shape[0], arr.shape[1]
        x1 = max(0, min(left, w))
        y1 = max(0, min(top, h))
        x2 = max(0, min(left + width, w))
        y2 = max(0, min(top + height, h))
        if x2 <= x1 or y2 <= y1:
            raise RuntimeError("Żądany region wychodzi poza obszar klatki.")
        return Image.fromarray(arr[y1:y2, x1:x2], mode="RGB")

    def stop(self) -> None:
        try:
            if self._stream:
                self._stream.stop()
        except Exception:
            pass
        try:
            if self._session:
                self._session.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Singletony
# ---------------------------------------------------------------------------

_PIPEWIRE_CAPTURE: Optional[PipewireWaylandCapture] = None


def _get_pipewire_capture() -> PipewireWaylandCapture:
    global _PIPEWIRE_CAPTURE
    if _PIPEWIRE_CAPTURE is None:
        _PIPEWIRE_CAPTURE = PipewireWaylandCapture(capture_interval=0.1)
    return _PIPEWIRE_CAPTURE


def shutdown_capture():
    """Wywołaj przy zamykaniu aplikacji."""
    global _PIPEWIRE_CAPTURE
    if _PIPEWIRE_CAPTURE:
        _PIPEWIRE_CAPTURE.stop()
        _PIPEWIRE_CAPTURE = None

atexit.register(shutdown_capture)

def reset_pipewire_source():
    """Resetuje sesję PipeWire i wymusza ponowny wybór okna za pomocą portalu."""
    global _PIPEWIRE_CAPTURE
    if _PIPEWIRE_CAPTURE is not None:
        _PIPEWIRE_CAPTURE.stop()
        _PIPEWIRE_CAPTURE = None
    
    try:
        _get_pipewire_capture()
        return True
    except Exception as e:
        logger.warning(f"Zresetowanie sesji PipeWire nie powiodło się: {e}")
        return False


def _determine_backend() -> str:
    """
    Automatycznie dobiera najlepszy backend do zrzutów ekranu.
    """
    app_config_path = os.path.expanduser('~/.config/app_config.json')
    try:
        with open(app_config_path, 'r', encoding='utf-8') as f:
            cfg = json.load(f)
            user_backend = cfg.get('capture_backend', 'Auto')
            if user_backend in ('pipewire_wayland', 'mss'):
                return user_backend
    except Exception:
        pass

    if _is_wayland() and pw_is_available():
        return 'pipewire_wayland'

    return 'mss'


SCREENSHOT_BACKEND = _determine_backend()


def capture_fullscreen() -> Optional[Image.Image]:
    """
    Pobiera zrzut całego ekranu.
    """
    try:
        if SCREENSHOT_BACKEND == 'pipewire_wayland':
            try:
                grabber = _get_pipewire_capture()
                return grabber.grab_fullscreen()
            except Exception as e:
                logger.error(f"Błąd backendu PipeWire: {e}, fallback do mss...")
                with mss.mss() as sct:
                    monitor = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
                    sct_img = sct.grab(monitor)
                    return Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")

        with mss.mss() as sct:
            monitor = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
            sct_img = sct.grab(monitor)
            return Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")

    except Exception as e:
        logger.error(f"BŁĄD (capture_fullscreen): {e}")
        return None


def capture_region(region: Dict[str, int]) -> Optional[Image.Image]:
    """
    Pobiera wycinek ekranu zdefiniowany przez słownik region.
    """
    try:
        top = int(region.get('top', 0))
        left = int(region.get('left', 0))
        width = int(region.get('width', 100))
        height = int(region.get('height', 100))

        if SCREENSHOT_BACKEND == 'pipewire_wayland':
            try:
                grabber = _get_pipewire_capture()
                return grabber.grab_region(left=left, top=top, width=width, height=height)
            except Exception as e:
                logger.error(f"Błąd backendu PipeWire (region): {e}, fallback do mss...")
                with mss.mss() as sct:
                    rect = {"top": top, "left": left, "width": width, "height": height}
                    sct_img = sct.grab(rect)
                    return Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")

        with mss.mss() as sct:
            rect = {"top": top, "left": left, "width": width, "height": height}
            sct_img = sct.grab(rect)
            return Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")

    except Exception as e:
        logger.error(f"BŁĄD (capture_region): {e}")
        return None
