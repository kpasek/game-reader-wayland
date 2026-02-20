import threading
import time
import os
import queue
import copy
from collections import deque
from datetime import datetime
from typing import Any, Optional, Tuple, Dict, List
# ImageChops jest wykorzystywany w funkcji _images_are_similar, a ImageStat w tej samej funkcji.
from PIL import Image, ImageChops, ImageStat

from app.capture import capture_region
from app.ocr import preprocess_image, recognize_text
from app.matcher import find_best_match, precompute_subtitles
from app.config_manager import ConfigManager, AreaConfig


class CaptureWorker(threading.Thread):
    """Wątek PRODUCENTA: Robi zrzuty ekranu."""

    def __init__(self, stop_event: threading.Event, img_queue: queue.Queue,
                 unified_area: Dict[str, int], interval: float, log_queue=None):
        super().__init__(daemon=True)
        self.stop_event = stop_event
        self.img_queue = img_queue
        self.unified_area = unified_area
        self.interval = interval
        self.log_queue = log_queue
        self.first_capture_done = False

    def run(self):
        while not self.stop_event.is_set():
            loop_start = time.monotonic()
            
            self.capture()
            elapsed = time.monotonic() - loop_start
            time.sleep(max(0.01, self.interval - elapsed))

    def capture(self):
        t0 = time.perf_counter()
        try:
            full_img = capture_region(self.unified_area)
        except Exception as e:
            full_img = None
            
        t_cap = (time.perf_counter() - t0) * 1000

        if full_img:
            if not self.first_capture_done:
                self.first_capture_done = True

            try:
                if self.img_queue.full():
                    try:
                        self.img_queue.get_nowait()
                    except queue.Empty:
                        pass
                self.img_queue.put((full_img, t_cap), block=False)
            except queue.Full:
                pass
        else:
            print(f"CaptureWorker: Capture failed (returned None)!")
            if not self._logged_fail:
                self._logged_fail = True
                msg = "CaptureWorker: Failed to grab screen (returned None/Empty)!"
                if self.log_queue:
                    self.log_queue.put({"time": "ERROR", "line_text": msg})



class ReaderThread(threading.Thread):
    """Wątek KONSUMENTA: OCR i Matching."""

    def __init__(self, config_manager: ConfigManager,
                 stop_event: threading.Event, audio_queue,
                 target_resolution: Optional[Tuple[int, int]],
                 log_queue=None,
                 debug_queue: Optional[queue.Queue] = None, brightness_threshold: int = 200):
        super().__init__(daemon=True)
        self.config_manager = config_manager
        self.stop_event = stop_event
        self.audio_queue = audio_queue
        self.log_queue = log_queue
        self.debug_queue = debug_queue
        self.target_resolution = target_resolution
        self.brightness_threshold = brightness_threshold

        self.recent_match_indices = deque(maxlen=3)
        self.last_ocr_texts = deque(maxlen=5)
        self.last_matched_idx = -1
        self.img_queue = None
        self.last_monitor_crops: Dict[int, Image.Image] = {}

        self.triggered_area_ids = set()
        self.enabled_continuous_areas = set()  # Dla stałych obszarów (poza 1)

        self.ocr_scale = 1.0
        self.empty_threshold = 0.15
        # config-managed values (access via ConfigManager when needed)

        # Use ConfigManager for text color
        self.text_color = config_manager.text_color_mode

        self.ocr_binarize = True

        self.current_unified_area = {'left': 0, 'top': 0, 'width': 0, 'height': 0}

    def trigger_area(self, area_id: Any):
        """Aktywuje jednorazowe pobranie i przetworzenie Obszaru o danym ID (manual/triggered)."""
        self.triggered_area_ids.add(area_id)

    def toggle_continuous_area(self, area_id: Any):
        """Włącza lub wyłącza przetwarzanie stałego obszaru (continuous)."""
        if self._is_main_area(area_id):
            return  # Obszar główny jest zawsze włączony

        if area_id in self.enabled_continuous_areas:
            self.enabled_continuous_areas.remove(area_id)
            if self.log_queue:
                self.log_queue.put({"time": "INFO", "line_text": f"Area #{area_id} deactivated."})
        else:
            self.enabled_continuous_areas.add(area_id)
            if self.log_queue:
                self.log_queue.put({"time": "INFO", "line_text": f"Area #{area_id} activated."})

    def _is_main_area(self, area_id: Any, index: int = -1) -> bool:
        """Checks if the ID refers to the canonical 'Main' area (0, 1, 'area_0' or 'area_1'?).
        Note: Migration uses 'area_0' for monitor[0], 'area_1' for monitor[1].
        Technically monitor[0] (slot 1 in UI) is the 'primary' one.
        """
        if index == 0:
            return True
        return area_id == 0 or area_id == 1 or str(area_id).lower() in ["area_0", "area_1"]


    # (Area-specific overrides handled explicitly during processing;
    # no helper methods for applying/restoring are used here.)
                 
    def _images_are_similar(self, img1: Image.Image, img2: Image.Image, similarity: float) -> bool:
        if similarity == 0: return False
        if img1 is None or img2 is None: return False
        if img1.size != img2.size: return False
        diff = ImageChops.difference(img1, img2)
        stat = ImageStat.Stat(diff)
        return sum(stat.mean) < similarity

    def run(self):
        if self.target_resolution:
            self.config_manager.display_resolution = self.target_resolution

        preset = self.config_manager.load_preset()
        if not preset: return

        # Ładowanie parametrów z ConfigManager (zawiera domyślne)
        interval = self.config_manager.capture_interval
        similarity = self.config_manager.similarity
        min_line_len = self.config_manager.min_line_length

        audio_speed = self.config_manager.audio_speed_inc

        raw_subtitles = self.config_manager.load_text_lines()
        precomputed_data = precompute_subtitles(raw_subtitles, min_line_len) if raw_subtitles else ([], {})

        # Get areas already scaled to the manager's display resolution
        areas_config = copy.deepcopy(self.config_manager.get_areas() or [])
        valid_areas = areas_config


        if not valid_areas:
            if self.log_queue:
                self.log_queue.put({"time": "ERROR", "line_text": "Nie znaleziono aktywnych obszarów. Sprawdź konfigurację."})
            return
        
        
        # Initialize enabled continuous areas from config
        self.enabled_continuous_areas = set()
        for area in valid_areas:
            # area is AreaConfig
            if area.type == 'continuous' and area.enabled:
                self.enabled_continuous_areas.add(area.id)

        # Areas returned by `get_preset_for_display` are already scaled to the
        # manager's `display_resolution` (if set). No further scaling required.

        monitors = [a.rect for a in valid_areas] # For Unified Calculation

        min_l = min(m['left'] for m in monitors)
        min_t = min(m['top'] for m in monitors)
        max_r = max(m['left'] + m['width'] for m in monitors)
        max_b = max(m['top'] + m['height'] for m in monitors)
        unified_area = {'left': min_l, 'top': min_t, 'width': max_r - min_l, 'height': max_b - min_t}

        self.current_unified_area = {
            'left': min_l,
            'top': min_t,
            'width': max_r - min_l,
            'height': max_b - min_t
        }

        queue_size = 4
        self.img_queue = queue.Queue(maxsize=queue_size)
        audio_dir = self.config_manager.audio_dir
        audio_ext = self.config_manager.audio_ext

        capture_worker = CaptureWorker(self.stop_event, self.img_queue, unified_area, interval, log_queue=self.log_queue)
        capture_worker.start()

        if self.log_queue:
             self.log_queue.put({"time": "INFO", "line_text": f"Reader started. Areas: {len(valid_areas)}. Logging enabled."})

        if self.config_manager.save_logs:
            if self.log_queue: self.log_queue.put({"time": "INFO", "line_text": f"Saving logs to session_log.txt"})
            with open("session_log.txt", "a", encoding='utf-8') as f:
                f.write(f"\n=== SESSION START {datetime.now()} ===\n")
                f.write("Time | Monitor | Capture(ms) | Pre(ms) | OCR(ms) | Match(ms) | Text | MatchResult\n")


        while not self.stop_event.is_set():
            try:
                full_img, t_cap = self.img_queue.get(timeout=2.0)
            except queue.Empty:
                continue

            if self.img_queue.qsize() > 0:
                try:
                    self.img_queue.get_nowait()
                except queue.Empty:
                    pass


            for idx, area_obj in enumerate(valid_areas):
                t_start_proc = time.perf_counter()
                area_id = area_obj.id
                area_rect = area_obj.rect
                area_type = area_obj.type
                # Logika włączania/wyłączania obszarów
                if area_type == 'manual':
                    if area_id not in self.triggered_area_ids:
                        continue
                    self.triggered_area_ids.remove(area_id)
                    self.last_monitor_crops.pop(idx, None)
                elif area_type == 'continuous':
                    # First slot (Area 0 or 1 depending on slot naming) is always active.
                    if not self._is_main_area(area_id, index=idx) and area_id not in self.enabled_continuous_areas:
                        continue

                rel_x, rel_y = area_rect['left'] - min_l, area_rect['top'] - min_t
                crop = full_img.crop((rel_x, rel_y, rel_x + area_rect['width'], rel_y + area_rect['height']))

                last_crop = self.last_monitor_crops.get(idx)
                if self._images_are_similar(crop, last_crop, similarity):
                    continue
                
                self.last_monitor_crops[idx] = crop.copy()

                t_pre_start = time.perf_counter()

                # Use explicit area object for preprocessing (no mutation of global config)
                processed, has_content, crop_bbox = preprocess_image(crop, self.config_manager, area_config=area_obj)

                if not has_content:
                    continue

                t_pre = (time.perf_counter() - t_pre_start) * 1000

                t_ocr_start = time.perf_counter()
                text = recognize_text(processed, self.config_manager)

                t_ocr = (time.perf_counter() - t_ocr_start) * 1000

                # Matching: log debug info, then use global ConfigManager and area-specific subtitle mode
                current_subtitle_mode = area_obj.subtitle_mode
                try:
                    pre_lines_count = len(precomputed_data[0]) if precomputed_data and isinstance(precomputed_data, tuple) else 0
                except Exception:
                    pre_lines_count = 0

                dbg_msg = (
                    f"MATCH DEBUG: text='{text}' | pre_lines={pre_lines_count} | "
                    f"mode={current_subtitle_mode} | partial_min_len={self.config_manager.partial_mode_min_len} | "
                    f"match_score_short={self.config_manager.match_score_short} | match_score_long={self.config_manager.match_score_long} | "
                    f"match_len_diff_ratio={self.config_manager.match_len_diff_ratio}"
                )
                if self.log_queue:
                    self.log_queue.put({"time": datetime.now().strftime('%H:%M:%S.%f')[:-3], "line_text": dbg_msg})

                t_match_start = time.perf_counter()
                match = find_best_match(text, precomputed_data, current_subtitle_mode,
                                        last_index=self.last_matched_idx,
                                        matcher_config=self.config_manager)
                t_match = (time.perf_counter() - t_match_start) * 1000

                if not text:
                    continue

                if len(text) < 2 or text in self.last_ocr_texts:
                    continue

                if has_content and crop_bbox and self.debug_queue:
                    abs_x = area_rect['left'] + crop_bbox[0]
                    abs_y = area_rect['top'] + crop_bbox[1]

                    abs_w = crop_bbox[2] - crop_bbox[0]
                    abs_h = crop_bbox[3] - crop_bbox[1]
                    self.debug_queue.put(('overlay', (abs_x, abs_y, abs_w, abs_h)))

                self.last_ocr_texts.append(text)

                # `match` and `t_match` already computed while overrides were active

                if self.log_queue:
                    line_txt = raw_subtitles[match[0]] if match else ""
                    log_entry = {
                        "time": datetime.now().strftime('%H:%M:%S.%f')[:-3],
                        "ocr": text, "match": match, "line_text": line_txt,
                        "stats": {
                            "monitor": f"#{area_id}",
                            "cap_ms": t_cap,
                            "pre_ms": t_pre,
                            "ocr_ms": t_ocr,
                            "match_ms": t_match
                        }
                    }
                    self.log_queue.put(log_entry)
                    if self.config_manager.save_logs:
                        with open("session_log.txt", "a", encoding='utf-8') as f:
                            match_str = f"MATCH({match[1]}%): {line_txt}" if match else "NO MATCH"
                            log_line = (f"{log_entry['time']} | A{area_id} | "
                                        f"Cap:{t_cap:.0f}ms | Pre:{t_pre:.0f}ms | OCR:{t_ocr:.0f}ms | Match:{t_match:.0f}ms | "
                                        f"'{text}' | {match_str}\n")
                            f.write(log_line)

                if match:
                    idx_match, score = match
                    self.last_matched_idx = idx_match
                    if idx_match not in self.recent_match_indices:
                        pass # Match log removed
                        self.recent_match_indices.append(idx_match)

                        audio_path = os.path.join(audio_dir, f"output1 ({idx_match + 1}){audio_ext}")
                        if not os.path.exists(audio_path):
                            print(f"Audio file not found: {audio_path}")

                        q_size = self.audio_queue.qsize()
                        speed_multiplier = 1.0

                        if q_size > 0:
                            speed_multiplier = audio_speed

                        self.audio_queue.put((audio_path, speed_multiplier))

        capture_worker.join()