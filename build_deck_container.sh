#!/usr/bin/env bash
set -e

echo "Budowanie aplikacji dla Steam Deck korzystajac z Podman (Debian 12 / glibc 2.36)"

podman run --rm -it -v "$PWD":/app:Z -w /app python:3.12-bookworm /bin/bash -c "
    set -e

    echo \"Sprzatanie starych plikow ze srodowiska (cache)...\"
    rm -rf .venv-bookworm
    rm -rf vendor/pipewire-capture/target
    rm -rf build/lektor dist/lektor

    echo \"Aktualizacja repo w kontenerze...\"
    apt-get update -qq

    echo \"Instalowanie zaleznosci systemowych...\"
    apt-get install -y -qq jq tesseract-ocr python3-tk libpipewire-0.3-dev pkg-config curl clang libclang-dev

    echo \"Instalowanie Rust...\"
    export RUSTUP_HOME=/opt/rust
    export CARGO_HOME=/opt/rust
    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --default-toolchain stable --profile minimal
    export PATH=/opt/rust/bin:\$PATH

    echo \"Ustawienie venv...\"
    python -m venv .venv-bookworm
    source .venv-bookworm/bin/activate

    echo \"Instalacja pip i maturin...\"
    pip install --upgrade pip maturin
    
    if [ -f requirements.txt ]; then
        pip install -r requirements.txt
    fi

    echo \"Budowanie pipewire-capture ze zrodel (czysty build bez auditwheel)...\"
    cd vendor/pipewire-capture
    maturin build --release --auditwheel skip
    
    echo \"Instalacja pipewire-capture...\"
    pip install target/wheels/*.whl
    cd ../..

    echo \"Instalacja do budowy pyinstaller...\"
    pip install pyinstaller customtkinter Pillow thefuzz mss 

    echo \"Uruchamianie pyinstallera w kontenerze...\"
    sed -i 's/VENV_DIR=\".venv-deck\"/VENV_DIR=\".venv-bookworm\"/' build_pyinstaller.sh
    
    ./build_pyinstaller.sh
    
    sed -i 's/VENV_DIR=\".venv-bookworm\"/VENV_DIR=\".venv-deck\"/' build_pyinstaller.sh

    echo \"Gotowe!\"
"

echo "Zakonczono. Pliczki wynikowe:"
ls -lh dist_pyinstaller/
