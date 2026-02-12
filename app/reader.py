import threading
import time
import os
import queue
from collections import deque
from datetime import datetime
from typing import Optional, Tuple, Dict, Any, List
# ImageChops jest wykorzystywany w funkcji _images_are_similar, a ImageStat w tej samej funkcji.
from PIL import Image, ImageChops, ImageStat, ImageOps, ImageFilter

from app.capture import capture_region
from app.ocr import preprocess_image, recognize_text, get_text_bounds
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

            self.capture()

            elapsed = time.monotonic() - loop_start
            time.sleep(max(0.01, self.interval - elapsed))

    def capture(self):
        t0 = time.perf_counter()
        full_img = capture_region(self.unified_area)
        t_cap = (time.perf_counter() - t0) * 1000

        if full_img:
            try:
                if self.img_queue.full():
                    try:
                        self.img_queue.get_nowait()
                    except queue.Empty:
                        pass
                self.img_queue.put((full_img, t_cap), block=False)
            except queue.Full:
                pass


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

        self.ocr_scale = 1.0
        self.empty_threshold = 0.15
        self.text_alignment = "None"
        self.save_logs = False
        self.subtitle_mode = 'Full Lines'

        self.matcher_config = {}
        self.audio_speed_inc = 1.2

        text_color_mode = config_manager.settings.get('text_color_mode', 'Light')
        self.text_color = text_color_mode

        self.ocr_binarize = True

        self.current_unified_area = {'left': 0, 'top': 0, 'width': 0, 'height': 0}

    def trigger_area(self, area_id: int):
        """Aktywuje jednorazowe pobranie i przetworzenie Obszaru o danym ID."""
        self.triggered_area_ids.add(area_id)
        # Znajdz indeks dla cropa? IDs are unique.
        # W run() uzywamy area['id'] do identyfikacji
        
        if self.log_queue:
            self.log_queue.put({
                "time": datetime.now().strftime('%H:%M:%S'),
                "ocr": "SYSTEM", "match": None,
                "line_text": f"Wyzwołano jednorazowy odczyt Obszaru {area_id}", "stats": {}
            })


    def _scale_monitor_areas_legacy(self, monitors: List[Dict], original_res_str: str) -> List[Dict]:
        """Original Implementation for Reference"""
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

    def _scale_monitor_areas(self, monitors: List[Dict], original_res_str: str) -> List[Dict]:
        """
        Scales area coordinates from the original preset resolution to the actual capture resolution.
        """
        from app.capture import capture_fullscreen
        import time
        
        # Try to determine physical resolution with retries
        if not hasattr(self, '_physical_res'):
            attempts = 10
            for i in range(attempts):
                try:
                    img = capture_fullscreen()
                    if img:
                        self._physical_res = img.size
                        # If we have 4K screen vs 1080p, and we are on wayland, 
                        # ensure we aren't getting fallback logical resolution if possible.
                        # But we can't easily check backend here cleanly.
                        # Just trust that if we got an image, it's correct-ish.
                        break
                except:
                    pass
                if i < attempts - 1:
                    time.sleep(0.5)
            
            if not hasattr(self, '_physical_res'):
                self._physical_res = None
        
        # Debug logging for resolution detection
        if self.log_queue and not hasattr(self, '_logged_res'):
             self._logged_res = True
             res = getattr(self, '_physical_res', 'None')
             msg = f"Resolution Debug: Physical={res}, Target={self.target_resolution}, Preset={original_res_str}"
             self.log_queue.put({"time": "INFO", "line_text": msg})
             # Force log to file as well for debugging
             try:
                 with open("session_debug.log", "a") as f:
                     f.write(f"{datetime.now()} {msg}\n")
             except: pass

        dest_w, dest_h = self._physical_res if getattr(self, '_physical_res', None) else (None, None)
        
        # Parse original resolution
        orig_w, orig_h = None, None
        if original_res_str:
            try:
                orig_w, orig_h = map(int, original_res_str.lower().split('x'))
            except:
                pass

        # Fallback Logic if Physical Capture failed
        if not dest_w or not dest_h:
             if orig_w and orig_h:
                 # Assume same as preset
                 dest_w, dest_h = orig_w, orig_h
             elif self.target_resolution:
                 # Only use target if we really don't know original
                 dest_w, dest_h = self.target_resolution
             else:
                 return monitors
        
        # HiDPI Heuristic Logic
        # Detect if we have a mismatch between Detected (Logical) and Preset (Physical) resolution
        if orig_w and orig_h and dest_w and dest_h:
            target_w = self.target_resolution[0] if self.target_resolution else 0
            
            # Check if this looks like a fractional scaling artifact (e.g. 1.5x which is 3840->2560)
            # Common scaling factors: 1.25, 1.5, 1.75.
            # Ratios like 2.0 (1920x1080) are ambiguous (could be genuine 1080p screen),
            # but 1.5 (2560x1440) is almost certainly HiDPI scaling on a 4K panel.
            ratio_w = orig_w / dest_w
            is_fractional_scale = abs(ratio_w - 1.5) < 0.05 or abs(ratio_w - 1.25) < 0.05 or abs(ratio_w - 1.75) < 0.05
            
            # Use stricter condition: Detected matches Target (Logical) AND (Detected < Preset) AND (Fractional Scale OR User forced via config?)
            # For now, explicit fractional scale detection is safest to avoid breaking 1080p users.
            
            if (orig_w > dest_w) and (target_w and abs(dest_w - target_w) < 50) and is_fractional_scale:
                 if self.log_queue and not hasattr(self, '_logged_hidpi'):
                    self._logged_hidpi = True
                    msg = f"HiDPI Scaling Trap Detected (Ratio {ratio_w:.2f})! Overriding detected {dest_w}x{dest_h} with Preset {orig_w}x{orig_h}"
                    self.log_queue.put({"time": "WARN", "line_text": msg})
                    try:
                       with open("session_debug.log", "a") as f: f.write(f"{datetime.now()} {msg}\n")
                    except: pass
                 dest_w, dest_h = orig_w, orig_h
        
        if not orig_w or not orig_h: return monitors
        
        if (orig_w, orig_h) == (dest_w, dest_h): return monitors
        
        sx, sy = dest_w / orig_w, dest_h / orig_h
        return [{'left': int(m['left'] * sx), 'top': int(m['top'] * sy),
                 'width': int(m['width'] * sx), 'height': int(m['height'] * sy)} for m in monitors]

    def _images_are_similar(self, img1: Image.Image, img2: Image.Image, similarity: float) -> bool:
        if similarity == 0: return False
        if img1 is None or img2 is None: return False
        if img1.size != img2.size: return False
        diff = ImageChops.difference(img1, img2)
        stat = ImageStat.Stat(diff)
        return sum(stat.mean) < similarity

    def run(self):
        preset = self.config_manager.load_preset()
        if not preset: return

        # Ładowanie parametrów
        self.ocr_scale = preset.get('ocr_scale_factor', 1.0)
        self.text_alignment = preset.get('text_alignment', "None")
        self.save_logs = preset.get('save_logs', False)
        self.subtitle_mode = preset.get('subtitle_mode', 'Full Lines')
        interval = preset.get('capture_interval', 0.5)
        similarity = preset.get('similarity', 5.0)

        self.audio_speed_inc = preset.get('audio_speed_inc', 1.20)

        # Konfiguracja dla matchera
        self.matcher_config = {
            'match_score_short': preset.get('match_score_short', 90),
            'match_score_long': preset.get('match_score_long', 75),
            'match_len_diff_ratio': preset.get('match_len_diff_ratio', 0.25),
            'partial_mode_min_len': preset.get('partial_mode_min_len', 25)
        }

        raw_subtitles = ConfigManager.load_text_lines(preset.get('text_file_path'))
        min_line_len = preset.get('min_line_length', 0)
        precomputed_data = precompute_subtitles(raw_subtitles, min_line_len) if raw_subtitles else ([], {})

        # --- LOAD AREAS ---
        areas_config = preset.get('areas', [])
        monitors = [] # List of rects for unified calc
        
        # If old config (no 'areas'), usage fallback (should be migrated but just in case)
        if not areas_config and preset.get('monitor'):
             raw_monitors = preset.get('monitor', [])
             if isinstance(raw_monitors, dict): raw_monitors = [raw_monitors]
             # Create dummy area objects
             for i, m in enumerate(raw_monitors):
                 if not m: continue
                 areas_config.append({
                     "id": i+1,
                     "type": "manual" if i == 2 else "continuous",
                     "rect": m,
                     "colors": preset.get("subtitle_colors", []) if i==0 else []
                 })

        # Scale areas
        valid_areas = []
        for area in areas_config:
            r = area.get('rect')
            if not r: continue
            
            # Scale rect
            scaled_list = self._scale_monitor_areas([r], preset.get('resolution'))
            if scaled_list:
                area['rect'] = scaled_list[0]
                valid_areas.append(area)

        if not valid_areas: return
        
        monitors = [a['rect'] for a in valid_areas] # For Unified Calculation

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
        audio_dir = preset.get('audio_dir', '')
        audio_ext = preset.get('audio_ext', '.mp3')

        capture_worker = CaptureWorker(self.stop_event, self.img_queue, unified_area, interval)
        capture_worker.start()

        if self.log_queue and self.save_logs:
            self.log_queue.put({"time": "INFO", "line_text": f"Start Reader. Logs enabled."})
        if self.save_logs:
            with open("session_log.txt", "a", encoding='utf-8') as f:
                f.write(f"\n=== SESSION START {datetime.now()} ===\n")
                f.write("Time | Monitor | Capture(ms) | Pre(ms) | OCR(ms) | Match(ms) | Text | MatchResult\n")

        print(f"ReaderThread started.")

        while not self.stop_event.is_set():
            try:
                full_img, t_cap = self.img_queue.get(timeout=0.2)
            except queue.Empty:
                continue

            if self.img_queue.qsize() > 0:
                try:
                    self.img_queue.get_nowait()
                except queue.Empty:
                    pass

            for idx, area_obj in enumerate(valid_areas):
                t_start_proc = time.perf_counter()
                
                area_id = area_obj.get('id', idx)
                area_rect = area_obj.get('rect')
                
                if area_obj.get('type') == 'manual':
                     if area_id not in self.triggered_area_ids:
                         continue
                     self.triggered_area_ids.remove(area_id)
                     # Clear last crop logic for manual might needed?
                     self.last_monitor_crops.pop(idx, None)

                rel_x, rel_y = area_rect['left'] - min_l, area_rect['top'] - min_t
                crop = full_img.crop((rel_x, rel_y, rel_x + area_rect['width'], rel_y + area_rect['height']))

                last_crop = self.last_monitor_crops.get(idx)
                if self._images_are_similar(crop, last_crop, similarity):
                    # print("images are similar")
                    continue
                self.last_monitor_crops[idx] = crop.copy()

                t_pre_start = time.perf_counter()

                # Przekazanie parametru density_threshold + COLORS
                processed, has_content, crop_bbox = preprocess_image(crop, self.config_manager, override_colors=area_obj.get('colors'))

                if not has_content:
                    # print("images has no content")
                    continue

                t_pre = (time.perf_counter() - t_pre_start) * 1000

                t_ocr_start = time.perf_counter()
                text = recognize_text(processed, self.config_manager)

                t_ocr = (time.perf_counter() - t_ocr_start) * 1000

                if not text:
                    # print("images has no text")
                    continue

                if len(text) < 2 or text in self.last_ocr_texts:
                    # print("last ocr filter")
                    continue

                if has_content and crop_bbox and self.debug_queue:
                    abs_x = area_rect['left'] + crop_bbox[0]
                    abs_y = area_rect['top'] + crop_bbox[1]

                    abs_w = crop_bbox[2] - crop_bbox[0]
                    abs_h = crop_bbox[3] - crop_bbox[1]
                    self.debug_queue.put(('overlay', (abs_x, abs_y, abs_w, abs_h)))

                self.last_ocr_texts.append(text)

                t_match_start = time.perf_counter()
                # Przekazanie matcher_config
                match = find_best_match(text, precomputed_data, self.subtitle_mode,
                                        last_index=self.last_matched_idx,
                                        matcher_config=self.matcher_config)
                t_match = (time.perf_counter() - t_match_start) * 1000

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
                    if self.save_logs:
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
                        print(f"Match: {score}% -> Line {idx_match}")
                        self.recent_match_indices.append(idx_match)

                        audio_path = os.path.join(audio_dir, f"output1 ({idx_match + 1}){audio_ext}")

                        q_size = self.audio_queue.qsize()
                        speed_multiplier = 1.0

                        if q_size > 0:
                            speed_multiplier = self.audio_speed_inc

                        self.audio_queue.put((audio_path, speed_multiplier))

        capture_worker.join()