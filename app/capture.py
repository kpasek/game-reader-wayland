import sys
import platform
import os
import uuid
import subprocess
from typing import Optional, Dict

try:
    import mss

    HAS_MSS = True
except ImportError:
    HAS_MSS = False

import pyscreenshot as ImageGrab
from PIL import Image


def _is_kde_wayland() -> bool:
    """Sprawdza czy działamy w sesji KDE Plasma na Waylandzie."""
    if platform.system().lower() != 'linux':
        return False
    session_type = os.environ.get('XDG_SESSION_TYPE', '').lower()
    desktop = os.environ.get('XDG_CURRENT_DESKTOP', '').lower()
    return 'wayland' in session_type and 'kde' in desktop


class KWinSpectacleWrapper:
    """
    Wrapper na narzędzie Spectacle, który wymusza zapis do RAM (/dev/shm).
    Jest to najszybsza metoda na KDE Wayland jeśli bezpośredni DBus/Grim nie działa.
    """

    def grab(self, x=None, y=None, width=None, height=None) -> Image.Image:
        temp_path = f"/dev/shm/kwin_shot_{uuid.uuid4()}.png"

        try:
            cmd = ["spectacle", "-b", "-n", "-f", "-o", temp_path]

            subprocess.run(
                cmd,
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=10
            )

            if not os.path.exists(temp_path):
                raise RuntimeError("Spectacle nie utworzył pliku w /dev/shm")

            img = Image.open(temp_path)
            img.load()
            
            # DEBUG: Save full raw capture from Spectacle
            # if not os.path.exists("debug_spectacle_full_integrity.png"):
            #      try:
            #          img.save("debug_spectacle_full_integrity.png")
            #          print(f"DEBUG: Saved debug_spectacle_full_integrity.png (Size: {img.size})")
            #      except: pass

            if x is not None and width is not None:
                box = (int(x), int(y), int(x + width), int(y + height))
                img = img.crop(box)
                
                # DEBUG: Save immediate crop result
                     # if not os.path.exists("debug_spectacle_crop_immediate.png"):
                     #      try:
                     #          img.save("debug_spectacle_crop_immediate.png")
                     #          print("DEBUG: Saved debug_spectacle_crop_immediate.png")
                     #      except: pass

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



def _determine_backend() -> str:
    """
    Automatycznie dobiera najlepszy backend do zrzutów ekranu.
    """
    # 1. Sprawdzamy KDE Wayland - tu Spectacle jest jedynym pewnym wyjściem
    if _is_kde_wayland():
        return 'kde_spectacle'

    if not HAS_MSS:
        return 'pyscreenshot'

    system = platform.system().lower()
    if system == 'windows':
        return 'mss'
    if system == 'linux':
        session_type = os.environ.get('XDG_SESSION_TYPE', '').lower()
        if 'wayland' in session_type:
            return 'pyscreenshot'
        return 'mss'
    return 'pyscreenshot'


SCREENSHOT_BACKEND = _determine_backend()


def capture_fullscreen() -> Optional[Image.Image]:
    """
    Pobiera zrzut całego ekranu.
    """
    try:
        print(f"[capture_fullscreen] backend={SCREENSHOT_BACKEND}")
        if SCREENSHOT_BACKEND == 'kde_spectacle':
            try:
                grabber = KWinSpectacleWrapper()
                return grabber.grab()
            except Exception as e:
                print(f"Błąd backendu Spectacle: {e}, fallback...", file=sys.stderr)

        if SCREENSHOT_BACKEND == 'mss':
            with mss.mss() as sct:
                monitor = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
                sct_img = sct.grab(monitor)
                return Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")

        img = ImageGrab.grab()
        try:
            print(f"[capture_fullscreen] grabbed size={img.size}")
        except Exception:
            pass
        return img

    except Exception as e:
        print(f"BŁĄD (capture_fullscreen): {e}", file=sys.stderr)
        try:
            img = ImageGrab.grab()
            try:
                print(f"[capture_fullscreen][fallback] grabbed size={img.size}")
            except Exception:
                pass
            return img
        except Exception:
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

        if SCREENSHOT_BACKEND == 'kde_spectacle':
            try:
                grabber = KWinSpectacleWrapper()
                return grabber.grab(x=left, y=top, width=width, height=height)
            except Exception as e:
                print(f"Błąd backendu Spectacle (region): {e}, fallback...", file=sys.stderr)

        if SCREENSHOT_BACKEND == 'mss':
            with mss.mss() as sct:
                rect = {"top": top, "left": left, "width": width, "height": height}
                sct_img = sct.grab(rect)
                img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
                return img
        img = ImageGrab.grab(bbox=(left, top, left + width, top + height))

    except Exception as e:
        print(f"BŁĄD (capture_region): {e}", file=sys.stderr)
        return None