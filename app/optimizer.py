from PIL import Image
import itertools
from collections import Counter
from typing import Tuple, List, Dict, Any, Optional
import multiprocessing

from app.ocr import preprocess_image, recognize_text
from app.matcher import find_best_match, precompute_subtitles, MATCH_MODE_FULL, MATCH_MODE_STARTS, MATCH_MODE_PARTIAL
from app.config_manager import ConfigManager, PresetConfig

# Global variables for worker processes to avoid repeated serialization
_worker_crop = None
_worker_db = None

def _init_worker(crop, db):
    global _worker_crop, _worker_db
    _worker_crop = crop
    _worker_db = db

def _evaluate_worker(args):
    """
    Worker function for parallel settings evaluation.
    args: (preset_obj, match_mode)
    """
    preset, match_mode = args
    mock_cfg = OptimizerConfigManager(preset)

    try:
        # We use the globally stored _worker_crop and _worker_db for efficiency
        processed_img, has_content, bbox = preprocess_image(_worker_crop.copy(), mock_cfg, area_config=preset)
        if not has_content:
            return 0, None

        ocr_text = recognize_text(processed_img, mock_cfg)
        if not ocr_text or len(ocr_text.strip()) < 2:
            return 0, None

        match_result = find_best_match(ocr_text, _worker_db, mode=match_mode, matcher_config=mock_cfg)
    except Exception:
        return 0, None

    if not match_result:
        return 0, bbox

    _, score = match_result

    from app.text_processing import clean_text, smart_remove_name
    ocr_no_name = smart_remove_name(ocr_text)
    cleaned_ocr = clean_text(ocr_no_name)
    
    if match_mode == MATCH_MODE_FULL:
        if cleaned_ocr in _worker_db[1]:
            score = 101
    elif match_mode == MATCH_MODE_STARTS:
        try:
            exact_map_keys = list(_worker_db[1].keys())
        except Exception:
            exact_map_keys = []
        for key in exact_map_keys:
            if not key:
                continue
            if cleaned_ocr.startswith(key) or key.startswith(cleaned_ocr):
                score = 101
                break
    
    return score, bbox


class OptimizerConfigManager(ConfigManager):
    """
    Specjalna wersja ConfigManager używana podczas optymalizacji.
    Używa obiektu PresetConfig w pamięci zamiast ładować z pliku.
    """
    def __init__(self, preset: 'PresetConfig'):
        self.settings = {} 
        self.preset_path = None
        self.display_resolution = None
        self.preset_cache = preset

    def _get_preset_obj(self):
        return self.preset_cache

    def load_preset(self, path=None):
        return self.preset_cache

    def save_preset(self, path, obj):
        pass

class SettingsOptimizer:
    def __init__(self, original_config_manager: ConfigManager = None):
        self.base_preset = PresetConfig()
        if original_config_manager:
            loaded_preset = original_config_manager.load_preset()
            import copy
            self.base_preset = copy.deepcopy(loaded_preset)

    def _extract_dominant_colors(self, image: Image.Image, num_colors: int = 3) -> List[str]:
        img_small = image.copy()
        img_small.thumbnail((100, 100))
        img_small = img_small.convert("RGB")
        pixels = list(img_small.getdata())
        valid_pixels = [p for p in pixels if (0.299*p[0] + 0.587*p[1] + 0.114*p[2]) > 40]
        if not valid_pixels: return ["#FFFFFF"]
        counts = Counter(valid_pixels)
        return [f"#{r:02x}{g:02x}{b:02x}" for (r, g, b), _ in counts.most_common(num_colors)]

    def optimize(self, 
                 images: List[Image.Image], 
                 rough_area: Tuple[int, int, int, int], 
                 subtitle_db: List[str],
                 match_mode: str = MATCH_MODE_FULL,
                 initial_color: str = None,
                 progress_callback=None,
                 stop_event: multiprocessing.Event = None) -> Dict[str, Any]:
        """
        Znajduje optymalne ustawienia OCR i matchingu dla zadanego wycinka ekranu.
        Wykorzystuje jeden Pool procesów dla wszystkich etapów.
        """
        if not images: return {}
        if not isinstance(images, list):
            images = [images]
        if stop_event and stop_event.is_set(): return {"score": 0, "settings": None, "optimized_area": rough_area}
        
        first_image = images[0]
        rx, ry, rw, rh = rough_area

        def create_crop(img):
            cx, cy = max(0, rx), max(0, ry)
            cw, ch = min(rw, img.size[0] - cx), min(rh, img.size[1] - cy)
            return img.crop((cx, cy, cx+cw, cy+ch)) if cw > 0 and ch > 0 else None

        crop0 = create_crop(first_image)
        if not crop0: return {"score": 0, "settings": {}, "optimized_area": rough_area, "error": "Invalid area or empty crop"}

        precomputed_db = precompute_subtitles(subtitle_db)
        candidate_colors = [initial_color] if initial_color else sorted(list(set(self._extract_dominant_colors(crop0)) | {"#FFFFFF"}))
            
        candidates = []
        params = {
            "color_tolerances": range(1, 30, 2),
            "thickenings": [0, 1],
            "contrasts": [round(x * 0.4, 1) for x in range(0, 6)],
            "brightness_threshold": range(150, 255, 10)
        }

        import copy
        for color, tol, thick, contrast in itertools.product(candidate_colors, params["color_tolerances"], params["thickenings"], params["contrasts"]):
            s = copy.deepcopy(self.base_preset)
            s._setting_mode, s.auto_remove_names, s.colors = "color", True, [color]
            s.color_tolerance, s.text_thickening = tol, thick
            setattr(s, 'ocr_scale_factor', 1.0) # Optimization evaluates at 1.0 scale
            s.text_color_mode, s.brightness_threshold, s.contrast, s.subtitle_mode = "Light", 200, contrast, match_mode
            candidates.append(s)
        
        for mode, thick, contrast, bright in itertools.product(["Light", "Dark"], params["thickenings"], params["contrasts"], params["brightness_threshold"]):
            s = copy.deepcopy(self.base_preset)
            s._setting_mode, s.auto_remove_names, s.colors = "brightness", True, []
            s.text_color_mode, s.text_thickening = mode, thick
            setattr(s, 'ocr_scale_factor', 1.0)
            s.brightness_threshold, s.contrast, s.subtitle_mode = bright, contrast, match_mode
            candidates.append(s)

        best_amount = 100
        total_steps = len(candidates) + (len(images) - 1) * best_amount
        checked, best_score = 0, 0

        def update_progress(val, score=None):
            nonlocal checked, best_score
            checked += val
            if score is not None and score > best_score: best_score = score
            if progress_callback: progress_callback(checked, total_steps, best_score)

        def sort_key(item):
            data, s, _ = item
            score = data if isinstance(data, (int, float)) else (sum(data)/len(data))
            prio = 1 if s._setting_mode == 'color' else 0
            if s._setting_mode == 'color': return (score, prio, -s.color_tolerance, -(s.text_thickening+1), -s.contrast)
            return (score, prio, s.brightness_threshold, -s.contrast, 0)

        cpu_count = multiprocessing.cpu_count()
        with multiprocessing.Pool(processes=cpu_count) as pool:
            # Stage 1
            pool.starmap(_init_worker, [(crop0, precomputed_db)] * cpu_count)
            ranked = []
            for i, (score, bbox) in enumerate(pool.imap(_evaluate_worker, [(s, match_mode) for s in candidates])):
                if stop_event and stop_event.is_set():
                    pool.terminate(); return {"score": 0, "settings": None, "optimized_area": rough_area}
                update_progress(1, score)
                if score > 50: 
                    ranked.append((score, candidates[i], bbox))

            ranked.sort(key=sort_key, reverse=True)
            finalists = [([score], s, bbox) for score, s, bbox in ranked[:best_amount]]

            # Stage 2
            rejected = []
            for idx, img in enumerate(images[1:], 1):
                if stop_event and stop_event.is_set():
                    pool.terminate(); return {"score": 0, "settings": None, "optimized_area": rough_area}
                
                crop_n = create_crop(img)
                if not crop_n: 
                    update_progress(best_amount); continue
                pool.starmap(_init_worker, [(crop_n, precomputed_db)] * cpu_count)
                
                results = pool.map(_evaluate_worker, [(f[1], match_mode) for f in finalists])
                next_round = []
                for i, (score, bbox) in enumerate(results):
                    scores, s, _ = finalists[i]
                    update_progress(1, score)
                    if score > 50: next_round.append((scores + [score], s, bbox))
                
                if not next_round:
                    rejected.append({"index": idx+1, "score": 0}); continue
                next_round.sort(key=sort_key, reverse=True)
                finalists = next_round

            if finalists:
                finalists.sort(key=sort_key, reverse=True)
                scores, s, _ = finalists[0]
                
                # Collect all bboxes from the best candidate across all successful frames
                all_bboxes = []
                # Re-evaluate the best settings on all images to get bboxes
                # (Or we could have tracked them, but re-evaluating on a few images is safer and fast)
                final_score = sum(scores)/len(scores)
                
                for img in images:
                    c = create_crop(img)
                    if c:
                        sc, bb = self._evaluate_settings(c, s, precomputed_db, match_mode)
                        if sc > 50 and bb:
                            all_bboxes.append(bb)
                
                refined_area = self._apply_area_refinement(first_image.size, rough_area, all_bboxes)
                return {"score": final_score, "settings": s, "optimized_area": refined_area, "rejected_screens": rejected}

        if finalists: # From survivors in Stage 1 if Stage 2 didn't run
            scores, s, bbox = finalists[0]
            # If only Stage 1 ran, we just have one bbox
            refined_area = self._apply_area_refinement(first_image.size, rough_area, [bbox] if bbox else [])
            return {"score": scores[0], "settings": s, "optimized_area": refined_area, "rejected_screens": []}
        return {"score": 0, "settings": None, "optimized_area": rough_area}

    def _apply_area_refinement(self, screen_size, rough_area, bboxes: List[Tuple[int, int, int, int]]):
        """
        Calculates the union of all bboxes, applies padding, and constrains to rough_area and screen.
        bboxes are relative to rough_area.
        """
        valid_bboxes = [b for b in bboxes if b]
        if not valid_bboxes: 
            return rough_area
            
        rx, ry, rw, rh = rough_area
        sw, sh = screen_size
        
        # Calculate Union (Aggregate Area)
        # bbox format from ocr.py (preprocess_image): (left, top, right, bottom)
        min_l = min(b[0] for b in valid_bboxes)
        min_t = min(b[1] for b in valid_bboxes)
        max_r = max(b[2] for b in valid_bboxes)
        max_b = max(b[3] for b in valid_bboxes)
        
        agg_w = max_r - min_l
        agg_h = max_b - min_t
        
        # Absolute coordinates of the union
        abs_l = rx + min_l
        abs_t = ry + min_t
        
        # Apply padding: 10% horizontal, 5% vertical of aggregate size
        margin_h = agg_w * 0.10
        margin_v = agg_h * 0.05
        
        final_x = int(abs_l - margin_h)
        final_y = int(abs_t - margin_v)
        final_w = int(agg_w + margin_h * 2)
        final_h = int(agg_h + margin_v * 2)
        
        # Constraint 1: Keep within screen boundaries
        if final_x < 0:
            final_w += final_x # Reduce width if x was negative
            final_x = 0
        if final_y < 0:
            final_h += final_y
            final_y = 0
            
        if final_x + final_w > sw:
            final_w = sw - final_x
        if final_y + final_h > sh:
            final_h = sh - final_y
            
        # Constraint 2: Must be contained within the original rough_area
        # final_x should be at least rx, but not more than rx + rw
        # We also need to be careful about not shrinking it too much if the detected text was outside? 
        # Actually, the detection is performed ON the crop, so it's always within rough_area relative (0,0,rw,rh).
        
        # Re-constrain to rough_area just in case of over-padding
        final_x = max(rx, final_x)
        final_y = max(ry, final_y)
        
        # Adjust width/height if we moved final_x/y
        if final_x + final_w > rx + rw:
            final_w = (rx + rw) - final_x
        if final_y + final_h > ry + rh:
            final_h = (ry + rh) - final_y
            
        # Ensure non-negative dimensions
        final_w = max(0, final_w)
        final_h = max(0, final_h)
        
        return (final_x, final_y, final_w, final_h)

    def _evaluate_settings(self, crop, preset, db, match_mode=MATCH_MODE_FULL):
        mock = OptimizerConfigManager(preset)
        try:
            processed, has, bbox = preprocess_image(crop.copy(), mock, area_config=preset)
            if not has: return 0, None
            text = recognize_text(processed, mock)
            if not text or len(text.strip()) < 2: return 0, None
            res = find_best_match(text, db, mode=match_mode, matcher_config=mock)
            return (res[1] if res else 0), bbox
        except Exception: return 0, None
