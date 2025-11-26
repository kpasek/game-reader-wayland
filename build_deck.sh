#!/usr/bin/env bash
set -e

APP_NAME="reader_deck"
ENTRY_FILE="game_reader_gui.py"
BUILD_DIR="build_deck"

source .venv_deck/bin/activate

echo "🚀 Buduję aplikację $APP_NAME (OneFile) - wersja Generic/Zen2"

# Czyszczenie
rm -rf "$BUILD_DIR" dist __pycache__ *.build *.dist *.onefile-build *.onefile-dist || true
rm -rf "$HOME/.cache/Nuitka"

# FLAGA 1: Architektura.
# Wymuszamy x86-64-v3 (obsługiwane przez Steam Deck).
# -mtune=generic zapobiega optymalizacjom pod Twój Zen 4.
export CFLAGS="-march=x86-64-v3 -mtune=generic"
export CXXFLAGS="-march=x86-64-v3 -mtune=generic"

# FLAGA 2: Linker
# -rdynamic naprawia błąd "undefined symbol: PyList_New"
export LDFLAGS="-rdynamic"

python -m nuitka \
  --onefile \
  --follow-imports \
  --enable-plugin=tk-inter \
  --enable-plugin=pylint-warnings \
  --output-dir="$BUILD_DIR" \
  --static-libpython=yes \
  --show-progress \
  --show-memory \
  --assume-yes-for-downloads \
  --lto=no \
  --jobs=$(nproc) \
  --include-package=thefuzz \
  --include-package=PIL \
  --include-package=pyscreenshot \
  "$ENTRY_FILE" \
  -o "$APP_NAME"

echo "✅ Gotowe! Plik znajduje się w katalogu $BUILD_DIR"