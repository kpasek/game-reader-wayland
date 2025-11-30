import threading
import time
import os
import re
import queue
from collections import deque
from datetime import datetime
from typing import Optional, Tuple, Dict, Any, List

from app.capture import capture_region
from app.ocr import preprocess_image, recognize_text  # Zaktualizowany import
from app.matcher import find_best_match, precompute_subtitles
from app.config_manager import ConfigManager


class CaptureWorker(threading.Thread):
    """Wątek PRODUCENTA: Robi zrzuty ekranu."""

    def __init__(self, stop_event: threading.Event, img_queue: queue.Queue,
                 unified_area: Dict[str, int], interval: float):
        super().__init__(daemon=True)
        self.stop_event = stop_event
        self.img_queue = img_queue
        self.unified_area = unified_area
        self.interval = interval

    def run(self):
        while not self.stop_event.is_set():
            loop_start = time.monotonic()

            t0 = time.perf_counter()
            full_img = capture_region(self.unified_area)
            t_cap = (time.perf_counter() - t0) * 1000

            if full_img:
                try:
                    # Jeśli kolejka pełna, wyrzucamy najstarszą klatkę (drop frame)
                    if self.img_queue.full():
                        try:
                            self.img_queue.get_nowait()
                        except queue.Empty:
                            pass

                    self.img_queue.put((full_img, t_cap), block=False)
                except queue.Full:
                    pass

            elapsed = time.monotonic() - loop_start
            # Dynamiczny sleep - staraj się trzymać interwał
            sleep_time = max(0.01, self.interval - elapsed)
            time.sleep(sleep_time)


class ReaderThread(threading.Thread):
    """Wątek KONSUMENTA: OCR i Matching."""

    def __init__(self, config_path: str, regex_template: str, app_settings: Dict[str, Any],
                 stop_event: threading.Event, audio_queue,
                 target_resolution: Optional[Tuple[int, int]],
                 log_queue=None,
                 auto_remove_names: bool = True):
        super().__init__(daemon=True)
        self.config_path = config_path
        self.regex_template = regex_template
        self.app_settings = app_settings
        self.stop_event = stop_event
        self.audio_queue = audio_queue
        self.log_queue = log_queue
        self.target_resolution = target_resolution
        self.auto_remove_names = auto_remove_names

        self.recent_match_indices = deque(maxlen=10)
        self.last_ocr_texts = deque(maxlen=5)
        self.last_matched_idx = -1
        self.area3_expiry_time = 0.0
        self.img_queue = None
        self.combined_regex = ""

        # Cache ustawień
        self.ocr_scale = 1.0
        self.subtitle_mode = 'Full Lines'
        self.ocr_grayscale = app_settings.get('ocr_grayscale', False)
        self.ocr_contrast = app_settings.get('ocr_contrast', False)

    def trigger_area_3(self, duration: float = 2.0):
        self.area3_expiry_time = time.time() + duration
        if self.log_queue:
            self.log_queue.put({
                "time": datetime.now().strftime('%H:%M:%S'),
                "ocr": "SYSTEM", "match": None,
                "line_text": f"Aktywowano Obszar 3 na {duration}s", "stats": {}
            })

    def _prepare_regex(self, names_path: str) -> str:
        names = ConfigManager.load_text_lines(names_path)
        if not names or "{NAMES}" not in self.regex_template:
            return self.regex_template.replace("{NAMES}", r"\0\Z")
        escaped_names = [re.escape(n) for n in names]
        pattern = "|".join(escaped_names)
        return self.regex_template.replace("{NAMES}", f"({pattern})")

    def _scale_monitor_areas(self, monitors: List[Dict], original_res_str: str) -> List[Dict]:
        if not self.target_resolution or not original_res_str: return monitors
        try:
            orig_w, orig_h = map(int, original_res_str.lower().split('x'))
            target_w, target_h = self.target_resolution
            if (orig_w, orig_h) == (target_w, target_h): return monitors
            sx, sy = target_w / orig_w, target_h / orig_h
            return [{'left': int(m['left'] * sx), 'top': int(m['top'] * sy),
                     'width': int(m['width'] * sx), 'height': int(m['height'] * sy)} for m in monitors]
        except:
            return monitors

    def run(self):
        preset = ConfigManager.load_preset(self.config_path)
        if not preset: return

        self.ocr_scale = preset.get('ocr_scale_factor', 1.0)
        self.subtitle_mode = preset.get('subtitle_mode', 'Full Lines')
        interval = preset.get('capture_interval', 0.5)

        raw_subtitles = ConfigManager.load_text_lines(preset.get('text_file_path'))
        precomputed_data = precompute_subtitles(raw_subtitles) if raw_subtitles else ([], {})
        self.combined_regex = self._prepare_regex(preset.get('names_file_path'))

        raw_monitors = preset.get('monitor', [])
        if isinstance(raw_monitors, dict): raw_monitors = [raw_monitors]
        monitors = self._scale_monitor_areas([m for m in raw_monitors if m], preset.get('resolution'))
        if not monitors: return

        min_l = min(m['left'] for m in monitors)
        min_t = min(m['top'] for m in monitors)
        max_r = max(m['left'] + m['width'] for m in monitors)
        max_b = max(m['top'] + m['height'] for m in monitors)
        unified_area = {'left': min_l, 'top': min_t, 'width': max_r - min_l, 'height': max_b - min_t}

        queue_size = 2  # Mała kolejka by wymusić dropowanie starych klatek
        self.img_queue = queue.Queue(maxsize=queue_size)
        audio_dir = preset.get('audio_dir', '')

        capture_worker = CaptureWorker(self.stop_event, self.img_queue, unified_area, interval)
        capture_worker.start()

        print("ReaderThread started.")

        while not self.stop_event.is_set():
            try:
                full_img, t_cap = self.img_queue.get(timeout=0.2)
            except queue.Empty:
                continue

            # Jeśli mamy bardzo duże opóźnienie w kolejce, pomijamy klatkę (jeśli w kolejce coś jeszcze czeka)
            if self.img_queue.qsize() > 0:
                try:
                    self.img_queue.get_nowait()
                except queue.Empty:
                    pass

            for idx, area in enumerate(monitors):
                # Pomijanie obszaru 3 jeśli nieaktywny
                if idx == 2 and time.time() > self.area3_expiry_time:
                    continue

                rel_x, rel_y = area['left'] - min_l, area['top'] - min_t
                crop = full_img.crop((rel_x, rel_y, rel_x + area['width'], rel_y + area['height']))

                t1 = time.perf_counter()
                processed = preprocess_image(crop, self.ocr_scale, self.ocr_grayscale, self.ocr_contrast)

                # recognize_text teraz zawiera szybki test na puste tło!
                text = recognize_text(processed, self.combined_regex, self.auto_remove_names)
                t_ocr = (time.perf_counter() - t1) * 1000

                # Jeśli tekst pusty, nie logujemy nawet, żeby nie śmiecić i nie tracić czasu na I/O
                if not text:
                    continue

                if len(text) < 2 or text in self.last_ocr_texts:
                    continue
                self.last_ocr_texts.append(text)

                t2 = time.perf_counter()
                match = find_best_match(text, precomputed_data, self.subtitle_mode, last_index=self.last_matched_idx)
                t_match = (time.perf_counter() - t2) * 1000

                if self.log_queue:
                    line_txt = raw_subtitles[match[0]] if match else ""
                    self.log_queue.put({
                        "time": datetime.now().strftime('%H:%M:%S'),
                        "ocr": text, "match": match, "line_text": line_txt,
                        "stats": {"monitor": idx + 1, "cap_ms": t_cap, "ocr_ms": t_ocr, "match_ms": t_match}
                    })

                if match:
                    idx_match, score = match
                    self.last_matched_idx = idx_match
                    if idx_match not in self.recent_match_indices:
                        print(f"Match: {score}% -> Line {idx_match}")
                        self.recent_match_indices.append(idx_match)
                        self.audio_queue.put(os.path.join(audio_dir, f"output1 ({idx_match + 1}).ogg"))

        capture_worker.join()