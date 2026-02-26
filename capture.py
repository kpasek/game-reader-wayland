import sys
import platform
import os
import uuid
import shutil
import subprocess
import threading
import logging
import time
import atexit
from typing import Optional, Dict, Tuple

from PIL import Image

logger = logging.getLogger(__name__)

# Opcjonalny backend MSS
try:
    import mss
    HAS_MSS = True
except ImportError:
    HAS_MSS = False

# Fallback do pyscreenshot
import pyscreenshot as ImageGrab

# Opcjonalny backend PipeWire dla Waylanda
try:
    from pipewire_capture import (
        PortalCapture,
        CaptureStream,
        is_available as pw_is_available,
    )  # type: ignore
    HAS_PIPEWIRE_CAPTURE = True
except ImportError:
    HAS_PIPEWIRE_CAPTURE = False

    def pw_is_available() -> bool:  # type: ignore[no-redef]
        return False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_linux() -> bool:
    return platform.system().lower() == "linux"


def _is_wayland() -> bool:
    return _is_linux() and "wayland" in os.environ.get("XDG_SESSION_TYPE", "").lower()


def _is_kde_wayland() -> bool:
    return _is_wayland() and "kde" in os.environ.get("XDG_CURRENT_DESKTOP", "").lower()


def _find_executable(name: str) -> Optional[str]:
    return shutil.which(name)


def _get_screen_resolution() -> Optional[Tuple[int, int]]:
    """Wykrywa rozdzielczość aktywnego ekranu."""
    try:
        out = subprocess.check_output(
            ['kscreen-doctor', '-o'], stderr=subprocess.DEVNULL, timeout=3
        ).decode()
        import re
        m = re.search(r'(\d+)x(\d+)@[\d.]+\*', out)
        if m:
            return int(m.group(1)), int(m.group(2))
    except Exception:
        pass
    try:
        out = subprocess.check_output(
            ['xrandr', '--current'], stderr=subprocess.DEVNULL, timeout=3
        ).decode()
        import re
        m = re.search(r'current (\d+) x (\d+)', out)
        if m:
            return int(m.group(1)), int(m.group(2))
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Backend 1: GSR per-subprocess (KDE Wayland)
# Zero mikroprzycięć, ~700-900ms per capture.
# ---------------------------------------------------------------------------

class GpuScreenRecorderCapture:
    """
    Capture przez gpu-screen-recorder jako subprocess per-klatka.
    Używa trybu -c png -f 1 (single shot, bezpośredni PNG, bez ffmpeg).
    Przeznaczony dla KDE Wayland gdzie PipeWire portal wymaga autoryzacji okna.
    """

    def __init__(self):
        self._gsr = _find_executable('gpu-screen-recorder')
        self._resolution: Optional[Tuple[int, int]] = None
        self._ready = False

    def start(self, timeout: float = 5.0) -> bool:
        if not self._gsr:
            logger.error("gpu-screen-recorder nie znaleziony w PATH")
            return False

        self._resolution = _get_screen_resolution()
        if not self._resolution:
            logger.error("Nie udało się wykryć rozdzielczości ekranu")
            return False

        try:
            w, h = self._resolution
            test_path = f"/dev/shm/lektor_gsr_test_{os.getpid()}.png"
            subprocess.run(
                [self._gsr,
                 '-w', 'screen',
                 '-c', 'png',
                 '-f', '1',
                 '-s', f'{w}x{h}',
                 '-v', 'no',
                 '-o', test_path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
                check=True
            )
            if os.path.exists(test_path):
                os.remove(test_path)
            self._ready = True
            logger.info(f"GSR per-subprocess gotowy: {w}x{h}")
            return True
        except Exception as e:
            logger.error(f"GSR test błąd: {e}")
            return False
        finally:
            _kill_gsr_kms_server()

    def capture(self) -> Optional[Image.Image]:
        """Robi jeden screenshot przez GSR -c png -f 1."""
        if not self._ready or not self._resolution:
            return None

        w, h = self._resolution
        png_path = f"/dev/shm/lektor_gsr_{os.getpid()}_{threading.get_ident()}.png"

        try:
            subprocess.run(
                [self._gsr,
                 '-w', 'screen',
                 '-c', 'png',
                 '-f', '1',
                 '-s', f'{w}x{h}',
                 '-v', 'no',
                 '-o', png_path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
                check=True
            )

            if not os.path.exists(png_path):
                return None

            img = Image.open(png_path)
            img.load()
            return img.convert('RGB')

        except Exception as e:
            logger.error(f"GSR capture błąd: {e}")
            return None
        finally:
            try:
                if os.path.exists(png_path):
                    os.remove(png_path)
            except OSError:
                pass
            _kill_gsr_kms_server()

    def is_healthy(self) -> bool:
        return self._ready

    def stop(self):
        pass


def _kill_gsr_kms_server():
    """Zabija gsr-kms-server który zostaje po subprocess GSR."""
    try:
        subprocess.run(
            ['pkill', '-f', 'gsr-kms-server'],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Backend 2: PipeWire (GNOME, Gamescope, inne Wayland)
# Streaming, ~0ms per frame po inicjalizacji.
# ---------------------------------------------------------------------------

class PipewireWaylandCapture:
    """
    Backend oparty o PipeWire + xdg-desktop-portal (pipewire-capture 0.2.9+).

    Portal (okno wyboru ekranu) wyświetla się tylko raz przy starcie.
    CaptureStream działa w tle, get_frame() zwraca aktualną klatkę.
    """

    def __init__(self, capture_interval: float = 0.1) -> None:
        if not HAS_PIPEWIRE_CAPTURE or not pw_is_available():
            raise RuntimeError("PipeWire capture nie jest dostępne w tym środowisku.")

        self._portal = PortalCapture()
        self._session = None
        self._stream = None

        # select_window() jest synchroniczne w 0.2.9 — zwraca PortalSession lub None
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
        import numpy as np

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

        arr = __import__('numpy').array(frame)  # BGRA: (H, W, 4)
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
# Backend 3: Spectacle subprocess (KDE Wayland fallback)
# ---------------------------------------------------------------------------

class KWinSpectacleWrapper:
    """
    Wrapper na narzędzie Spectacle. Fallback gdy GSR jest niedostępny.
    """

    def grab(self, x=None, y=None, width=None, height=None) -> Image.Image:
        temp_path = f"/dev/shm/kwin_shot_{uuid.uuid4()}.png"

        try:
            cmd = ["spectacle", "-b", "-n", "-m", "-o", temp_path]
            subprocess.run(
                cmd, check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=10
            )

            if not os.path.exists(temp_path):
                raise RuntimeError("Spectacle nie utworzył pliku w /dev/shm")

            img = Image.open(temp_path)
            img.load()

            if x is not None and width is not None:
                img = img.crop((int(x), int(y), int(x + width), int(y + height)))

            return img

        except subprocess.TimeoutExpired:
            raise RuntimeError("Spectacle przekroczył limit czasu.")
        except subprocess.CalledProcessError:
            raise RuntimeError("Błąd wywołania narzędzia Spectacle.")
        finally:
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass


# ---------------------------------------------------------------------------
# Singletony
# ---------------------------------------------------------------------------

_gsr_instance: Optional[GpuScreenRecorderCapture] = None
_gsr_lock = threading.Lock()
_gsr_available: Optional[bool] = None

_PIPEWIRE_CAPTURE: Optional[PipewireWaylandCapture] = None


def _get_or_init_gsr() -> Optional[GpuScreenRecorderCapture]:
    global _gsr_instance, _gsr_available

    if _gsr_available is False:
        return None

    with _gsr_lock:
        if _gsr_instance is not None and _gsr_instance.is_healthy():
            return _gsr_instance

        cap = GpuScreenRecorderCapture()
        if cap.start():
            _gsr_instance = cap
            _gsr_available = True
            return _gsr_instance
        else:
            _gsr_available = False
            logger.warning("GSR niedostępny — fallback na Spectacle")
            return None


def _get_pipewire_capture() -> PipewireWaylandCapture:
    global _PIPEWIRE_CAPTURE
    if _PIPEWIRE_CAPTURE is None:
        _PIPEWIRE_CAPTURE = PipewireWaylandCapture(capture_interval=0.1)
    return _PIPEWIRE_CAPTURE


def shutdown_capture():
    """Wywołaj przy zamykaniu aplikacji."""
    global _gsr_instance, _PIPEWIRE_CAPTURE
    if _gsr_instance:
        _gsr_instance.stop()
        _gsr_instance = None
    if _PIPEWIRE_CAPTURE:
        _PIPEWIRE_CAPTURE.stop()
        _PIPEWIRE_CAPTURE = None
    _kill_gsr_kms_server()


atexit.register(shutdown_capture)


# ---------------------------------------------------------------------------
# Backend selection
# ---------------------------------------------------------------------------

def _determine_backend() -> str:
    """
    Priorytety:
    - KDE Wayland + gpu-screen-recorder  -> 'kde_gsr'
    - Wayland + pipewire-capture         -> 'pipewire_wayland'
    - KDE Wayland (fallback)             -> 'kde_spectacle'
    - Windows/X11 + mss                  -> 'mss'
    - fallback                           -> 'pyscreenshot'
    """
    if _is_kde_wayland():
        if HAS_PIPEWIRE_CAPTURE and pw_is_available():
            return 'pipewire_wayland'
        if _find_executable('gpu-screen-recorder'):
            return 'kde_gsr'
        return 'kde_spectacle'

    if _is_wayland() and HAS_PIPEWIRE_CAPTURE and pw_is_available():
        return 'pipewire_wayland'

    if not HAS_MSS:
        return 'pyscreenshot'

    system = platform.system().lower()
    if system == 'windows':
        return 'mss'
    if system == 'linux':
        if _is_wayland():
            return 'pyscreenshot'
        return 'mss'
    return 'pyscreenshot'


SCREENSHOT_BACKEND = _determine_backend()


# ---------------------------------------------------------------------------
# Publiczne API
# ---------------------------------------------------------------------------

def _kde_capture(left=None, top=None, width=None, height=None) -> Optional[Image.Image]:
    """Capture przez GSR (primary) lub Spectacle (fallback) dla KDE Wayland."""
    cap = _get_or_init_gsr()

    if cap is not None:
        img = cap.capture()
        if img is not None:
            if left is not None:
                return img.crop((left, top, left + width, top + height))
            return img
        logger.debug("GSR: brak klatki, fallback na Spectacle")

    try:
        grabber = KWinSpectacleWrapper()
        return grabber.grab(x=left, y=top, width=width, height=height)
    except Exception as e:
        print(f"Błąd backendu Spectacle: {e}", file=sys.stderr)
        return None


def capture_fullscreen() -> Optional[Image.Image]:
    """Pobiera zrzut całego ekranu."""
    try:
        if SCREENSHOT_BACKEND in ('kde_gsr', 'kde_spectacle'):
            return _kde_capture()

        if SCREENSHOT_BACKEND == 'pipewire_wayland':
            grabber = _get_pipewire_capture()
            return grabber.grab_fullscreen()

        if SCREENSHOT_BACKEND == 'mss':
            with mss.mss() as sct:
                monitor = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
                sct_img = sct.grab(monitor)
                return Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")

        return ImageGrab.grab()

    except Exception as e:
        print(f"BŁĄD (capture_fullscreen): {e}", file=sys.stderr)
        return None


def capture_region(region: Dict[str, int]) -> Optional[Image.Image]:
    """Pobiera wycinek ekranu zdefiniowany przez słownik region."""
    try:
        top    = int(region.get('top', 0))
        left   = int(region.get('left', 0))
        width  = int(region.get('width', 100))
        height = int(region.get('height', 100))

        if SCREENSHOT_BACKEND in ('kde_gsr', 'kde_spectacle'):
            return _kde_capture(left=left, top=top, width=width, height=height)

        if SCREENSHOT_BACKEND == 'pipewire_wayland':
            grabber = _get_pipewire_capture()
            return grabber.grab_region(left=left, top=top, width=width, height=height)

        if SCREENSHOT_BACKEND == 'mss':
            with mss.mss() as sct:
                rect = {"top": top, "left": left, "width": width, "height": height}
                sct_img = sct.grab(rect)
                return Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")

        return ImageGrab.grab(bbox=(left, top, left + width, top + height))

    except Exception as e:
        print(f"BŁĄD (capture_region): {e}", file=sys.stderr)
        return None
