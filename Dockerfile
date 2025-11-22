# Używamy starszego obrazu (np. Ubuntu 20.04 lub Python 3.10 slim), 
# aby GLIBC było kompatybilne ze Steam Deckiem.
FROM python:3.10-slim-bullseye

# Instalacja zależności systemowych (kompilator, tkinter, biblioteki graficzne)
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    ccache \
    python3-tk \
    tk-dev \
    tcl-dev \
    libffi-dev \
    libx11-dev \
    patchelf \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Instalacja zależności Pythona
# Zakładam, że masz requirements.txt, jeśli nie - wpisz pakiety ręcznie
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install nuitka

# Kopiowanie kodu źródłowego (katalog app i pliki)
COPY app/ ./
COPY *.py .
COPY *.json .

# Budowanie (bez flag CPU, w kontenerze to bezpieczne)
RUN python -m nuitka \
    --standalone \
    --onefile \
    --follow-imports \
    --enable-plugin=tk-inter \
    --include-package=thefuzz \
    --output-dir=/build \
    --remove-output \
    game_reader_gui.py \
    -o reader_deck

# Po zakończeniu kontenera nic się nie dzieje, plik czeka w /build