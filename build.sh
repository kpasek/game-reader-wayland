#!/usr/bin/env bash
set -e

# -------------------------
# Konfiguracja builda Nuitka
# -------------------------

APP_NAME="lektor"
ENTRY_FILE="lektor.py"
BUILD_DIR="build"

# Opcjonalnie: aktywuj wirtualne środowisko, jeśli masz
source .venv/bin/activate

echo "🚀 Buduję aplikację $APP_NAME przy użyciu Nuitka..."

# Wyczyść poprzednie buildy
rm -rf "$BUILD_DIR" dist __pycache__ *.build *.dist *.onefile-build *.onefile-dist || true

# -------------------------
# Kompilacja
# -------------------------
python -m nuitka \
  --standalone \
  --onefile \
  --follow-imports \
  --enable-plugin=tk-inter \
  --enable-plugin=pylint-warnings \
  --remove-output \
  --output-dir="$BUILD_DIR" \
  --clang \
  --show-progress \
  --show-memory \
  --assume-yes-for-downloads \
  --lto=yes \
  --jobs=$(nproc) \
  --include-package=thefuzz \
  --include-package=mss \
  "$ENTRY_FILE" \
  -o "$APP_NAME"

# -------------------------
# Wynik
# -------------------------
echo ""
echo "✅ Kompilacja zakończona!"
echo "Plik wynikowy: $BUILD_DIR/$APP_NAME"
echo ""
ls -lh "$BUILD_DIR/$APP_NAME"
