#!/usr/bin/env bash
set -e

# -------------------------
# Konfiguracja builda Nuitka
# -------------------------

APP_NAME="lektor"
ENTRY_FILE="lektor.py"
BUILD_DIR="build"

# Domyślnie instalujemy po buildzie. Użyj --no-install aby pominąć kopiowanie.
INSTALL=true

# Parsowanie argumentów prostą pętlą (obsługuje tylko --no-install i --install)
for arg in "$@"; do
  case "$arg" in
    --no-install)
      INSTALL=false
      ;;
    --install)
      INSTALL=true
      ;;
    *)
      # inne argumenty przekazujemy dalej (np. dla przyszłych rozszerzeń)
      ;;
  esac
done

# Opcjonalnie: aktywuj wirtualne środowisko, jeśli masz
source .venv/bin/activate

echo "🚀 Buduję aplikację $APP_NAME przy użyciu Nuitka..."

# Wyczyść poprzednie buildy
#rm -rf "$BUILD_DIR" dist __pycache__ *.build *.dist *.onefile-build *.onefile-dist || true

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

if [ "$INSTALL" = true ]; then
  # -------------------------
  # Instalacja (kopiowanie do katalogu użytkownika)
  # -------------------------
  # Domyślny katalog docelowy — zawsze nadpisujemy starą wersję
  DEST_DIR="$HOME/Applications/Lektor"

  echo "\n📦 Instaluję aplikację do: $DEST_DIR"
  mkdir -p "$DEST_DIR"

  # Jeśli artefakt jest katalogiem, kopiujemy jego zawartość.
  if [ -d "$BUILD_DIR/$APP_NAME" ]; then
    cp -a "$BUILD_DIR/$APP_NAME/." "$DEST_DIR/"
    echo "Skopiowano katalog zawartości do $DEST_DIR"
  elif [ -e "$BUILD_DIR/$APP_NAME" ]; then
    # Jeśli to plik (np. --onefile), skopiuj plik do katalogu docelowego i ustaw prawa wykonywalne
    cp -a "$BUILD_DIR/$APP_NAME" "$DEST_DIR/"
    chmod +x "$DEST_DIR/$APP_NAME"
    echo "Skopiowano plik do $DEST_DIR/$APP_NAME"
  else
    echo "⚠️  Nie znaleziono artefaktu buildu: $BUILD_DIR/$APP_NAME" >&2
    exit 1
  fi

  echo "✅ Instalacja zakończona."
else
  echo "ℹ️  Instalacja pominięta (uruchomiono z --no-install)."
fi
