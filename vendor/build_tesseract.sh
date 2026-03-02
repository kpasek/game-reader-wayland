#!/usr/bin/env bash

set -e

echo "Budowanie paczki Tesseract-OCR dla Steam Deck (Debian)..."

# Przejdź do głównego katalogu (tam gdzie jest README.md/pyproject.toml) jeśli odpalono skrypt bedąc w vendor
cd "$(dirname "$0")/.."

podman run --rm -v "$PWD":/app:Z -w /app python:3.12-bookworm bash -c "
    apt-get update -qq
    apt-get install -y -qq tesseract-ocr curl xz-utils

    echo \"Tworzenie struktury katalogów...\"
    v_dir='vendor/tesseract_deck'
    rm -rf \$v_dir
    mkdir -p \$v_dir/lib \$v_dir/tessdata

    tesseract_path=\$(which tesseract)
    echo \"Kopiowanie \${tesseract_path}...\"
    cp \${tesseract_path} \$v_dir/tesseract.bin

    echo \"Pobieranie zależności...\"
    ldd \${tesseract_path} | awk '/=>/ {print \$3}' | grep -v 'libc.so' | grep -v 'ld-linux' | xargs -I '{}' cp -v '{}' \$v_dir/lib/

    echo \"Pobieranie modeli językowych (pol, eng, osd - standard)...\"
    # Używamy standardowych modeli (nie fast), aby poprawić jakość na trudnych obrazach
    curl -sL https://github.com/tesseract-ocr/tessdata/raw/main/pol.traineddata -o \$v_dir/tessdata/pol.traineddata
    curl -sL https://github.com/tesseract-ocr/tessdata/raw/main/eng.traineddata -o \$v_dir/tessdata/eng.traineddata
    curl -sL https://github.com/tesseract-ocr/tessdata/raw/main/osd.traineddata -o \$v_dir/tessdata/osd.traineddata

    echo \"Tworzenie nowej binarki opakowującej...\"
    cat << 'WRAPPER' > \$v_dir/tesseract
#!/bin/bash
DIR=\"\$( cd \"\$( dirname \"\${BASH_SOURCE[0]}\" )\" && pwd )\"
export LD_LIBRARY_PATH=\"\$DIR/lib:\$LD_LIBRARY_PATH\"
export TESSDATA_PREFIX=\"\$DIR/tessdata\"
exec \"\$DIR/tesseract.bin\" \"\$@\"
WRAPPER
    
    chmod +x \$v_dir/tesseract
    
    echo \"Pakowanie do archiwum (opcjonalnie)...\"
    cd vendor
    tar -cJf tesseract_deck.tar.xz tesseract_deck
    
    echo \"Paczka vendor/tesseract_deck jest gotowa!\"
"
