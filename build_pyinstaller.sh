#!/usr/bin/env bash
set -e

# --- Konfiguracja ---
APP_NAME="lektor"
ENTRY_FILE="lektor.py"
VENV_DIR=".venv"
BUILD_DIR="dist_pyinstaller"

echo "🚀 Rozpoczynam lokalne budowanie aplikacji $APP_NAME za pomocą PyInstaller..."

# 1. Sprawdzenie i aktywacja venv
if [ ! -d "$VENV_DIR" ]; then
    echo "❌ Błąd: Środowisko wirtualne $VENV_DIR nie istnieje!"
    echo "Upewnij się, że stworzyłeś je przed uruchomieniem tego skryptu."
    exit 1
fi

echo "📦 Aktywuję środowisko $VENV_DIR..."
source "$VENV_DIR/bin/activate"

# 2. Instalacja PyInstallera i pip jeśli brakuje
if ! command -v pyinstaller &> /dev/null; then
    echo "📥 PyInstaller nie jest zainstalowany w venv. Instaluję..."
    pip install pyinstaller wheel setuptools
fi

# 3. Czyszczenie poprzednich plików
echo "🧹 Czyszczenie starych plików buildu..."
rm -rf build dist "$BUILD_DIR" *.spec

# 5. Budowanie (Onefile)
echo "🛠️ Uruchamiam PyInstallera..."

pyinstaller --noconfirm --onefile --windowed --clean \
    --name "$APP_NAME" \
    --collect-all "customtkinter" \
    --hidden-import "PIL._tkinter_finder" \
    "$ENTRY_FILE"

# 6. Przenoszenie wyniku
mkdir -p "$BUILD_DIR"
mv dist/"$APP_NAME" "$BUILD_DIR/"
rm -rf dist build

echo ""
echo "✅ Budowanie zakończone sukcesem!"
echo "📍 Plik wynikowy: $BUILD_DIR/$APP_NAME"
echo ""
ls -lh "$BUILD_DIR/$APP_NAME"
