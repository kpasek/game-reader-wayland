from PIL import Image
import itertools
from collections import Counter
from typing import Tuple, List, Dict, Any, Optional

from app.ocr import preprocess_image, recognize_text
from app.matcher import find_best_match, precompute_subtitles, MATCH_MODE_FULL, MATCH_MODE_STARTS, MATCH_MODE_PARTIAL
from app.config_manager import ConfigManager, PresetConfig

class OptimizerConfigManager(ConfigManager):
    """
    Specjalna wersja ConfigManager używana podczas optymalizacji.
    Używa obiektu PresetConfig w pamięci zamiast ładować z pliku.
    """
    def __init__(self, preset: 'PresetConfig'):
        # Inicjalizujemy bez ładowania konfigu aplikacji
        self.settings = {} 
        self.preset_path = None
        self.display_resolution = None
        self.preset_cache = preset

    def _get_preset_obj(self):
        return self.preset_cache

    def load_preset(self, path=None):
        return self.preset_cache

    def save_preset(self, path, obj):
        pass # Nie zapisujemy podczas optymalizacji

class SettingsOptimizer:
    def __init__(self, original_config_manager: ConfigManager = None):
        # Use simple object to hold base candidates. We will copy it and adjust.
        self.base_preset = PresetConfig()
        if original_config_manager:
            loaded_preset = original_config_manager.load_preset()
            import copy
            self.base_preset = copy.deepcopy(loaded_preset)

    def _extract_dominant_colors(self, image: Image.Image, num_colors: int = 3) -> List[str]:
        # ... no changes here ...
        # (Rest of _extract_dominant_colors omitted for brevity)
        """
        Znajduje domuniujące kolory na obrazie, ignorując ciemne tło (prawdopodobnie tło gry).
        Zwraca listę kolorów w formacie HEX (np. ["#FFFFFF", "#FF0000"]).
        """
        # 1. Zmniejszamy obraz dla wydajności
        img_small = image.copy()
        img_small.thumbnail((100, 100))
        img_small = img_small.convert("RGB") # Upewniamy się, że mamy RGB
        
        pixels = list(img_small.getdata())
        
        # 2. Filtrowanie ciemnych pikseli (tła)
        # Przyjmujemy próg luminancji, poniżej którego uznajemy kolor za tło
        valid_pixels = []
        for r, g, b in pixels:
            # Wzór na luminancję: 0.299R + 0.587G + 0.114B
            luminance = 0.299 * r + 0.587 * g + 0.114 * b
            if luminance > 40: # Próg odcięcia tła (eksperymentalnie dobrany)
                valid_pixels.append((r, g, b))
        
        # Jeśli po filtrowaniu nic nie zostało, zwracamy tylko biały
        if not valid_pixels:
            return ["#FFFFFF"]
            
        # 3. Zliczanie najczęstszych kolorów
        counts = Counter(valid_pixels)
        top_colors = counts.most_common(num_colors)
        
        # 4. Konwersja na HEX
        hex_colors = []
        for (r, g, b), _ in top_colors:
            # Formatowanie hex stringa
            hex_c = f"#{r:02x}{g:02x}{b:02x}"
            hex_colors.append(hex_c)
            
        return hex_colors


    def optimize(self, 
                 images: List[Image.Image], 
                 rough_area: Tuple[int, int, int, int], 
                 subtitle_db: List[str],
                 match_mode: str = MATCH_MODE_FULL,
                 initial_color: str = None,
                 progress_callback=None) -> Dict[str, Any]:
        """
        Znajduje optymalne ustawienia OCR i matchingu dla zadanego wycinka ekranu (rough_area)
        i bazy napisów.
        
        Args:
            images: Pojedynczy obraz PIL.Image lub lista obrazów [PIL.Image].
                    Jeśli podano listę, optymalizacja odbywa się wieloetapowo.
        """
            
        if not images:
            return {}

        first_image = images[0]
        rx, ry, rw, rh = rough_area

        # Przygotowanie funkcji pomocniczej do cropowania
        def create_crop(img):
            cx = max(0, rx); cy = max(0, ry)
            cw = min(rw, img.size[0] - cx); ch = min(rh, img.size[1] - cy)
            if cw <= 0 or ch <= 0: return None
            return img.crop((cx, cy, cx+cw, cy+ch))

        crop0 = create_crop(first_image)
        if not crop0:
            return {"error": "Invalid area", "score": 0, "settings": {}, "optimized_area": rough_area}

        # 2. Przygotowanie bazy napisów (raz na całą optymalizację)
        precomputed_db = precompute_subtitles(subtitle_db)

        # 3. Wykrywanie potencjalnych kolorów napisów (tylko na pierwszym zrzucie)
        detected_colors = self._extract_dominant_colors(crop0, num_colors=3)
        # Jeśli użytkownik wybrał kolor, używamy tylko tego koloru jako kandydata
        if initial_color:
            candidate_colors_list = [initial_color]
        else:
            candidate_colors = set(detected_colors)
            candidate_colors.add("#FFFFFF")
            candidate_colors_list = sorted(list(candidate_colors))
            
        candidates = []

        params = {
            "color_tolerances": range(1, 30, 1),
            "thickenings": [0, 1],
            "contrasts": [round(x * 0.2, 2) for x in range(0, 11)],
            "brightness_threshold": range(150, 255, 2)
        }

        import copy
        # Generujemy pełną listę wszystkich kombinacji ustawień do sprawdzenia
        # Branch A: Color-based
        for color in candidate_colors_list:
            for tol, thick, contrast in itertools.product(params["color_tolerances"], params["thickenings"], params["contrasts"]):
                s = copy.deepcopy(self.base_preset)
                # Attach metadata for sorting/reporting
                s._setting_mode = "color" 
                s.auto_remove_names = True
                s.colors = [color]
                s.color_tolerance = tol
                s.text_thickening = thick
                s.ocr_scale_factor = 1.0
                s.text_color_mode = "Light" 
                s.brightness_threshold = 200 
                s.contrast = contrast
                s.subtitle_mode = match_mode  # Zastosuj wybrany tryb
                candidates.append(s)
        
        # Branch B: Brightness Mode (Light/Dark/Mixed)
        for mode, thick in itertools.product(["Light", "Dark"], params["thickenings"]):
            for contrast, brightness in itertools.product(params["contrasts"], params["brightness_threshold"]):
                s = copy.deepcopy(self.base_preset)
                s._setting_mode = "brightness"
                s.auto_remove_names = True
                s.colors = []
                s.text_color_mode = mode
                s.text_thickening = thick
                s.ocr_scale_factor = 1.0
                s.brightness_threshold = brightness
                s.contrast = contrast
                s.subtitle_mode = match_mode  # Zastosuj wybrany tryb
                candidates.append(s)


        # ETAP 1: Ewaluacja na pierwszym obrazie
        survivors = []
        best_score_st1 = 0
        best_settings_st1 = None
        best_candidates_amount = 100

        ranked_candidates = []

        total_candidates = len(candidates) + (len(images) -1) * best_candidates_amount
        # Report initial zero progress (include best score placeholder)
        if progress_callback:
            try:
                progress_callback(0, total_candidates, 0)
            except Exception:
                pass

        checked = 0
        for preset_obj in candidates:
            score, bbox = self._evaluate_settings(crop0, preset_obj, precomputed_db, match_mode)

            checked += 1
            if progress_callback:
                try:
                    progress_callback(checked, total_candidates, best_score_st1)
                except Exception:
                    pass
            if score > best_score_st1:
                best_score_st1 = score
                best_settings_st1 = preset_obj
            
            if score > 50:
                ranked_candidates.append((score, preset_obj, bbox))

        def sort_key(item):
            score, s, _ = item
            mode_prio = 1 if s._setting_mode == 'color' else 0

            if s._setting_mode == 'color':
                return (score, mode_prio, -s.color_tolerance, -(s.text_thickening + 1), -s.contrast)

            return (score, mode_prio, -s.brightness_threshold, 0, -s.contrast)

        ranked_candidates.sort(key=sort_key, reverse=True)
        survivors = ranked_candidates[:best_candidates_amount]

        # --- PODSUMOWANIE 5 NAJLEPSZYCH USTAWIEŃ po każdym zrzucie ---
        def print_summary(ranked, img_idx, total_imgs):
            print(f"\nPODSUMOWANIE 5 NAJLEPSZYCH USTAWIEŃ po zrzucie {img_idx+1}/{total_imgs}:")
            for idx, (score_list, s, bbox) in enumerate(ranked[:5], 1):
                color = s.colors[0] if s.colors else '-'
                match_mode_str = match_mode
                final_score = sum(score_list) / len(score_list) if score_list else 0
                score_this_img = score_list[-1] if score_list else 0
                print(f"{idx}. Final Score: {final_score:.1f}% | Score: {score_this_img:.1f}% | Kolor: {color} | Tryb: {match_mode_str} | Tolerancja: {s.color_tolerance} | Kontrast: {s.contrast} | Pogrubienie: {s.text_thickening}")

        # Pierwszy zrzut: score_list = [score]
        survivors = [([score], s, bbox) for score, s, bbox in survivors]
        print_summary(survivors, 0, len(input_images))

        # Jeśli mamy więcej obrazów, filtrujemy
        rejected_screens = []
        if len(input_images) > 1 and survivors:
            finalists = survivors
            # Sprawdzamy kolejne obrazy
            for idx, img in enumerate(input_images[1:], start=1):
                crop_n = create_crop(img)
                if not crop_n: continue
                next_round = []
                best_ocr = None
                best_ocr_score = -1
                best_ocr_img = None
                for score_list, s, _ in finalists:
                    score, bbox = self._evaluate_settings(crop_n, s, precomputed_db, match_mode)
                    if score > best_ocr_score:
                        best_ocr_score = score
                        best_ocr_img = crop_n
                        try:
                            best_ocr = recognize_text(crop_n, OptimizerConfigManager(s))
                        except Exception:
                            best_ocr = "<OCR error>"
                    if score > 50:
                        next_round.append((score_list + [score], s, bbox))
                if not next_round:
                    # Zapisz info o odrzuconym zrzucie
                    # (Rest of loop remains mostly similar but uses s instead of settings)
                    # Zapisz info o odrzuconym zrzucie
                    preview_path = None
                    if best_ocr_img is not None:
                        try:
                            preview_path = f"odrzucony_zrzut_{idx+1}.png"
                            best_ocr_img.save(preview_path)
                        except Exception as e:
                            preview_path = f"Błąd zapisu: {e}"
                    rejected_screens.append({
                        "index": idx+1,
                        "ocr": best_ocr,
                        "score": best_ocr_score,
                        "preview": preview_path
                    })
                    continue
                next_round.sort(key=sort_key, reverse=True)
                finalists = next_round
                print_summary(finalists, idx, len(input_images))
            if finalists:
                finalists.sort(key=sort_key, reverse=True)
                best_score_list, best_preset, best_bbox = finalists[0]
                avg_score = sum(best_score_list) / len(best_score_list)
                opt_rect = rough_area
                print(f"best settings: {best_preset}")
                return {
                    "score": avg_score, 
                    "settings": best_preset, 
                    "optimized_area": opt_rect,
                    "rejected_screens": rejected_screens
                }

        # Fallback jeśli tylko 1 obraz LUB brak survivors
        if best_settings_st1:
            opt_rect = rough_area
            print(f"best settings: {best_settings_st1}")
            return {
                "match_mode": match_mode,
                "score": best_score_st1, 
                "settings": best_settings_st1,
                "optimized_area": opt_rect,
                "rejected_screens": []
            }
        return {"score": 0, "settings": None, "optimized_area": rough_area, "match_mode": match_mode, "rejected_screens": []}

    def _evaluate_settings(self, 
                           crop: Image.Image, 
                           preset: PresetConfig, 
                           precomputed_db: Any,
                           match_mode: str = MATCH_MODE_FULL) -> Tuple[float, Optional[Tuple[int, int, int, int]]]:
        """
        Pomocnicza funkcja wykonująca jeden krok ewaluacji: Preprocess -> OCR -> Match.
        Zwraca (score, bbox) lub (0, None) w przypadku błędu/braku wyniku.
        """
        mock_cfg = OptimizerConfigManager(preset)

        try:
            # Pass the preset as area_config so preprocess_image can read per-preset values
            processed_img, has_content, bbox = preprocess_image(crop.copy(), mock_cfg, area_config=preset)
            if not has_content:
                return 0, None

            ocr_text = recognize_text(processed_img, mock_cfg)
            if not ocr_text or len(ocr_text.strip()) < 2:
                return 0, None

            match_result = find_best_match(ocr_text, precomputed_db, mode=match_mode, matcher_config=mock_cfg)
        except Exception:
            # Jeśli cokolwiek pójdzie nie tak (preprocess/OCR/matching), traktujemy jako brak wyniku
            return 0, None

        if not match_result:
            return 0, bbox

        _, score = match_result

        # Check for exact match (Score 101)
        # precomputed_db[1] is the exact_map (cleaned_text -> index)
        from app.text_processing import clean_text, smart_remove_name

        ocr_no_name = smart_remove_name(ocr_text)
        cleaned_ocr = clean_text(ocr_no_name)
        # For exact/full-lines mode require full equality.
        if match_mode == MATCH_MODE_FULL:
            if cleaned_ocr in precomputed_db[1]:
                score = 101
        # For 'Starts' mode allow the recognized text to be a prefix or the
        # original to be a prefix of the recognized text — treat as exact start.
        elif match_mode == MATCH_MODE_STARTS:
            try:
                exact_map_keys = list(precomputed_db[1].keys())
            except Exception:
                exact_map_keys = []
            for key in exact_map_keys:
                if not key:
                    continue
                if cleaned_ocr.startswith(key) or key.startswith(cleaned_ocr):
                    score = 101
                    break
        else:
            # For other modes (partial etc.) keep existing behavior (no forced 101).
            pass

        return score, bbox
