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
                 match_mode: str = "Full Lines",
                 initial_color: str = None) -> Dict[str, Any]:
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
        # Jeśli użytkownik wybrał kolor, używamy tylko tego koloru jako kandydata
        if initial_color:
            candidate_colors_list = [initial_color]
        else:
            candidate_colors = set(detected_colors)
            candidate_colors.add("#FFFFFF")
            candidate_colors_list = sorted(list(candidate_colors))

        # Generowanie kandydatów ustawień
        candidates = []

        # Wspólne parametry do permutacji
        # Zmiana: Testy zawsze w pełnej skali (1.0), aby wykluczyć błędy przy skalowaniu


        params = {
            "color_tolerances": range(1, 30, 1),
            "thickenings": [0, 1],
            "contrasts": [round(x * 0.1, 2) for x in range(0, 11)]  # 0.0, 0.1, ..., 1.0
        }

        # Generujemy pełną listę wszystkich kombinacji ustawień do sprawdzenia
        # Branch A: Color-based
        for color in candidate_colors_list:
            for tol, thick, contrast in itertools.product(params["color_tolerances"], params["thickenings"], params["contrasts"]):
                s = self.base_preset.copy()
                s.update({
                    "auto_remove_names": True,
                    "resolution": "1920x1080",
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
        
        # Branch B: Text Color Mode (Light/Dark/Mixed) - tylko jeśli nie znaleziono kolorów?
        # W oryginalnym kodzie było to oddzielne, tutaj dla uproszczenia (i zgodnie z prośbą usunięcia z UI)
        # możemy pominąć, lub dodać jako fallback. Skoro usuwamy z UI, to tutaj w optymalizatorze
        # też wypadałoby się skupić na kolorach (subtitle_colors), chyba że użytkownik chce tryb jasny/ciemny bez kolorów.
        # Ale skoro extract_dominant_colors zawsze coś zwraca (choćby biały), to Branch A pokrywa większość.
        # Dodam jednak dla pewności defaultowy biały bez filtracji kolorem (czyli czyste OCR na progowaniu jasności)
        # Tzw. legacy mode.
        for mode in ["Light", "Dark"]:
            for thick, contrast in itertools.product(params["thickenings"], params["contrasts"]):
                s = self.base_preset.copy()
                s.update({
                    "auto_remove_names": True,
                    "subtitle_colors": [], # Pusta lista = tryb jasności/kontrastu
                    "text_color_mode": mode,
                    "text_thickening": thick,
                    "ocr_scale_factor": 1.0,
                    "brightness_threshold": 200,
                    "contrast": contrast
                })
                candidates.append(s)


        # ETAP 1: Ewaluacja na pierwszym obrazie
        survivors = []
        best_score_st1 = 0
        best_settings_st1 = None

        # Zamiast sztywnego progu 100%, zbieramy najlepszych kandydatów
        ranked_candidates = []

        for settings in candidates:
            score, bbox = self._evaluate_settings(crop0, settings, precomputed_db, match_mode)

            if score > best_score_st1:
                best_score_st1 = score
                best_settings_st1 = settings
                best_bbox_st1 = bbox
            
            # Dodajemy wszystko co ma jakikolwiek sens (> 10%) - próg znacznie obniżony
            if score > 10:
                ranked_candidates.append((score, settings, bbox))

        # Sortujemy i bierzemy znacznie szerszą grupę kandydatów (TOP 50)
        # Preferuj: wyższy score, niższa tolerancja, brak pogrubienia
        def sort_key(item):
            score, settings, _ = item
            tolerance = settings.get('color_tolerance', 9999)
            thick = settings.get('text_thickening', 1)
            contrast = settings.get('contrast', 9999)
            # Najpierw score (malejąco), potem tolerancja (rosnąco), potem pogrubienie (0 preferowane), potem kontrast (rosnąco)
            return (score, -tolerance, -int(thick == 0), -contrast)

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
        ranked_candidates = [([score], settings, bbox) for score, settings, bbox in ranked_candidates]
        print_summary(ranked_candidates, 0, len(input_images))

        # Jeśli mamy więcej obrazów, filtrujemy
        rejected_screens = []
        if len(input_images) > 1 and survivors:
            finalists = ranked_candidates
            # Sprawdzamy kolejne obrazy
            for idx, img in enumerate(input_images[1:], start=1):
                crop_n = create_crop(img)
                if not crop_n: continue
                next_round = []
                best_ocr = None
                best_ocr_score = -1
                best_ocr_settings = None
                best_ocr_img = None
                for score_list, settings, _ in finalists:
                    score, bbox = self._evaluate_settings(crop_n, settings, precomputed_db, match_mode)
                    # Zapamiętaj najlepszy OCR (niezależnie od progu)
                    if score > best_ocr_score:
                        best_ocr_score = score
                        best_ocr_settings = settings
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
                finalists = next_round[:20]
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
                "score": best_score_st1, 
                "settings": best_settings_st1,
                "optimized_area": opt_rect,
                "rejected_screens": []
            }
        return {"score": 0, "settings": {}, "optimized_area": rough_area, "rejected_screens": []}

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
            from app.text_processing import clean_text, smart_remove_name
            
            # Musimy usunąć imię tak samo jak robi to matcher
            ocr_no_name = smart_remove_name(ocr_text)
            cleaned_ocr = clean_text(ocr_no_name)
            
            if cleaned_ocr in precomputed_db[1]:
                 score = 101
                 
            return score, bbox
        
        return 0, bbox
