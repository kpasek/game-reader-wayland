#!/usr/bin/env bash
set -e

# ===================================================================================
# Skrypt budujący TYLKO aplikację (binary) dla Steam Deck / Linux
# Używa dedykowanego obrazu Docker/Podman zdefiniowanego w Dockerfile.build
# ===================================================================================

IMAGE_NAME="game-reader-builder:latest"
DOCKERFILE="Dockerfile.build"
WORK_DIR="/app"
DIST_DIR="dist"
BINARY_NAME="lektor"

echo "=== [1/3] Inicjalizacja silnika kontenerów ==="

if command -v podman &> /dev/null; then
    ENGINE="podman"
elif command -v docker &> /dev/null; then
    ENGINE="docker"
else
    echo "❌ Błąd: Nie znaleziono 'podman' ani 'docker'. Zainstaluj jeden z nich."
    exit 1
fi

echo "🔧 Używany silnik: $ENGINE"

echo "=== [2/3] Budowanie obrazu buildera (cacheowane) ==="
$ENGINE build -t "$IMAGE_NAME" -f "$DOCKERFILE" .

echo "=== [3/3] Budowanie aplikacji w kontenerze ==="

$ENGINE run --rm \
    -v "$(pwd):$WORK_DIR:Z" \
    -w "$WORK_DIR" \
    "$IMAGE_NAME" \
    /bin/bash -c "
    set -e
    
    python -m venv .venv-build
    source .venv-build/bin/activate

    echo '--- [Container] Instalacja zależności Python ---'
    pip uninstall -y pipewire-capture || true
    grep -v 'pipewire-capture' requirements.txt > requirements_build.tmp
    pip install -r requirements_build.tmp
    rm requirements_build.tmp
    pip install maturin pyinstaller

    echo '--- [Container] Budowanie pipewire-capture ze źródeł ---'
    if [ -d \"vendor/pipewire-capture\" ]; then
        cd vendor/pipewire-capture
        cargo clean || true
        rm -rf target/wheels
        
        # Używamy flagi --auditwheel skip, aby nie dołączać bibliotek systemowych (np. libpipewire)
        # do paczki wheel. Dzięki temu aplikacja na Steam Decku użyje systemowego PipeWire'a.
        maturin build --release --strip --auditwheel skip
        
        WHEEL_FILE=\$(ls target/wheels/*.whl 2>/dev/null | head -n 1)
        if [ -z \"\$WHEEL_FILE\" ]; then
            echo '❌ Błąd: Nie znaleziono zbudowanego paczki wheel!'
            exit 1
        fi
        
        echo \"📦 Instaluję wheel: \$WHEEL_FILE\"
        pip install \"\$WHEEL_FILE\" --force-reinstall
        cd ../..
    fi

    echo '--- [Container] Budowanie binarki (PyInstaller) ---'
    mkdir -p $DIST_DIR
    
    # Powrót do standardowej metody budowania (bez manipulacji plikiem .spec)
    pyinstaller --noconfirm --onefile --windowed --clean \
        --name \"$BINARY_NAME\" \
        --collect-all \"customtkinter\" \
        --hidden-import \"PIL._tkinter_finder\" \
        --add-data \"app_config.json:.\" \
        lektor.py

    echo '--- [Container] Zakończono! ---'
"

echo "✅ Binarka gotowa: $DIST_DIR/$BINARY_NAME"
