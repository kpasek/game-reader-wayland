from PIL import Image
import itertools
from collections import Counter
from typing import Tuple, List, Dict, Any, Optional

from app.ocr import preprocess_image, recognize_text
from app.matcher import find_best_match, precompute_subtitles, MATCH_MODE_FULL
from app.config_manager import ConfigManager

class OptimizerConfigManager(ConfigManager):
    """
    Specjalna wersja ConfigManager, która zwraca wymuszony zestaw ustawień (preset),
    zamiast ładować go z pliku.
    """
    def __init__(self, override_settings: Dict[str, Any]):
        # Nie wołamy super().__init__, bo nie chcemy ładować plików
        self.override_settings = override_settings
        self.settings = {} # Dummy

    def load_preset(self, path=None) -> Dict[str, Any]:
        return self.override_settings

class SettingsOptimizer:
    def __init__(self, original_config_manager: ConfigManager = None):
        # We can use the original to get some defaults if needed, 
        # but mostly we will be generating variations.
        self.base_preset = original_config_manager.load_preset() if original_config_manager else {}

    def _extract_dominant_colors(self, image: Image.Image, num_colors: int = 3) -> List[str]:
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
                 images: Any, 
                 rough_area: Tuple[int, int, int, int], 
                 subtitle_db: List[str],
                 match_mode: str = MATCH_MODE_FULL,
                 initial_color: str = None) -> Dict[str, Any]:
        """
        Znajduje optymalne ustawienia OCR i matchingu dla zadanego wycinka ekranu (rough_area)
        i bazy napisów.
        
        Args:
            images: Pojedynczy obraz PIL.Image lub lista obrazów [PIL.Image].
                    Jeśli podano listę, optymalizacja odbywa się wieloetapowo.
        """
        
        try:
            num_images = len(images) if isinstance(images, list) else 1
        except Exception:
            num_images = 'unknown'

        # Normalizacja do listy
        if not isinstance(images, list):
            input_images = [images]
        else:
            input_images = images
            
        if not input_images:
            return {}

        first_image = input_images[0]
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

        # Generujemy pełną listę wszystkich kombinacji ustawień do sprawdzenia
        # Branch A: Color-based
        for color in candidate_colors_list:
            for tol, thick, contrast in itertools.product(params["color_tolerances"], params["thickenings"], params["contrasts"]):
                s = self.base_preset.copy()
                s.update({
                    "setting_mode": "color",
                    "auto_remove_names": True,
                    "text_alignment": "None",
                    "subtitle_colors": [color],
                    "color_tolerance": tol,
                    "text_thickening": thick,
                    "ocr_scale_factor": 1.0,
                    "text_color_mode": "Light", 
                    "brightness_threshold": 200, 
                    "contrast": contrast
                })
                candidates.append(s)
        
        # Branch B: Brightness Mode (Light/Dark/Mixed)
        for mode in ["Light", "Dark"]:
            for contrast, brightness in itertools.product(params["contrasts"], params["brightness_threshold"]):
                s = self.base_preset.copy()
                s.update({
                    "setting_mode": "brightness",
                    "auto_remove_names": True,
                    "text_alignment": "None",
                    "subtitle_colors": [],
                    "text_color_mode": mode,
                    "text_thickening": 0,
                    "ocr_scale_factor": 1.0,
                    "brightness_threshold": brightness,
                    "contrast": contrast
                })
                candidates.append(s)


        # ETAP 1: Ewaluacja na pierwszym obrazie
        survivors = []
        best_score_st1 = 0
        best_settings_st1 = None

        ranked_candidates = []

        for settings in candidates:
            score, bbox = self._evaluate_settings(crop0, settings, precomputed_db, match_mode)

            if score > best_score_st1:
                best_score_st1 = score
                best_settings_st1 = settings
            
            if score > 50:
                ranked_candidates.append((score, settings, bbox))

        def sort_key(item):
            score, settings, _ = item
            # Prefer color-mode candidates over brightness-mode when otherwise equal.
            mode_prio = 1 if settings.get('setting_mode') == 'color' else 0

            if settings.get('setting_mode') == 'color':
                tolerance = settings.get('color_tolerance', 9999)
                thick = settings.get('text_thickening', 1)
                contrast = settings.get('contrast', 9999)
                # Higher mode_prio (color) helps color candidates win in reverse sorting
                return (score, mode_prio, -tolerance, -int(thick == 0), -contrast)

            brightness = settings.get('brightness_threshold', 1)
            contrast = settings.get('contrast', 9999)
            return (score, mode_prio, brightness, 1, -contrast)

        ranked_candidates.sort(key=sort_key, reverse=True)
        survivors = ranked_candidates[:50]

        # --- PODSUMOWANIE 5 NAJLEPSZYCH USTAWIEŃ po każdym zrzucie ---
        def print_summary(ranked, img_idx, total_imgs):
            print(f"\nPODSUMOWANIE 5 NAJLEPSZYCH USTAWIEŃ po zrzucie {img_idx+1}/{total_imgs}:")
            for idx, (score_list, settings, bbox) in enumerate(ranked[:5], 1):
                color = settings.get('subtitle_colors', [''])[0] if settings.get('subtitle_colors') else '-'
                match_mode_str = match_mode
                tolerance = settings.get('color_tolerance', '-')
                contrast = settings.get('contrast', '-')
                thick = settings.get('text_thickening', '-')
                final_score = sum(score_list) / len(score_list) if score_list else 0
                score_this_img = score_list[-1] if score_list else 0
                print(f"{idx}. Final Score: {final_score:.1f}% | Score: {score_this_img:.1f}% | Kolor: {color} | Tryb: {match_mode_str} | Tolerancja: {tolerance} | Kontrast: {contrast} | Pogrubienie: {thick}")

        # Pierwszy zrzut: score_list = [score]
        survivors = [([score], settings, bbox) for score, settings, bbox in survivors]
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
                for score_list, settings, _ in finalists:
                    score, bbox = self._evaluate_settings(crop_n, settings, precomputed_db, match_mode)
                    if score > best_ocr_score:
                        best_ocr_score = score
                        best_ocr_img = crop_n
                        try:
                            ocr_text = recognize_text(crop_n, OptimizerConfigManager(settings))
                        except Exception:
                            ocr_text = "<OCR error>"
                        best_ocr = ocr_text
                    if score > 50:
                        next_round.append((score_list + [score], settings, bbox))
                if not next_round:
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
                best_score_list, best_settings, best_bbox = finalists[0]
                avg_score = sum(best_score_list) / len(best_score_list)
                opt_rect = rough_area
                return {
                    "score": avg_score, 
                    "settings": best_settings, 
                    "optimized_area": opt_rect,
                    "rejected_screens": rejected_screens
                }

        # Fallback jeśli tylko 1 obraz LUB brak survivors
        if best_settings_st1:
            # Same fix here
            opt_rect = rough_area
            return {
                "match_mode": match_mode,
                "score": best_score_st1, 
                "settings": best_settings_st1,
                "optimized_area": opt_rect,
                "rejected_screens": []
            }
        return {"score": 0, "settings": {}, "optimized_area": rough_area, "match_mode": match_mode, "rejected_screens": []}

    def _evaluate_settings(self, 
                           crop: Image.Image, 
                           settings: Dict[str, Any], 
                           precomputed_db: Any,
                           match_mode: str = MATCH_MODE_FULL) -> Tuple[float, Optional[Tuple[int, int, int, int]]]:
        """
        Pomocnicza funkcja wykonująca jeden krok ewaluacji: Preprocess -> OCR -> Match.
        Zwraca (score, bbox) lub (0, None) w przypadku błędu/braku wyniku.
        """
        mock_cfg = OptimizerConfigManager(settings)

        try:
            processed_img, has_content, bbox = preprocess_image(crop.copy(), mock_cfg)
            if not has_content:
                return 0, None

            ocr_text = recognize_text(processed_img, mock_cfg)
            if not ocr_text or len(ocr_text.strip()) < 2:
                return 0, None

            match_result = find_best_match(ocr_text, precomputed_db, mode=match_mode)
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
        if cleaned_ocr in precomputed_db[1]:
            score = 101

        return score, bbox
