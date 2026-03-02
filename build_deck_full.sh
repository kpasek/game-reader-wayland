#!/usr/bin/env bash
set -e

DIST_PACKAGE_DIR="dist_steamdeck"
BINARY_NAME="lektor"
ZIP_NAME="lektor_steamdeck.zip"

echo "=== [1/3] Budowanie aplikacji (build_deck.sh) ==="
./build_deck.sh

echo "=== [2/3] Budowanie/Sprawdzanie Tesseract (vendor/build_tesseract.sh) ==="
if [ ! -d "vendor/tesseract_deck" ]; then
    echo "Folder vendor/tesseract_deck nie istnieje. Uruchamiam budowanie..."
    ./vendor/build_tesseract.sh
else
    echo "Folder vendor/tesseract_deck już istnieje. Pomijam budowanie (usuń go, aby wymusić przebudowę)."
fi

echo "=== [3/3] Tworzenie paczki dystrybucyjnej ==="

# Tworzenie czystego katalogu
rm -rf "$DIST_PACKAGE_DIR"
mkdir -p "$DIST_PACKAGE_DIR"

# Kopiowanie binarki
cp "dist/$BINARY_NAME" "$DIST_PACKAGE_DIR/"

# Kopiowanie Tesseract (cały folder)
# Docelowa struktura na decku:
# .
# ├── lektor
# ├── vendor
# │   └── tesseract_deck

mkdir -p "$DIST_PACKAGE_DIR/vendor"
cp -r "vendor/tesseract_deck" "$DIST_PACKAGE_DIR/vendor/"

# Tworzenie ZIP
echo "Pakowanie do $ZIP_NAME..."
cd "$DIST_PACKAGE_DIR"
zip -r "../$ZIP_NAME" .
cd ..

echo " "
echo "✅ Gotowe!"
echo "Paczka: $ZIP_NAME"
echo "Zawartość paczki:"
unzip -l "$ZIP_NAME"
