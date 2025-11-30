import threading
import time
import os
import re
import queue
from collections import deque
from datetime import datetime
from typing import Optional, Tuple, Dict, Any, List

from app.capture import capture_region
from app.ocr import preprocess_image, recognize_text
from app.matcher import find_best_match, precompute_subtitles
from app.config_manager import ConfigManager


class CaptureWorker(threading.Thread):
    """
    Wątek PRODUCENTA: Odpowiedzialny wyłącznie za wykonywanie zrzutów ekranu.

    Działa niezależnie od OCR, aby zapewnić stały interwał próbkowania.
    Zrzuty trafiają do kolejki. Jeśli kolejka jest pełna (OCR nie nadąża),
    najstarsze klatki są porzucane, aby zachować niskie opóźnienie.
    """

    def __init__(self, stop_event: threading.Event, img_queue: queue.Queue,
                 unified_area: Dict[str, int], interval: float):
        super().__init__(daemon=True)
        self.name = "CaptureWorker"
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
                    # Jeśli kolejka pełna, usuń najstarszy element (drop frame)
                    if self.img_queue.full():
                        try:
                            self.img_queue.get_nowait()
                        except queue.Empty:
                            pass

                    self.img_queue.put((full_img, t_cap), block=False)
                except queue.Full:
                    pass

            # Utrzymanie stałego FPS (interwału)
            elapsed = time.monotonic() - loop_start
            time.sleep(max(0, self.interval - elapsed))


class ReaderThread(threading.Thread):
    """
    Wątek KONSUMENTA: Pobiera zrzuty z kolejki, wykonuje OCR i dopasowuje tekst.
    Zarządza również odtwarzaniem dźwięku po znalezieniu dopasowania.
    """

    def __init__(self, config_path: str, regex_template: str, app_settings: Dict[str, Any],
                 stop_event: threading.Event, audio_queue,
                 target_resolution: Optional[Tuple[int, int]],
                 log_queue=None,
                 auto_remove_names: bool = True):
        super().__init__(daemon=True)
        self.name = "ReaderThread"
        self.config_path = config_path
        self.regex_template = regex_template
        self.app_settings = app_settings
        self.stop_event = stop_event
        self.audio_queue = audio_queue
        self.log_queue = log_queue
        self.target_resolution = target_resolution
        self.auto_remove_names = auto_remove_names

        # Bufory historii, aby nie powtarzać tych samych linii
        self.recent_match_indices = deque(maxlen=10)
        self.last_ocr_texts = deque(maxlen=5)

        self.last_matched_idx = -1
        self.area3_expiry_time = 0.0
        self.img_queue = None
        self.combined_regex = ""

        # Ustawienia domyślne (nadpisywane przez preset)
        self.ocr_scale = 1.0
        self.subtitle_mode = 'Full Lines'
        self.ocr_grayscale = app_settings.get('ocr_grayscale', False)
        self.ocr_contrast = app_settings.get('ocr_contrast', False)

    def trigger_area_3(self, duration: float = 2.0):
        """Aktywuje tymczasowy obszar (np. na adnotacje w grze)."""
        self.area3_expiry_time = time.time() + duration
        if self.log_queue:
            self._log_system_msg(f"Aktywowano Obszar 3 na {duration}s")

    def _prepare_regex(self, names_path: str) -> str:
        """Kompiluje regex z listą imion, jeśli są dostępne."""
        names = ConfigManager.load_text_lines(names_path)
        if not names or "{NAMES}" not in self.regex_template:
            return self.regex_template.replace("{NAMES}", r"\0\Z")

        # Escape imion, by nie psuły regexa
        escaped_names = [re.escape(n) for n in names]
        pattern = "|".join(escaped_names)
        return self.regex_template.replace("{NAMES}", f"({pattern})")

    def _scale_monitor_areas(self, monitors: List[Dict], original_res_str: str) -> List[Dict]:
        """Przelicza współrzędne obszarów, jeśli rozdzielczość gry jest inna niż podczas konfiguracji."""
        if not self.target_resolution or not original_res_str:
            return monitors
        try:
            orig_w, orig_h = map(int, original_res_str.lower().split('x'))
            target_w, target_h = self.target_resolution

            if (orig_w, orig_h) == (target_w, target_h):
                return monitors

            sx = target_w / orig_w
            sy = target_h / orig_h

            return [{
                'left': int(m['left'] * sx),
                'top': int(m['top'] * sy),
                'width': int(m['width'] * sx),
                'height': int(m['height'] * sy)
            } for m in monitors]
        except Exception as e:
            print(f"Błąd skalowania obszarów: {e}")
            return monitors

    def _log_system_msg(self, msg: str):
        self.log_queue.put({
            "time": datetime.now().strftime('%H:%M:%S'),
            "ocr": "SYSTEM",
            "match": None,
            "line_text": msg,
            "stats": {}
        })

    def run(self):
        preset = ConfigManager.load_preset(self.config_path)
        if not preset:
            print("Błąd: Nie można załadować profilu.")
            return

        # 1. Konfiguracja
        self.ocr_scale = preset.get('ocr_scale_factor', 1.0)
        self.subtitle_mode = preset.get('subtitle_mode', 'Full Lines')
        interval = preset.get('capture_interval', 0.5)
        audio_dir = preset.get('audio_dir', '')

        raw_subtitles = ConfigManager.load_text_lines(preset.get('text_file_path'))
        if not raw_subtitles:
            print("Błąd: Brak pliku z napisami.")
            return

        print(f"Lektor startuje. Liczba linii: {len(raw_subtitles)}. Tryb: {self.subtitle_mode}")

        # 2. Precomputing (hashowanie napisów)
        precomputed_data = precompute_subtitles(raw_subtitles)
        self.combined_regex = self._prepare_regex(preset.get('names_file_path'))

        # 3. Przygotowanie obszarów ekranu
        raw_monitors = preset.get('monitor', [])
        if isinstance(raw_monitors, dict): raw_monitors = [raw_monitors]
        monitors = [m for m in raw_monitors if m]
        monitors = self._scale_monitor_areas(monitors, preset.get('resolution'))

        if not monitors:
            print("Błąd: Brak zdefiniowanych obszarów ekranu.")
            return

        # 4. Obliczenie wspólnego obszaru (bounding box) dla wszystkich monitorów
        #    Dzięki temu robimy jeden zrzut ekranu zamiast kilku mniejszych (szybciej w MSS/Wayland)
        min_l = min(m['left'] for m in monitors)
        min_t = min(m['top'] for m in monitors)
        max_r = max(m['left'] + m['width'] for m in monitors)
        max_b = max(m['top'] + m['height'] for m in monitors)

        unified_area = {
            'left': min_l, 'top': min_t,
            'width': max_r - min_l, 'height': max_b - min_t
        }

        queue_size = len(monitors) + 1
        self.img_queue = queue.Queue(maxsize=queue_size)

        # 5. Uruchomienie producenta (CaptureWorker)
        capture_worker = CaptureWorker(self.stop_event, self.img_queue, unified_area, interval)
        capture_worker.start()

        # 6. Główna pętla przetwarzania
        while not self.stop_event.is_set():
            try:
                full_img, t_cap = self.img_queue.get(timeout=0.2)
            except queue.Empty:
                continue

            # Iteracja po zdefiniowanych obszarach (Dialog, Wybory, Adnotacje)
            for idx, area in enumerate(monitors):
                # Obsługa obszaru tymczasowego (np. index 2)
                if idx == 2 and time.time() > self.area3_expiry_time:
                    continue

                # Wycięcie konkretnego obszaru ze zrzutu zbiorczego
                rel_x = area['left'] - min_l
                rel_y = area['top'] - min_t
                crop = full_img.crop((rel_x, rel_y, rel_x + area['width'], rel_y + area['height']))

                # Przetwarzanie obrazu i OCR
                t1 = time.perf_counter()
                processed_img = preprocess_image(crop, self.ocr_scale, self.ocr_grayscale, self.ocr_contrast)
                text = recognize_text(processed_img, self.combined_regex, self.auto_remove_names)
                t_ocr = (time.perf_counter() - t1) * 1000

                if not text or len(text) < 2:
                    continue

                if text in self.last_ocr_texts:
                    continue
                self.last_ocr_texts.append(text)

                # Dopasowanie tekstu
                t2 = time.perf_counter()
                match = find_best_match(text, precomputed_data, self.subtitle_mode, last_index=self.last_matched_idx)
                t_match = (time.perf_counter() - t2) * 1000

                # Logowanie
                if self.log_queue:
                    matched_text = raw_subtitles[match[0]] if match else ""
                    self.log_queue.put({
                        "time": datetime.now().strftime('%H:%M:%S'),
                        "ocr": text,
                        "match": match,
                        "line_text": matched_text,
                        "stats": {"monitor": idx + 1, "cap_ms": t_cap, "ocr_ms": t_ocr, "match_ms": t_match}
                    })

                # Odtwarzanie audio
                if match:
                    idx_match, score = match
                    self.last_matched_idx = idx_match

                    if idx_match not in self.recent_match_indices:
                        print(f" >>> MATCH ({score}%): {raw_subtitles[idx_match]}")
                        self.recent_match_indices.append(idx_match)

                        # Oczekiwany format pliku audio: output1 (numer_linii).ogg
                        audio_file = os.path.join(audio_dir, f"output1 ({idx_match + 1}).ogg")
                        self.audio_queue.put(audio_file)

        capture_worker.join()