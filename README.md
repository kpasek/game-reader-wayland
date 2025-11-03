# Game Reader (Wayland)

Aplikacja lektora do gier dla Linuksa (Wayland) z kolejką audio i obsługą uruchamiania gier.

## Wymagania Systemowe

Przed instalacją upewnij się, że masz:
* Python 3.8+
* `spectacle` (dla KDE) lub `gnome-screenshot` (dla GNOME)
* `tesseract-ocr`
* `tesseract-ocr-pol` (lub inny pakiet językowy)

Na KDE (Kubuntu/Debian):
`sudo apt install spectacle tesseract-ocr tesseract-ocr-pol python3-tk`

## Instalacja

Zaleca się instalację w wirtualnym środowisku (venv):

1.  **Stwórz środowisko:**
    ```bash
    python3 -m venv .venv
    ```

2.  **Aktywuj środowisko:**
    ```bash
    source .venv/bin/activate
    ```

3.  **Zainstaluj pakiet:**
    Będąc w głównym katalogu projektu (tam gdzie jest `pyproject.toml`), uruchom:
    ```bash
    pip install .
    ```
    To polecenie zainstaluje zależności z `requirements.txt` oraz samą aplikację (tworząc polecenie `game_reader`).

## Uruchamianie

Po instalacji możesz zamknąć i ponownie aktywować środowisko (`source .venv/bin/activate`).

### 1. Uruchomienie standardowe (GUI)
Po prostu wpisz w terminalu:
```bash
game_reader