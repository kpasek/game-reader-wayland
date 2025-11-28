import threading
import time
import os
import re
from collections import deque
from datetime import datetime
from typing import Optional, Tuple, Dict, Any, List

# Importy z naszych nowych modułów
from app.capture import capture_region
from app.ocr import preprocess_image, recognize_text
from app.matcher import find_best_match
from app.config_manager import ConfigManager


class ReaderThread(threading.Thread):
    def __init__(self, config_path: str, regex_template: str, app_settings: Dict[str, Any],
                 stop_event: threading.Event, audio_queue,
                 target_resolution: Optional[Tuple[int, int]],
                 log_queue=None):
        super().__init__(daemon=True)
        self.name = "ReaderThread"
        self.config_path = config_path
        self.regex_template = regex_template
        self.app_settings = app_settings
        self.stop_event = stop_event
        self.audio_queue = audio_queue
        self.log_queue = log_queue
        self.target_resolution = target_resolution

        # Bufory historii
        self.recent_match_indices = deque(maxlen=5)
        self.last_ocr_texts = deque(maxlen=5)
        self.log_buffer = deque(maxlen=1000)

        # Ustawienia wydajności
        self.ocr_scale = app_settings.get('ocr_scale_factor', 1.0)
        self.ocr_grayscale = app_settings.get('ocr_grayscale', False)
        self.ocr_contrast = app_settings.get('ocr_contrast', False)
        self.subtitle_mode = app_settings.get('subtitle_mode', 'Full Lines')

        self.combined_regex = ""

    def _prepare_regex(self, names_path: str) -> str:
        """Podmienia {NAMES} w regexie na listę imion z pliku."""
        names = ConfigManager.load_text_lines(names_path)
        if not names or "{NAMES}" not in self.regex_template:
            return self.regex_template.replace("{NAMES}", r"\0\Z")  # Jeśli brak imion, usuń znacznik

        escaped_names = [re.escape(n) for n in names]
        pattern = "|".join(escaped_names)
        return self.regex_template.replace("{NAMES}", f"({pattern})")

    def _scale_monitor_areas(self, monitors: List[Dict], original_res_str: str) -> List[Dict]:
        """Przelicza współrzędne obszarów, jeśli rozdzielczość gry jest inna niż natywna."""
        if not self.target_resolution or not original_res_str:
            return monitors

        try:
            orig_w, orig_h = map(int, original_res_str.lower().split('x'))
            target_w, target_h = self.target_resolution

            if (orig_w, orig_h) == (target_w, target_h):
                return monitors

            print(f"Skalowanie obszarów: {orig_w}x{orig_h} -> {target_w}x{target_h}")
            sx = target_w / orig_w
            sy = target_h / orig_h

            scaled = []
            for m in monitors:
                scaled.append({
                    'left': int(m['left'] * sx),
                    'top': int(m['top'] * sy),
                    'width': int(m['width'] * sx),
                    'height': int(m['height'] * sy)
                })
            return scaled
        except Exception as e:
            print(f"Błąd skalowania obszarów: {e}")
            return monitors

    def run(self):
        # 1. Ładowanie konfiguracji presetu
        preset = ConfigManager.load_preset(self.config_path)
        if not preset:
            print("Błąd: Nie można wczytać presetu.")
            return

        subtitles = ConfigManager.load_text_lines(preset.get('text_file_path'))
        if not subtitles:
            print("Błąd: Brak pliku z napisami.")
            return

        self.combined_regex = self._prepare_regex(preset.get('names_file_path'))

        # 2. Przygotowanie obszarów
        raw_monitors = preset.get('monitor', [])
        if isinstance(raw_monitors, dict): raw_monitors = [raw_monitors]

        monitors = self._scale_monitor_areas([m for m in raw_monitors if m], preset.get('resolution'))
        if not monitors:
            print("Błąd: Brak zdefiniowanych obszarów.")
            return

        # 3. Obliczanie Unified Bounding Box (aby robić jeden zrzut zamiast N)
        min_l = min(m['left'] for m in monitors)
        min_t = min(m['top'] for m in monitors)
        max_r = max(m['left'] + m['width'] for m in monitors)
        max_b = max(m['top'] + m['height'] for m in monitors)

        unified_area = {
            'left': min_l, 'top': min_t,
            'width': max_r - min_l, 'height': max_b - min_t
        }

        audio_dir = preset.get('audio_dir', '')
        interval = preset.get('CAPTURE_INTERVAL', 0.3)

        print(f"Start wątku czytającego. Obszar całkowity: {unified_area}")

        while not self.stop_event.is_set():
            loop_start = time.monotonic()

            # A. Pobranie zrzutu
            t0 = time.perf_counter()
            full_img = capture_region(unified_area)
            t_cap = (time.perf_counter() - t0) * 1000

            if not full_img:
                time.sleep(0.1)
                continue

            # B. Iteracja po podobszarach
            for idx, area in enumerate(monitors):
                # Wycinamy fragment z dużego obrazka
                # Współrzędne względne wewnątrz unified_area
                rel_x = area['left'] - min_l
                rel_y = area['top'] - min_t
                rel_w = area['width']
                rel_h = area['height']

                crop = full_img.crop((rel_x, rel_y, rel_x + rel_w, rel_y + rel_h))

                # C. OCR
                t1 = time.perf_counter()
                processed = preprocess_image(crop, self.ocr_scale, self.ocr_grayscale, self.ocr_contrast)
                text = recognize_text(processed, self.combined_regex)
                t_ocr = (time.perf_counter() - t1) * 1000

                if not text or len(text) < 2: continue
                if text in self.last_ocr_texts: continue  # Ignoruj powtórzenia OCR

                self.last_ocr_texts.append(text)

                # D. Dopasowanie
                t2 = time.perf_counter()
                match = find_best_match(text, subtitles, self.subtitle_mode)
                t_match = (time.perf_counter() - t2) * 1000

                print(f"OCR [{idx + 1}]: '{text}'")

                # Logowanie
                if self.log_queue:
                    self.log_queue.put({
                        "time": datetime.now().strftime('%H:%M:%S'),
                        "ocr": text,
                        "match": match,
                        "line_text": subtitles[match[0]] if match else "",
                        "stats": {"monitor": idx + 1, "cap_ms": t_cap, "ocr_ms": t_ocr, "match_ms": t_match}
                    })

                # E. Akcja po dopasowaniu
                if match:
                    idx_match, score = match
                    if idx_match not in self.recent_match_indices:
                        print(f" >>> DOPASOWANIE ({score}%): {subtitles[idx_match]}")
                        self.recent_match_indices.append(idx_match)
                        self.log_buffer.append(f"Match: {score}% | {subtitles[idx_match]}")

                        audio_file = os.path.join(audio_dir, f"output1 ({idx_match + 1}).ogg")
                        self.audio_queue.put(audio_file)

            elapsed = time.monotonic() - loop_start
            time.sleep(max(0, interval - elapsed))