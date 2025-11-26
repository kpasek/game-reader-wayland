from collections import deque
import datetime
import os
import sys
import re
import threading
import time
from typing import Any, Deque, Dict, Optional, Tuple, List

from app.utils import capture_screen_region, find_best_match, load_config, load_text_file, ocr_and_clean_image

try:
    from PIL import Image, ImageOps, ImageEnhance
except ImportError:
    print("Błąd: Nie znaleziono biblioteki 'Pillow'.", file=sys.stderr)
    sys.exit(1)


class ReaderThread(threading.Thread):
    def __init__(self, config_path: str, regex_template: str, app_settings: Dict[str, Any],
                 stop_event: threading.Event, audio_queue,
                 target_resolution: Optional[Tuple[int, int]],
                 log_queue=None):
        super().__init__(daemon=True)
        self.name = "ReaderThread"
        print(f"Inicjalizacja wątku czytelnika z presetem: {config_path}")

        self.stop_event = stop_event
        self.audio_queue = audio_queue
        self.log_queue = log_queue
        self.config_path = config_path
        self.regex_template = regex_template
        self.combined_regex_pattern = ""
        self.app_settings = app_settings
        self.subtitle_mode = app_settings.get('subtitle_mode', 'Full Lines')

        self.recent_indices: Deque[int] = deque(maxlen=5)
        self.log_buffer: Deque[str] = deque(maxlen=1000)

        self.last_ocr_texts = deque(maxlen=5)

        self.ocr_scale = self.app_settings.get('ocr_scale_factor', 1.0)
        self.ocr_grayscale = self.app_settings.get('ocr_grayscale', False)
        self.ocr_contrast = self.app_settings.get('ocr_contrast', False)
        self.target_resolution = target_resolution

    def _build_combined_regex(self, config: Dict[str, Any], template: str) -> str:
        names_file_path = config.get("names_file_path")
        names_list = []
        if names_file_path and os.path.exists(names_file_path):
            names_list = load_text_file(names_file_path)

        if names_list and "{NAMES}" in template:
            escaped_names = [re.escape(name.strip()) for name in names_list if name.strip()]
            if not escaped_names:
                return template.replace("{NAMES}", r"\0\Z")
            names_pattern = "|".join(escaped_names)
            return template.replace("{NAMES}", f"({names_pattern})")
        elif "{NAMES}" in template:
            return template.replace("{NAMES}", r"\0\Z")
        else:
            return template

    def _recalculate_monitor_area(self, config: Dict[str, Any], target_res: Optional[Tuple[int, int]]) -> List[
        Dict[str, int]]:
        original_monitor_data = config.get('monitor', [])

        monitor_list = []
        if isinstance(original_monitor_data, list):
            monitor_list = original_monitor_data
        elif isinstance(original_monitor_data, dict):
            monitor_list = [original_monitor_data]

        monitor_list = [m for m in monitor_list if m]

        original_res_str = config.get("resolution")

        if not target_res or not original_res_str:
            return monitor_list

        try:
            orig_w, orig_h = map(int, original_res_str.lower().split('x'))
            target_w, target_h = target_res

            if (orig_w, orig_h) == (target_w, target_h):
                return monitor_list

            print(f"Przeliczanie obszarów z {orig_w}x{orig_h} do {target_w}x{target_h}...")
            x_ratio = target_w / orig_w
            y_ratio = target_h / orig_h

            new_list = []
            for area in monitor_list:
                new_area = {
                    'left': int(area['left'] * x_ratio),
                    'top': int(area['top'] * y_ratio),
                    'width': int(area['width'] * x_ratio),
                    'height': int(area['height'] * y_ratio)
                }
                new_list.append(new_area)

            return new_list
        except Exception as e:
            print(f"BŁĄD przeliczania rozdzielczości: {e}", file=sys.stderr)
            return monitor_list

    def preprocess_image(self, image: Image.Image) -> Image.Image:
        try:
            if self.ocr_scale < 1.0:
                new_width = int(image.width * self.ocr_scale)
                new_height = int(image.height * self.ocr_scale)
                image = image.resize((new_width, new_height), Image.LANCZOS)  # type: ignore
            if self.ocr_grayscale:
                image = ImageOps.grayscale(image)
            if self.ocr_contrast:
                enhancer = ImageEnhance.Contrast(image)
                image = enhancer.enhance(2.0)
            return image
        except Exception:
            return image

    def run(self):
        try:
            config = load_config(self.config_path)
            self.combined_regex_pattern = self._build_combined_regex(config, self.regex_template)

            monitor_configs = self._recalculate_monitor_area(config, self.target_resolution)

            if not monitor_configs:
                print("BŁĄD: Brak zdefiniowanych obszarów do monitorowania.", file=sys.stderr)
                return

            subtitles = load_text_file(config['text_file_path'])
            if not subtitles:
                print("BŁĄD: Pusty plik napisów.", file=sys.stderr)
                return
            capture_interval = config.get('CAPTURE_INTERVAL', 0.3)
            audio_dir = config['audio_dir']

            min_left = min(c['left'] for c in monitor_configs)
            min_top = min(c['top'] for c in monitor_configs)
            max_right = max(c['left'] + c['width'] for c in monitor_configs)
            max_bottom = max(c['top'] + c['height'] for c in monitor_configs)

            unified_area = {
                'left': min_left,
                'top': min_top,
                'width': max_right - min_left,
                'height': max_bottom - min_top
            }

            print(f"Czytelnik startuje. Obszary: {len(monitor_configs)}. Wspólny obszar zrzutu: {unified_area}")

            while not self.stop_event.is_set():
                start_time = time.monotonic()

                t0_cap = time.perf_counter()
                unified_image = capture_screen_region(unified_area)
                t_cap = (time.perf_counter() - t0_cap) * 1000  # ms

                if not unified_image:
                    time.sleep(0.1)
                    continue

                for idx, area_config in enumerate(monitor_configs):

                    rel_x = area_config['left'] - min_left
                    rel_y = area_config['top'] - min_top
                    rel_w = area_config['width']
                    rel_h = area_config['height']

                    try:
                        # crop((left, top, right, bottom))
                        image = unified_image.crop((rel_x, rel_y, rel_x + rel_w, rel_y + rel_h))
                    except Exception as e:
                        print(f"Błąd wycinania obszaru {idx}: {e}", file=sys.stderr)
                        continue

                    processed_image = self.preprocess_image(image)

                    t0_ocr = time.perf_counter()
                    text = ocr_and_clean_image(processed_image, self.combined_regex_pattern)
                    t_ocr = (time.perf_counter() - t0_ocr) * 1000  # ms

                    if not text or len(text) < 2:
                        continue

                    if text in self.last_ocr_texts:
                        continue

                    self.last_ocr_texts.append(text)

                    # 4. Pomiar czasu dopasowania
                    t0_match = time.perf_counter()
                    match_result = find_best_match(text, subtitles, self.subtitle_mode)
                    t_match = (time.perf_counter() - t0_match) * 1000  # ms

                    print(f"\n{datetime.datetime.now().strftime('%H:%M:%S')} - OCR [{idx + 1}]: '{text}'")

                    if self.log_queue:
                        self.log_queue.put({
                            "time": datetime.datetime.now().strftime('%H:%M:%S'),
                            "ocr": text,
                            "match": match_result,
                            "line_text": subtitles[match_result[0]] if match_result else "",
                            "stats": {
                                "monitor": idx + 1,
                                "cap_ms": t_cap,  # Czas wspólnego zrzutu
                                "ocr_ms": t_ocr,
                                "match_ms": t_match
                            }
                        })

                    if match_result is not None:
                        best_match_index, best_match_score = match_result

                        if best_match_index not in self.recent_indices:
                            print(f" >>> DOPASOWANIE ({best_match_score}%): {subtitles[best_match_index]}")

                            self.log_buffer.append(
                                f"Match: {best_match_score}% | OCR: {text} | Line: {subtitles[best_match_index]}")
                            self.recent_indices.append(best_match_index)

                            file_name = f"output1 ({best_match_index + 1}).ogg"
                            file_path = os.path.join(audio_dir, file_name)
                            self.audio_queue.put(file_path)

                elapsed = time.monotonic() - start_time
                wait_time = max(0, capture_interval - elapsed)
                time.sleep(wait_time)

        except Exception as e:
            print(f"KRYTYCZNY BŁĄD READER: {e}", file=sys.stderr)