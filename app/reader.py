from collections import deque
import os
import sys
import threading
import time
from typing import Any, Deque, Dict

from app.utils import capture_screen_region, find_best_match, load_config, load_text_file, ocr_and_clean_image

try:
    from PIL import Image, ImageOps, ImageEnhance, ImageTk
except ImportError:
    print("Błąd: Nie znaleziono biblioteki 'Pillow'. Zainstaluj ją: pip install Pillow", file=sys.stderr)
    sys.exit(1)

class ReaderThread(threading.Thread):
    """Wątek, który wykonuje OCR i dodaje napisy do kolejki."""


    def __init__(self, config_path: str, regex_pattern: str, app_settings: Dict[str, Any], stop_event: threading.Event, audio_queue):
        super().__init__(daemon=True)
        self.name = "ReaderThread"
        print(f"Inicjalizacja wątku czytelnika z presetem: {config_path}")

        self.stop_event = stop_event
        self.audio_queue = audio_queue
        self.config_path = config_path
        self.regex_pattern = regex_pattern
        self.app_settings = app_settings  # <-- NOWE
        self.subtitle_mode = app_settings.get('subtitle_mode', 'Full Lines')

        self.recent_indices: Deque[int] = deque(maxlen=5)  # Bufor 5 ostatnich
        self.last_ocr_text = ""

        self.ocr_scale = self.app_settings.get('ocr_scale_factor', 1.0)
        self.ocr_grayscale = self.app_settings.get('ocr_grayscale', False)
        self.ocr_contrast = self.app_settings.get('ocr_contrast', False)

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
                # Ustawienie na 2.0 mocno podbija kontrast
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
            subtitles = load_text_file(config['text_file_path'])
            if not subtitles:
                print("BŁĄD: Plik napisów jest pusty lub nie istnieje. Zatrzymuję wątek.", file=sys.stderr)
                return

            monitor_config = config['monitor']
            capture_interval = config.get('CAPTURE_INTERVAL', 0.5)
            audio_dir = config['audio_dir']

            print(
                f"Czytelnik rozpoczyna pętlę (Tryb: {self.subtitle_mode}, Bufor: {self.recent_indices.maxlen})...")
            while not self.stop_event.is_set():
                start_time = time.monotonic()

                image = capture_screen_region(monitor_config)
                if not image:
                    time.sleep(capture_interval)
                    continue

                processed_image = self.preprocess_image(image)
                ocr_text = ocr_and_clean_image(
                    processed_image, self.regex_pattern)

                if not ocr_text:
                    self.last_ocr_text = ""
                    time.sleep(capture_interval)
                    continue

                if ocr_text == self.last_ocr_text:
                    time.sleep(capture_interval)
                    continue
                self.last_ocr_text = ocr_text
                
                print(f"\nOCR odczytał: '{ocr_text}'")

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
                time.sleep(wait_time)

        except Exception as e:
            print(f"KRYTYCZNY BŁĄD w wątku czytelnika: {e}", file=sys.stderr)
        finally:
            print("Wątek czytelnika zatrzymany.")
