import pytesseract
from PIL import Image
import itertools
from collections import Counter
from typing import Tuple, List, Dict, Any, Optional

from app.ocr import preprocess_image, recognize_text
from app.matcher import find_best_match, precompute_subtitles
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
                 match_mode: str = "Full Lines") -> Dict[str, Any]:
        """
        Znajduje optymalne ustawienia OCR i matchingu dla zadanego wycinka ekranu (rough_area)
        i bazy napisów.
        
        Args:
            images: Pojedynczy obraz PIL.Image lub lista obrazów [PIL.Image].
                    Jeśli podano listę, optymalizacja odbywa się wieloetapowo.
        """
        
        # Normalizacja do listy
        if not isinstance(images, list):
            input_images = [images]
        else:
            input_images = images
            
        if not input_images:
            return {}

        first_image = input_images[0]

        # 1. Wstępne przygotowanie obrazu (crop) dla pierwszego obrazu
        # rough_area = (left, top, width, height)
        rx, ry, rw, rh = rough_area
        
        # Zabezpieczenie przed wyjściem poza obraz
        img_w, img_h = first_image.size
        # ... (zachowanie logiki cropa dla cropów pomocniczych, ale tutaj musimy cropować każdego z osobna w pętli)
        
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
        candidate_colors = set(detected_colors)
        candidate_colors.add("#FFFFFF")
        candidate_colors_list = sorted(list(candidate_colors))

        # Generowanie kandydatów ustawień
        candidates = []

        # Wspólne parametry do permutacji
        params = {
            "scales": [0.5, 0.75, 1.0],
            "color_tolerances": range(5, 45, 5),
            "thickenings": [0, 1]
        }

        # Generujemy pełną listę wszystkich kombinacji ustawień do sprawdzenia
        # Branch A: Color-based
        for color in candidate_colors_list:
            for tol, thick, scale in itertools.product(params["color_tolerances"], params["thickenings"], params["scales"]):
                s = self.base_preset.copy()
                s.update({
                    "auto_remove_names": True,
                    "resolution": "1920x1080",
                    "text_alignment": "None",
                    "subtitle_colors": [color],
                    "color_tolerance": tol,
                    "text_thickening": thick,
                    "ocr_scale_factor": scale,
                    "text_color_mode": "Light", 
                    "brightness_threshold": 200, 
                    "contrast": 0
                })
                candidates.append(s)
        
        # Branch B: Text Color Mode (Light/Dark/Mixed) - tylko jeśli nie znaleziono kolorów?
        # W oryginalnym kodzie było to oddzielne, tutaj dla uproszczenia (i zgodnie z prośbą usunięcia z UI)
        # możemy pominąć, lub dodać jako fallback. Skoro usuwamy z UI, to tutaj w optymalizatorze
        # też wypadałoby się skupić na kolorach (subtitle_colors), chyba że użytkownik chce tryb jasny/ciemny bez kolorów.
        # Ale skoro extract_dominant_colors zawsze coś zwraca (choćby biały), to Branch A pokrywa większość.
        # Dodam jednak dla pewności defaultowy biały bez filtracji kolorem (czyli czyste OCR na progowaniu jasności)
        # Tzw. legacy mode.
        for mode in ["Light", "Dark"]:
             for thick, scale in itertools.product(params["thickenings"], params["scales"]):
                s = self.base_preset.copy()
                s.update({
                    "auto_remove_names": True,
                    "subtitle_colors": [], # Pusta lista = tryb jasności/kontrastu
                    "text_color_mode": mode,
                    "text_thickening": thick,
                    "ocr_scale_factor": scale,
                    "brightness_threshold": 200,
                    "contrast": 0
                })
                candidates.append(s)


        # ETAP 1: Ewaluacja na pierwszym obrazie
        survivors = []
        best_score_st1 = 0
        best_settings_st1 = None

        for settings in candidates:
            score, bbox = self._evaluate_settings(crop0, settings, precomputed_db, match_mode)

            if score > best_score_st1:
                best_score_st1 = score
                best_settings_st1 = settings
                best_bbox_st1 = bbox

            # Kryterium przejścia dalej: 100% (lub więcej dla exact match)
            if score >= 100:
                survivors.append((score, settings, bbox))

        # Jeśli mamy więcej obrazów, filtrujemy
        if len(input_images) > 1 and survivors:
            finalists = survivors
            
            # Sprawdzamy kolejne obrazy
            for idx, img in enumerate(input_images[1:], start=1):
                crop_n = create_crop(img)
                if not crop_n: continue
                
                next_round = []
                for prev_score, settings, _ in finalists:
                    # Sprawdzamy czy nadal trzyma poziom
                    score, bbox = self._evaluate_settings(crop_n, settings, precomputed_db, match_mode)
                    
                    if score >= 100:
                        # Sumujemy score
                        next_round.append((prev_score + score, settings, bbox))
                
                if not next_round:
                    break
                    
                finalists = next_round
            
            if finalists:
                # Sortujemy po sumarycznym score malejąco
                finalists.sort(key=lambda x: x[0], reverse=True)
                best_total_score, best_settings, best_bbox = finalists[0]
                # Średni score na obraz
                avg_score = best_total_score / len(input_images)
                
                # Use rough_area as the optimized area to preserve the user's intent (margin)
                # Using the tight bbox (detect_text_bounds) removes the margin we carefully added.
                opt_rect = rough_area
                
                # Update: If the detected area is significantly different or shifted, 
                # we might inform the user, but overwriting the margin with a tight fit
                # causes the "Shifted Right/Down" illusion when content changes slightly.
                # However, if we really want to use the refined area, we must ensure 'bx, by' 
                # are relative to 'rough_area' correctly. They seem to be.
                # But 'bbox' comes from 'preprocess_image' which adds padding=4.
                
                # FIX: Always return the rough_area (Input + Margin) to respect the expansion.
                # The text detection inside it is just for OCR validation.

                return {
                    "score": avg_score, 
                    "settings": best_settings, 
                    "optimized_area": opt_rect 
                }

        # Fallback jeśli tylko 1 obraz LUB brak survivors
        if best_settings_st1:
            # Same fix here
            opt_rect = rough_area
                
            return {
                "score": best_score_st1, 
                "settings": best_settings_st1,
                "optimized_area": opt_rect 
            }
            
        return {"score": 0, "settings": {}, "optimized_area": rough_area}

    def _evaluate_settings(self, 
                           crop: Image.Image, 
                           settings: Dict[str, Any], 
                           precomputed_db: Any,
                           match_mode: str = "Full Lines") -> Tuple[float, Optional[Tuple[int, int, int, int]]]:
        """
        Pomocnicza funkcja wykonująca jeden krok ewaluacji: Preprocess -> OCR -> Match.
        Zwraca (score, bbox) lub (0, None) w przypadku błędu/braku wyniku.
        """
        mock_cfg = OptimizerConfigManager(settings)

        # A. Preprocess
        try:
            processed_img, has_content, bbox = preprocess_image(crop.copy(), mock_cfg)
        except Exception:
            # W razie błędów w przetwarzaniu obrazu
            return 0, None

        if not has_content:
            return 0, None

        # B. OCR
        try:
            ocr_text = recognize_text(processed_img, mock_cfg)
        except Exception:
            # W razie błędów tesseracta
            return 0, None
        
        # Filtrowanie zbyt krótkich napisów (szum OCR)
        if not ocr_text or len(ocr_text.strip()) < 2:
            return 0, None

        # C. Matching
        try:
            match_result = find_best_match(ocr_text, precomputed_db, mode=match_mode)
        except Exception:
            return 0, None

        if match_result:
            _, score = match_result
            
            # Check for exact match (Score 101)
            # precomputed_db[1] is the exact_map (cleaned_text -> index)
            from app.text_processing import clean_text
            cleaned_ocr = clean_text(ocr_text)
            if cleaned_ocr in precomputed_db[1]:
                 score = 101
                 
            return score, bbox
        
        return 0, bbox
