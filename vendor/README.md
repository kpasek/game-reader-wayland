# Vendor

Katalog przeznaczony na zewnętrzne zależności wymagane do zbudowania i działania aplikacji (szczególnie w środowisku Steam Deck oraz Wayland).

## Tesseract-OCR dla Steam Deck (SteamOS)
Na Steam Deck system jest w trybie read-only, przez co paczki instalowane przez `pacman` często znikają po aktualizacji systemu, albo ingerencja wiąże się ze złamaniem gwarancji.
Rozwiązaniem jest zapakowanie aplikacji `tesseract` wraz z jej bibliotekami i językami w "przenośny" format.

### Budowanie paczki Tesseract (Linux)
Aby zbudować przenośną paczkę z OCR:
```bash
./vendor/build_tesseract.sh
```
*(Wymaga działającego silnika kontenerów `podman` lub po ręcznej podmianie wewnątrz skryptu `docker`).*

Po poprawnym wykonaniu skryptu, powstanie folder `vendor/tesseract_deck` oraz archiwum `vendor/tesseract_deck.tar.xz`.
Dzięki plikom opakowującym `vendor/tesseract_deck/tesseract` działa bez integracji z hostem.

---

## Zależność `pipewire-capture` (Wayland)

Biblioteka `pipewire-capture` została pobrana i zmodyfikowana lokalnie, aby umożliwić przechwytywanie całych monitorów oprócz pojedynczych okien, co jest kluczowe dla działania Game Readera pod Waylandem (w tym w trybie Game Mode na Steam Decku).

### Budowanie i instalacja lokalnej zależności

Jeśli konfigurujesz ten projekt od zera lub na nowej maszynie linuksowej z Wayland, musisz skompilować i zainstalować tę lokalną zależność w swoim środowisku wirtualnym (nie dotyczy to uruchomień z gotowego builda PyInstaller/Nuitka).

**Wymagania wstępne:**

1.  **Narzędzia Rust:** Potrzebujesz zainstalowanego Rusta. Najłatwiejszym sposobem jest przez `rustup` (https://rustup.rs/).
2.  **Pliki deweloperskie PipeWire:** Musisz zainstalować systemowe biblioteki deweloperskie dla PipeWire.
    *   **Debian/Ubuntu:** `sudo apt install libpipewire-0.3-dev`
    *   **Fedora:** `sudo dnf install pipewire-devel`
    *   **Arch Linux / SteamOS:** `sudo pacman -S pipewire`
3.  **Maturin:** Ten projekt używa `maturin` do budowania wiązań Pythona z biblioteką w Rust. Upewnij się, że jest on zainstalowany w twoim wirtualnym środowisku:
    ```bash
    pip install maturin
    ```

**Instalacja:**

Ponieważ zmodyfikowane zależności w folderze `vendor` są ignorowane w kontroli wersji (z wyjątkiem samego folderu), musisz pobrać i zmodyfikować repozytorium ręcznie:

1.  **Sklonuj repozytorium:**
    ```bash
    mkdir -p vendor
    cd vendor
    git clone https://github.com/bquenin/pipewire-capture.git
    cd ..
    ```

2.  **Zaaplikuj modyfikację ułatwiającą nagrywanie monitorów:**
    Otwórz plik `vendor/pipewire-capture/src/portal.rs` w swoim edytorze. Znajdź kod odpowiedzialny za wybór źródeł (około linii 137), który wygląda tak:
    ```rust
            SourceType::Window.into(),
    ```
    Zamień go na poniższą linię, aby umożliwić przechwytywanie całych monitorów:
    ```rust
            (SourceType::Window | SourceType::Monitor).into(),
    ```

3.  **Kompilacja i instalacja:**
    Po spełnieniu powyższych warunków, wejdź w środowisko projektu i zainstaluj `pipewire-capture`:
    ```bash
    cd vendor/pipewire-capture
    pip install -e .
    ```

Zweryfikuj instalację, uruchamiając `pip list` i sprawdzając, czy `pipewire-capture` wskazuje na lokalny katalog `vendor`.

