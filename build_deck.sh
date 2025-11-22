#!/usr/bin/env bash
set -e

APP_NAME="reader_deck"
ENTRY_FILE="game_reader_gui.py"
BUILD_DIR="build"

source .venv/bin/activate

echo "🚀 Buduję aplikację $APP_NAME przy użyciu Nuitka"

# 1. Czyszczenie cache jest absolutnie kluczowe przy zmianie kompilatora
rm -rf "$BUILD_DIR" dist __pycache__ *.build *.dist *.onefile-build *.onefile-dist || true
rm -rf "$HOME/.cache/Nuitka"

# 2. Usuwamy WSZYSTKIE flagi związane z architekturą.
# Clang sam dobierze bezpieczne ustawienia.
# unset CFLAGS
# unset CXXFLAGS

# # 3. Wymuszamy użycie Clang
# export CC=clang
# export CXX=clang++
export CFLAGS="-march=x86-64-v3"
export CXXFLAGS="-march=x86-64-v3"
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
  --show-progress \
  --show-memory \
  --assume-yes-for-downloads \
  --lto=no \
  --jobs=$(nproc) \
  --include-package=thefuzz \
  "$ENTRY_FILE" \
  -o "$APP_NAME"

echo "✅ Kompilacja zakończona!"