#!/usr/bin/env bash
set -e

# --- Konfiguracja ---
APP_NAME="lektor"
ENTRY_FILE="lektor.py"
VENV_DIR=".venv-deck"
BUILD_DIR="dist_pyinstaller"

echo "🚀 Rozpoczynam budowanie aplikacji $APP_NAME dla Steam Deck (PyInstaller)..."

# 1. Sprawdzenie i aktywacja venv
if [ ! -d "$VENV_DIR" ]; then
    echo "❌ Błąd: Środowisko wirtualne $VENV_DIR nie istnieje!"
    echo "Upewnij się, że stworzyłeś je przed uruchomieniem tego skryptu."
    exit 1
fi

echo "📦 Aktywuję środowisko $VENV_DIR..."
source "$VENV_DIR/bin/activate"

# 2. Instalacja PyInstallera jeśli brakuje
if ! command -v pyinstaller &> /dev/null; then
    echo "📥 PyInstaller nie jest zainstalowany w venv. Instaluję..."
    pip install pyinstaller
fi

# 3. Czyszczenie poprzednich plików
echo "🧹 Czyszczenie starych plików buildu..."
rm -rf build dist "$BUILD_DIR" *.spec

# 4. Przygotowanie danych dodatkowych (datas)
# W razie potrzeby dodaj tutaj pliki (np. ikony, konfiguracje)
# Format: --add-data "source:dest" (na Linuxie używamy dwukropka :)
ADD_DATAS=""
if [ -f "app_config.json" ]; then
    ADD_DATAS="$ADD_DATAS --add-data app_config.json:."
fi

# 5. Budowanie (Onefile)
echo "🛠️ Uruchamiam PyInstallera..."
# --onefile: pakuje wszystko do jednego pliku wykonywalnego
# --windowed / --noconsole: ukrywa terminal (dla aplikacji GUI)
# --clean: czyści cache przed budowaniem
# --name: nazwa pliku wynikowego
# --collect-all: przydatne dla niektórych bibliotek (np. customtkinter, PIL)

pyinstaller --noconfirm --onefile --windowed --clean \
    --name "$APP_NAME" \
    $ADD_DATAS \
    --collect-all customtkinter \
    --collect-all PIL \
    --hidden-import thefuzz \
    --hidden-import mss \
    --hidden-import pipewire_capture \
    "$ENTRY_FILE"

# 6. Przenoszenie wyniku
mkdir -p "$BUILD_DIR"
mv dist/"$APP_NAME" "$BUILD_DIR/"

echo ""
echo "✅ Budowanie zakończone sukcesem!"
echo "📍 Plik wynikowy: $BUILD_DIR/$APP_NAME"
echo ""
ls -lh "$BUILD_DIR/$APP_NAME"
