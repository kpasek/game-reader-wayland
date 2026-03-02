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
    
    # Tworzymy wirtualne środowisko wewnątrz kontenera (aby nie śmiecić systemowym pythonem kontenera, choć w Dockerze to mniej istotne)
    # W tym przypadku możemy użyć globalnego środowiska w kontenerze, bo jest on efemeryczny, ale venv jest bezpieczniejszy dla niektórych narzędzi.
    python -m venv .venv-build
    source .venv-build/bin/activate

    echo '--- [Container] Instalacja zależności Python ---'
    # Odinstalowujemy potencjalnie zainstalowane wersje z cache (żeby wymusić reinstalację później)
    pip uninstall -y pipewire-capture || true
    # Filtrujemy pipewire-capture z requirements - budujemy go ręcznie
    grep -v 'pipewire-capture' requirements.txt > requirements_build.tmp
    # Instalujemy resztę. Używamy cache pip jeśli zamontowany volume (opcjonalnie), tutaj prosto.
    pip install -r requirements_build.tmp
    rm requirements_build.tmp
    # Upewnij się, że pyinstaller/maturin są dostępne w venv (mogły być zainstalowane globalnie w Dockerfile, ale venv je przykrył)
    pip install maturin pyinstaller

    echo '--- [Container] Budowanie pipewire-capture ze źródeł ---'
    if [ -d \"vendor/pipewire-capture\" ]; then
        cd vendor/pipewire-capture
        # Czyścimy stare buildy, aby uniknąć konfliktów i starych bibliotek z auditwheel
        echo '--- [Container] Czyszczenie cargo ---'
        cargo clean || true
        rm -rf target/wheels
        
        # Budujemy wheel. Flaga --strip zmniejsza rozmiar.
        # WAŻNE: 'maturin build' może wyprodukować wiele wheel (linux, manylinux etc.)
        # Używamy --auditwheel skip, aby nie próbował bundlować bibliotek systemowych (libpipewire),
        # które i tak muszą być w systemie hosta.
        
        maturin build --release --strip --auditwheel skip
        
        # Instalujemy PIERWSZY znaleziony plik .whl
        # Ponieważ używamy --auditwheel skip, powstanie wheel typu 'linux_x86_64', nie 'manylinux'
        WHEEL_FILE=\$(ls target/wheels/*.whl 2>/dev/null | head -n 1)
        
        if [ -z \"\$WHEEL_FILE\" ]; then
            echo '❌ Błąd: Nie znaleziono zbudowanego paczki wheel dla pipewire-capture!'
            exit 1
        fi
        
        echo \"📦 Instaluję wheel: \$WHEEL_FILE\"
        pip install \"\$WHEEL_FILE\" --force-reinstall
        
        cd ../..
    else
        echo '⚠️ Ostrzeżenie: Brak katalogu vendor/pipewire-capture'
    fi

    echo '--- [Container] Budowanie binarki (PyInstaller) ---'
    mkdir -p $DIST_DIR
    
    pyinstaller --noconfirm --onefile --windowed --clean \
        --name \"$BINARY_NAME\" \
        --collect-all \"customtkinter\" \
        --hidden-import \"PIL._tkinter_finder\" \
        --add-data \"app_config.json:.\" \
        lektor.py

    echo '--- [Container] Zakończono! ---'
"

echo "✅ Binarka gotowa: $DIST_DIR/$BINARY_NAME"
