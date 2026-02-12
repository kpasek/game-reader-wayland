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
                 image: Image.Image, 
                 rough_area: Tuple[int, int, int, int], 
                 subtitle_db: List[str]) -> Dict[str, Any]:
        """
        Znajduje optymalne ustawienia OCR i matchingu dla zadanego wycinka ekranu (rough_area)
        i bazy napisów.
        
        Zwraca słownik z najlepszymi ustawieniami oraz wynikiem (score).
        """
        
        # 1. Wstępne przygotowanie obrazu (crop)
        # rough_area = (left, top, width, height)
        rx, ry, rw, rh = rough_area
        
        # Zabezpieczenie przed wyjściem poza obraz
        img_w, img_h = image.size
        rx = max(0, rx)
        ry = max(0, ry)
        rw = min(rw, img_w - rx)
        rh = min(rh, img_h - ry)
        
        # Jeśli crop jest niepoprawny, zwróć błąd
        if rw <= 0 or rh <= 0:
            return {"error": "Invalid area", "score": 0, "settings": {}, "optimized_area": rough_area}

        crop = image.crop((rx, ry, rx + rw, ry + rh))

        # 2. Przygotowanie bazy napisów (raz na całą optymalizację)
        precomputed_db = precompute_subtitles(subtitle_db)

        # 3. Wykrywanie potencjalnych kolorów napisów
        detected_colors = self._extract_dominant_colors(crop, num_colors=3)
        # Dodajemy biały jako obowiązkowy fallback, używamy set by uniknąć duplikatów
        candidate_colors = set(detected_colors)
        candidate_colors.add("#FFFFFF")
        # Konwertujemy z powrotem na listę dla deterministycznej iteracji (sortowanie opcjonalne, ale pomocne)
        candidate_colors_list = sorted(list(candidate_colors))

        best_score = -1
        best_settings = {}
        best_crop_rel = None # Bbox względem rough_area

        # Wspólne ustawienia (niezmienne w pętli)
        common_settings = {
            "auto_remove_names": True,
            "resolution": "1920x1080", # Można to ewentualnie parametryzować w przyszłości
            "text_alignment": "None" 
        }

        # Zmienne iterowane (Wspólne)
        scales = [0.5, 0.75, 1.0]

        # ---------------------------------------------------------
        # Branch A: Color-based (Color Filter)
        # ---------------------------------------------------------
        # Variables:
        # - subtitle_colors: [Color] (Jeden kolor na raz)
        # - color_tolerance: range(5, 45, 5) -> 5, 10, ..., 40
        # - text_thickening: [0, 1]
        # - ocr_scale_factor: scales
        color_tolerances = range(5, 45, 5)
        thickenings = [0, 1]

        for color in candidate_colors_list:
            for tol, thick, scale in itertools.product(color_tolerances, thickenings, scales):
                
                settings = self.base_preset.copy()
                settings.update(common_settings)
                settings.update({
                    "subtitle_colors": [color], # Testujemy jeden konkretny kolor
                    "color_tolerance": tol,
                    "text_thickening": thick,
                    "ocr_scale_factor": scale,
                    # Wartości domyślne dla Branch B (ignorowane gdy subtitle_colors jest ustawione)
                    "text_color_mode": "Light", 
                    "brightness_threshold": 200, 
                    "contrast": 0,
                    "contract": 0 
                })

                score, bbox = self._evaluate_settings(crop, settings, precomputed_db)
                if score > best_score:
                    best_score = score
                    best_settings = settings
                    best_crop_rel = bbox

        # ---------------------------------------------------------
        # Branch B: Grayscale/Binary (No specific color)
        # ---------------------------------------------------------
        # Variables:
        # - brightness_threshold: range(150, 230, 5) -> 150...225 (Użytkownik podał (150, 230, 5) co w Pythonie wyklucza 230)
        # - contrast: [0.0, 0.2, 0.5, 1.0]
        # - ocr_scale_factor: scales
        
        brightness_range = range(150, 230, 5)
        contrasts = [0.0, 0.2, 0.5, 1.0]
        text_color_modes = ["Light"] # Standardowo Light

        for br, cont, scale, mode in itertools.product(brightness_range, contrasts, scales, text_color_modes):
             settings = self.base_preset.copy()
             settings.update(common_settings)
             settings.update({
                "subtitle_colors": [], # Pusta lista wymusza branch grayscale w OCR
                "brightness_threshold": br,
                "contrast": cont,
                "contract": cont, # Dla wstecznej kompatybilności (literówka w OCR logic)
                "ocr_scale_factor": scale,
                "text_color_mode": mode,
                "text_thickening": 0 # W trybie binarnym zazwyczaj nie pogrubiamy, lub jest to osobny parametr (tutaj upraszczamy)
             })

             score, bbox = self._evaluate_settings(crop, settings, precomputed_db)
             if score > best_score:
                 best_score = score
                 best_settings = settings
                 best_crop_rel = bbox

        # 4. Obliczanie wynikowego, absolutnego obszaru
        final_area = rough_area
        if best_crop_rel:
             # bbox format: (left, upper, right, lower) względem cropa
             bl, bt, br_x, bb = best_crop_rel
             
             abs_x = rx + bl
             abs_y = ry + bt
             abs_w = br_x - bl
             abs_h = bb - bt
             
             final_area = (abs_x, abs_y, abs_w, abs_h)

        return {
            "score": best_score,
            "settings": best_settings,
            "optimized_area": final_area
        }

    def _evaluate_settings(self, 
                           crop: Image.Image, 
                           settings: Dict[str, Any], 
                           precomputed_db: Any) -> Tuple[float, Optional[Tuple[int, int, int, int]]]:
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
            match_result = find_best_match(ocr_text, precomputed_db, mode="Full Lines")
        except Exception:
            return 0, None

        if match_result:
            _, score = match_result
            return score, bbox
        
        return 0, bbox
