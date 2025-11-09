from collections import deque
from datetime import date
import datetime
import os
import sys
import threading
import time
import re
from typing import Any, Deque, Dict
from typing import Any, Deque, Dict, Optional, Tuple

from app.dbus_ss import FreedesktopDBusWrapper
from app.utils import capture_screen_region, find_best_match, load_config, load_text_file, ocr_and_clean_image

try:
    from PIL import Image, ImageOps, ImageEnhance, ImageTk
except ImportError:
    print("Błąd: Nie znaleziono biblioteki 'Pillow'. Zainstaluj ją: pip install Pillow", file=sys.stderr)
    sys.exit(1)

class ReaderThread(threading.Thread):
    """Wątek, który wykonuje OCR i dodaje napisy do kolejki."""


    def __init__(self, config_path: str, regex_template: str, app_settings: Dict[str, Any],
                 stop_event: threading.Event, audio_queue,
                 target_resolution: Optional[Tuple[int, int]]):
        super().__init__(daemon=True)
        self.name = "ReaderThread"
        print(f"Inicjalizacja wątku czytelnika z presetem: {config_path}")

        self.stop_event = stop_event
        self.audio_queue = audio_queue
        self.config_path = config_path
        self.regex_template = regex_template
        self.combined_regex_pattern = ""
        self.app_settings = app_settings
        self.subtitle_mode = app_settings.get('subtitle_mode', 'Full Lines')

        self.recent_indices: Deque[int] = deque(maxlen=5)
        self.last_ocr_text = ""

        self.ocr_scale = self.app_settings.get('ocr_scale_factor', 1.0)
        self.ocr_grayscale = self.app_settings.get('ocr_grayscale', False)
        self.ocr_contrast = self.app_settings.get('ocr_contrast', False)
        self.target_resolution = target_resolution

    def preprocess_image(self, image: Image.Image) -> Image.Image:
        """Stosuje skalowanie, skalę szarości i kontrast do obrazu przed OCR."""
        try:
            # 1. Skalowanie (jeśli trzeba)
            if self.ocr_scale < 1.0:
                new_width = int(image.width * self.ocr_scale)
                new_height = int(image.height * self.ocr_scale)
                image = image.resize(
                    (new_width, new_height), Image.LANCZOS)  # type: ignore

            # 2. Skala szarości
            if self.ocr_grayscale:
                image = ImageOps.grayscale(image)

            # 3. Kontrast
            if self.ocr_contrast:
                enhancer = ImageEnhance.Contrast(image)
                image = enhancer.enhance(2.0)

            return image
        except Exception as e:
            print(
                f"BŁĄD: Błąd podczas preprocessingu obrazu: {e}", file=sys.stderr)
            return image  # Zwróć oryginał w razie błędu

    def run(self):
        try:
            print("Wątek czytelnika uruchomiony.")

            config = load_config(self.config_path)

            # 1. Zbuduj finalny Regex
            self.combined_regex_pattern = self._build_combined_regex(config, self.regex_template)

            # 2. Przelicz obszar monitora
            monitor_config = self._recalculate_monitor_area(config, self.target_resolution)

            subtitles = load_text_file(config['text_file_path'])
            if not subtitles:
                print("BŁĄD: Plik napisów jest pusty lub nie istnieje. Zatrzymuję wątek.", file=sys.stderr)
                return

            monitor_config = config['monitor']
            capture_interval = config.get('CAPTURE_INTERVAL', 0.3)
            audio_dir = config['audio_dir']

            print(
                f"Czytelnik rozpoczyna pętlę (Tryb: {self.subtitle_mode}, Bufor: {self.recent_indices.maxlen})...")
            with FreedesktopDBusWrapper() as dbus:
                while not self.stop_event.is_set():
                    start_time = time.monotonic()

                    image = capture_screen_region(dbus, monitor_config)
                    if not image:
                        time.sleep(capture_interval)
                        continue
                    processed_image = self.preprocess_image(image)
                    ocr_text = ocr_and_clean_image(
                        processed_image, self.combined_regex_pattern)
                    if not ocr_text:
                        self.last_ocr_text = ""
                        time.sleep(capture_interval)
                        continue

                    if ocr_text == self.last_ocr_text:
                        time.sleep(capture_interval)
                        continue
                    self.last_ocr_text = ocr_text
                    
                    print(f"\n{datetime.datetime.now()} - OCR odczytał: '{ocr_text}'")

                    best_match_index = find_best_match(ocr_text, subtitles, self.subtitle_mode)

                    if best_match_index is not None and best_match_index not in self.recent_indices:
                        print(f"Dopasowano (Indeks: {best_match_index}). Dodaję do kolejki.")

                        self.recent_indices.append(best_match_index)
                        
                        line_number = best_match_index + 1
                        file_name = f"output1 ({line_number}).ogg"
                        file_path = os.path.join(audio_dir, file_name)

                        self.audio_queue.put(file_path)

                    elapsed = time.monotonic() - start_time
                    wait_time = max(0, capture_interval - elapsed)

                    print (f"{datetime.datetime.now()} - Czas cyklu: {elapsed:.2f}s, oczekiwanie: {wait_time:.2f}s")
                    time.sleep(wait_time)

        except Exception as e:
            print(f"KRYTYCZNY BŁĄD w wątku czytelnika: {e}", file=sys.stderr)
        finally:
            print("Wątek czytelnika zatrzymany.")


    def _build_combined_regex(self, config: Dict[str, Any], template: str) -> str:
        """Łączy wzorzec regex z GUI z listą imion z pliku."""
        names_file_path = config.get("names_file_path")
        names_list = []

        if names_file_path and os.path.exists(names_file_path):
            print(f"Wczytuję plik imion: {names_file_path}")
            names_list = load_text_file(names_file_path)

        if names_list and "{NAMES}" in template:
            escaped_names = [re.escape(name.strip()) for name in names_list if name.strip()]
            if not escaped_names:
                # Zastąp {NAMES} wzorcem, który nigdy nie pasuje
                return template.replace("{NAMES}", r"\0\Z")

            names_pattern = "|".join(escaped_names)
            final_regex = template.replace("{NAMES}", f"({names_pattern})")
            print(f"Zbudowano połączony Regex (fragment): {final_regex[:100]}...")
            return final_regex
        elif "{NAMES}" in template:
            # Użytkownik użył {NAMES}, ale nie ma pliku - wzorzec nie powinien pasować
            return template.replace("{NAMES}", r"\0\Z")
        else:
            # Użyj wzorca z GUI bezpośrednio
            return template

    def _recalculate_monitor_area(self, config: Dict[str, Any], target_res: Optional[Tuple[int, int]]) -> Dict[str, int]:
        """Przelicza obszar 'monitor' na podstawie docelowej rozdzielczości."""
        original_monitor_config = config['monitor']
        original_res_str = config.get("resolution")

        if not target_res or not original_res_str:
            print("Brak rozdzielczości docelowej lub bazowej, używam obszaru z presetu.")
            return original_monitor_config

        try:
            orig_w, orig_h = map(int, original_res_str.lower().split('x'))
            target_w, target_h = target_res

            if (orig_w, orig_h) == (target_w, target_h):
                return original_monitor_config

            print(f"Przeliczanie obszaru z {orig_w}x{orig_h} do {target_w}x{target_h}...")
            
            x_ratio = target_w / orig_w
            y_ratio = target_h / orig_h

            new_config = {
                'left': int(original_monitor_config['left'] * x_ratio),
                'top': int(original_monitor_config['top'] * y_ratio),
                'width': int(original_monitor_config['width'] * x_ratio),
                'height': int(original_monitor_config['height'] * y_ratio)
            }
            print(f"Nowy przeliczony obszar: {new_config}")
            return new_config
        except Exception as e:
            print(f"BŁĄD: Nie można przeliczyć rozdzielczości: {e}. Używam domyślnej.", file=sys.stderr)
            return original_monitor_config
