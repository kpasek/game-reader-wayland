import threading
import time
import os
import queue
import copy
from collections import deque
from datetime import datetime
from typing import Optional, Tuple, Dict, List
# ImageChops jest wykorzystywany w funkcji _images_are_similar, a ImageStat w tej samej funkcji.
from PIL import Image, ImageChops, ImageStat

from app.capture import capture_region
from app.ocr import preprocess_image, recognize_text
from app.matcher import find_best_match, precompute_subtitles
from app.config_manager import ConfigManager


class AreaConfigContext:
    """
    Pomocnicza klasa udająca ConfigManager, ale zwracająca ustawienia
    specyficzne dla danego obszaru (połączone z globalnymi).
    """
    def __init__(self, effective_preset_data):
        self.preset_data = effective_preset_data
        self.settings = effective_preset_data

    def load_preset(self, path=None):
        return self.preset_data


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
            if not getattr(self, '_logged_fail', False):
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
        self.text_alignment = "None"
        self.save_logs = False

        self.matcher_config = {}
        self.audio_speed_inc = 1.2

        text_color_mode = config_manager.settings.get('text_color_mode', 'Light')
        self.text_color = text_color_mode

        self.ocr_binarize = True

        self.current_unified_area = {'left': 0, 'top': 0, 'width': 0, 'height': 0}

    def trigger_area(self, area_id: int):
        """Aktywuje jednorazowe pobranie i przetworzenie Obszaru o danym ID (manual/triggered)."""
        self.triggered_area_ids.add(area_id)

    def toggle_continuous_area(self, area_id: int):
        """Włącza lub wyłącza przetwarzanie stałego obszaru (continuous)."""
        if area_id == 1:
            return  # Obszar 1 jest zawsze włączony

        if area_id in self.enabled_continuous_areas:
            self.enabled_continuous_areas.remove(area_id)
            if self.log_queue:
                self.log_queue.put({"time": "INFO", "line_text": f"Area #{area_id} deactivated."})
        else:
            self.enabled_continuous_areas.add(area_id)
            if self.log_queue:
                self.log_queue.put({"time": "INFO", "line_text": f"Area #{area_id} activated."})
        
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

    def _scale_monitor_areas(self, monitors: List[Dict]) -> List[Dict]:
        """Delegate scaling to central utilities (4K -> physical)."""
        try:
            # Determine dest resolution similarly to other code paths
            if not hasattr(self, '_physical_res') or not self._physical_res:
                from app.capture import capture_fullscreen
                try:
                    img = capture_fullscreen()
                    if img:
                        self._physical_res = img.size
                except Exception:
                    pass

            if hasattr(self, '_physical_res') and self._physical_res:
                dest_w, dest_h = self._physical_res
            elif self.target_resolution:
                dest_w, dest_h = self.target_resolution
            else:
                dest_w, dest_h = 3840, 2160

            from app import scale_utils
            return scale_utils.scale_list_to_physical(monitors, dest_w, dest_h)
        except Exception:
            return monitors
                 
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
        interval = self.config_manager.capture_interval
        similarity = self.config_manager.similarity
        min_line_len = preset.get('min_line_length', 0)

        self.audio_speed_inc = self.config_manager.audio_speed_inc

        # Konfiguracja dla matchera
        self.matcher_config = {
            'match_score_short': self.config_manager.match_score_short,
            'match_score_long': self.config_manager.match_score_long,
            'match_len_diff_ratio': self.config_manager.match_len_diff_ratio,
            'partial_mode_min_len': self.config_manager.partial_mode_min_len
        }

        raw_subtitles = ConfigManager.load_text_lines(preset.get('text_file_path'))
        precomputed_data = precompute_subtitles(raw_subtitles, min_line_len) if raw_subtitles else ([], {})

        # --- LOAD AREAS ---
        # Centralne skalowanie: pobierz preset i przeskaluj recty z 4K do fizycznej rozdzielczości
        from app.capture import capture_fullscreen
        dest_w = dest_h = None
        try:
            if not hasattr(self, '_physical_res') or not self._physical_res:
                img_tmp = capture_fullscreen()
                if img_tmp:
                    self._physical_res = img_tmp.size
        except Exception:
            pass

        if hasattr(self, '_physical_res') and self._physical_res:
            dest_w, dest_h = self._physical_res
        elif self.target_resolution:
            dest_w, dest_h = self.target_resolution
        else:
            dest_w, dest_h = 3840, 2160

        # Use ConfigManager helper to fetch preset with areas already scaled to dest resolution
        preset_for_display = self.config_manager.get_preset_for_resolution(None, (dest_w, dest_h))
        areas_config = copy.deepcopy(preset_for_display.get('areas', []))
        valid_areas = areas_config

        if not valid_areas:
            if self.log_queue:
                self.log_queue.put({"time": "ERROR", "line_text": "Nie znaleziono aktywnych obszarów. Sprawdź konfigurację."})
            return
        
        
        # Initialize enabled continuous areas from config
        self.enabled_continuous_areas = set()
        for area in valid_areas:
            if area.get('type') == 'continuous' and area.get('enabled', False):
                self.enabled_continuous_areas.add(area.get('id'))

        # Skaluje recty z kanonicznego 4K do aktualnej rozdzielczości obrazu
        try:
            # If rects already look like physical coordinates (fit within dest), skip scaling.
            dest_w, dest_h = dest_w, dest_h
            rects = [a['rect'] for a in valid_areas]
            need_scale = False
            for r in rects:
                if not r: continue
                try:
                    # If any rect exceeds destination bounds, assume it's in 4K and needs scaling
                    if (r.get('left', 0) < 0 or r.get('top', 0) < 0 or
                        r.get('left', 0) + r.get('width', 0) > dest_w or
                        r.get('top', 0) + r.get('height', 0) > dest_h):
                        need_scale = True
                        break
                except Exception:
                    need_scale = True
                    break

            if need_scale:
                scaled_rects = self._scale_monitor_areas(rects)
                for i, a in enumerate(valid_areas):
                    a['rect'] = scaled_rects[i]
            else:
                # Rects already in physical coords; leave as-is
                pass
        except Exception:
            # Fallback: użyj oryginalnych rectów jeżeli skalowanie nie powiedzie się
            pass

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

        capture_worker = CaptureWorker(self.stop_event, self.img_queue, unified_area, interval, log_queue=self.log_queue)
        capture_worker.start()

        if self.log_queue:
             self.log_queue.put({"time": "INFO", "line_text": f"Reader started. Areas: {len(valid_areas)}. Logging enabled."})

        if self.save_logs:
            if self.log_queue: self.log_queue.put({"time": "INFO", "line_text": f"Saving logs to session_log.txt"})
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
                area_type = area_obj.get('type', 'manual')

                # Logika włączania/wyłączania obszarów
                if area_type == 'manual':
                     if area_id not in self.triggered_area_ids:
                         continue
                     self.triggered_area_ids.remove(area_id)
                     # Clear last crop logic for manual might needed?
                     self.last_monitor_crops.pop(idx, None)
                elif area_type == 'continuous':
                    # Obszar 1 zawsze aktywny, inne muszą być włączone
                    if area_id != 1 and area_id not in self.enabled_continuous_areas:
                        continue

                rel_x, rel_y = area_rect['left'] - min_l, area_rect['top'] - min_t
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
                    continue
                self.last_monitor_crops[idx] = crop.copy()

                # --- Prepare Context for Area ---
                area_settings = area_obj.get('settings', {}).copy()
                # Legacy fallback for colors
                if 'subtitle_colors' not in area_settings and 'colors' in area_obj:
                     area_settings['subtitle_colors'] = area_obj['colors']
                
                merged_preset = preset.copy()
                merged_preset.update(area_settings)

                area_ctx = AreaConfigContext(merged_preset)
                from app.matcher import MATCH_MODE_FULL
                current_subtitle_mode = merged_preset.get('subtitle_mode', MATCH_MODE_FULL)

                t_pre_start = time.perf_counter()

                # Używamy area_ctx zamiast globalnego configa. override_colors nie jest już potrzebne
                # bo settings w kontekście ma już poprawne kolory.
                processed, has_content, crop_bbox = preprocess_image(crop, area_ctx)

                if not has_content:
                    continue

                t_pre = (time.perf_counter() - t_pre_start) * 1000

                t_ocr_start = time.perf_counter()
                text = recognize_text(processed, area_ctx)

                t_ocr = (time.perf_counter() - t_ocr_start) * 1000

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

                t_match_start = time.perf_counter()
                # Przekazanie dynamicznego trybu dopasowania (Area Specific)
                match = find_best_match(text, precomputed_data, current_subtitle_mode,
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
                        if not os.path.exists(audio_path):
                            print(f"Audio file not found: {audio_path}")

                        q_size = self.audio_queue.qsize()
                        speed_multiplier = 1.0

                        if q_size > 0:
                            speed_multiplier = self.audio_speed_inc

                        self.audio_queue.put((audio_path, speed_multiplier))

        capture_worker.join()