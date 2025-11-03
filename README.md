# Game Reader (Wayland)

Aplikacja lektora do gier dla Linuksa (Wayland) z kolejką audio i obsługą uruchamiania gier.

## Wymagania Systemowe

Przed instalacją upewnij się, że masz:
* Python 3.8+
* `ffmpeg` (dla dynamicznej zmiany prędkości audio)
* `spectacle` (dla KDE) lub `gnome-screenshot` (dla GNOME)
* `tesseract-ocr`
* `tesseract-ocr-pol` (lub inny pakiet językowy)

Na KDE (Kubuntu/Debian):
`sudo apt install ffmpeg spectacle tesseract-ocr tesseract-ocr-pol python3-tk`

---

## Instalacja i Uruchamianie

Masz dwie zalecane metody instalacji.

### Metoda 1: Instalacja dla użytkownika (Zalecana)

Ta metoda instaluje skrypt i jego zależności w Twoim katalogu domowym (`~/.local/`). Polecenie `game_reader` staje się dostępne globalnie dla Twojego użytkownika, co **idealnie nadaje się do uruchamiania ze Steam/Lutris**.

1.  Będąc w głównym katalogu projektu (tam, gdzie jest `pyproject.toml`), uruchom:
    ```bash
    pip install --user .
    ```
    *(Użyj `pip3` jeśli `pip` nie jest domyślny)*.

2.  **Ważne:** Upewnij się, że `~/.local/bin` jest w Twojej ścieżce `$PATH`.
    Większość nowoczesnych dystrybucji robi to automatycznie. Możesz sprawdzić wpisując `echo $PATH`. Jeśli nie, dodaj poniższą linię do swojego pliku `.bashrc` lub `.zshrc`:
    ```bash
    export PATH="$HOME/.local/bin:$PATH"
    ```
    Po tym uruchom ponownie terminal lub `source ~/.bashrc`.

#### Uruchamianie (Metoda 1)

* **Standardowe (GUI):**
    ```bash
    game_reader
    ```

* **Ze Steam (Opcje uruchamiania):**
    ```bash
    game_reader --preset "/ścieżka/do/twojego/presetu.json" -- %command%
    ```

### Metoda 2: Budowanie samodzielnej aplikacji (PyInstaller)

Ta metoda tworzy **jeden, duży plik wykonywalny**, który zawiera Pythona, wszystkie biblioteki i Twój skrypt. Nie wymaga żadnej instalacji.

1.  Zainstaluj PyInstaller (wystarczy raz):
    ```bash
    pip install pyinstaller
    ```

2.  W głównym katalogu projektu uruchom budowanie:
    ```bash
    pyinstaller --onefile --windowed --name=game_reader game_reader_gui.py
    ```
    * `--onefile`: Tworzy jeden plik.
    * `--windowed`: Ukrywa czarne okno konsoli podczas uruchamiania GUI.
    * `--name=game_reader`: Nazwa pliku wyjściowego.

3.  Po zakończeniu, Twój plik znajdzie się w katalogu `dist/`. Będzie to `dist/game_reader`.

4.  Skopiuj ten plik w dowolne dogodne miejsce, np. `~/bin/` lub `~/.local/bin/`.

#### Uruchamianie (Metoda 2)

* **Standardowe (GUI):**
    ```bash
    /ścieżka/do/skopiowanego/pliku/game_reader
    ```

* **Ze Steam (Opcje uruchamiania):**
    ```bash
    /ścieżka/do/skopiowanego/pliku/game_reader --preset "/ścieżka/do/twojego/presetu.json" -- %command%
    ```