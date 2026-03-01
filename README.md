# Lektor 

**Lektor** to aplikacja pomocnicza dla graczy, która w czasie rzeczywistym odczytuje (OCR) dialogi wyświetlane na ekranie, dopasowuje je do bazy napisów i odtwarza przygotowane pliki audio (dubbing).

## 🚀 Możliwości

* **OCR w czasie rzeczywistym:** Szybkie rozpoznawanie tekstu z wybranych obszarów ekranu.
* **Inteligentne dopasowanie:** Wykorzystuje algorytmy fuzzy matching (Rapidfuzz), aby ignorować błędy OCR i drobne różnice w tekście.
* **Działanie w tle:** Minimalistyczne GUI i sterowanie skrótami klawiszowymi.
* **Wsparcie dla Wayland i Windows:** Automatyczny wybór backendu do zrzutów ekranu (`mss` dla Windows/X11, PipeWire dla Wayland).
* **Filtrowanie:** Automatyczne usuwanie imion postaci (np. "Geralt: Witaj") i szumów.

---

## 🛠️ Wymagania Techniczne

### System

* Python 3.8+.
* System operacyjny: Windows 10/11 lub Linux (testowane na GNOME Wayland).

### Zewnętrzne Narzędzia

1.  **Tesseract OCR**: Silnik rozpoznawania tekstu.
    * *Windows:* Zainstaluj [Tesseract installer](https://github.com/UB-Mannheim/tesseract/wiki). Ścieżka domyślna: `C:\Program Files\Tesseract-OCR`.
    * *Linux:* `sudo apt install tesseract-ocr tesseract-ocr-pol`
2.  **FFmpeg (ffplay)**: Do odtwarzania dźwięku.
    * Musi być dostępny w zmiennej środowiskowej PATH (polecenie `ffplay` musi działać w terminalu).

### Instalacja Python

```bash
# 1. Utwórz środowisko wirtualne
python -m venv venv
source venv/bin/activate  # Linux/macOS
venv\Scripts\activate     # Windows
```

# 2. Zainstaluj zależności
```shell
pip install -r requirements.txt
```

## 📁 Struktura Folderu Lektora (Preset)
Aplikacja pracuje na "profilach" (presetach). Każda gra powinna mieć swój katalog o następującej strukturze:

Plaintext
```shell
MojaGra_Dubbing/
├── lektor.json        # Plik konfiguracyjny (tworzony automatycznie przez aplikację)
├── subtitles.txt      # Plik tekstowy z liniami dialogowymi (UTF-8)
├── names.txt          # (Opcjonalnie) Lista imion do wycinania z dialogów
└── audio/             # Katalog z plikami dźwiękowymi
    ├── output1 (1).ogg
    ├── output1 (2).ogg
    └── ...
```
### Ważne: Pliki audio muszą być nazwane zgodnie z numerem linii w subtitles.txt, np. output1 (15).ogg odpowiada 15. linii tekstu.

## 🎮 Instrukcja Użytkowania
Uruchom plik `lektor.py`.

Wybierz katalog z profilem gry (menu Lektor -> Wybierz katalog...).

Zdefiniuj obszary ekranu:

Wybierz Lektor -> Obszary ekranu -> Obszar 1.

Zaznacz myszką prostokąt, w którym pojawiają się dialogi.

Możesz zdefiniować do 3 obszarów (np. Obszar 1: Dialogi główne, Obszar 2: Wybory, Obszar 3: Adnotacje).

Dostosuj parametry w oknie głównym (prędkość audio, głośność, częstotliwość skanowania).

Kliknij START (lub użyj skrótu klawiszowego).

Skróty Klawiszowe
Skróty domyślne. Można je zmienić w menu Plik -> Ustawienia aplikacji.

Ctrl + F5: Start / Stop czytania.

Ctrl + F6: Aktywacja "Obszaru 3" na 2 sekundy (przydatne do czytania dymków nad postaciami lub adnotacji).

## 🧠 Architektura (Dla Deweloperów)
Aplikacja działa w modelu Producent-Konsument wykorzystując wątki i kolejki.

* Wątek GUI (Main): Obsługuje interfejs Tkinter.

* CaptureWorker (Producent): Działa w pętli z zadanym interwałem. Wykonuje zrzut ekranu obejmujący wszystkie zdefiniowane strefy naraz (dla optymalizacji) i wrzuca go do kolejki img_queue.

* ReaderThread (Konsument):

* Pobiera obraz z kolejki img_queue.

* Wykonuje OCR (pytesseract) i wstępnie przetwarza tekst.

* Porównuje wynik z bazą subtitles.txt (fuzzy matching).

* Jeśli znajdzie dopasowanie -> wrzuca ścieżkę pliku audio do audio_queue.

* PlayerThread: Odbiera ścieżki z audio_queue i uruchamia proces ffplay do odtwarzania.

Autor: kpasek | Wersja: v0.8.0