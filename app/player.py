import os
import queue
import sys
import threading
import time
import subprocess
import shutil

class PlayerThread(threading.Thread):
    """
    Wątek, który obsługuje odtwarzanie audio z kolejki z dynamiczną prędkością,
    używając do tego odtwarzacza systemowego (mpv lub ffplay) 
    w celu uzyskania wysokiej jakości i niskich opóźnień.
    """

    def __init__(self, stop_event: threading.Event, audio_queue):
        super().__init__(daemon=True)
        self.stop_event = stop_event
        self.audio_queue = audio_queue
        self.name = "PlayerThread"
        self.player_executable = None
        self.player_type = None  # 'mpv' lub 'ffplay'

        # Sprawdź dostępne odtwarzacze systemowe
        self.find_system_player()
        
        if not self.player_executable:
            self.stop_event.set() # Uniemożliwia uruchomienie wątku run()

    def find_system_player(self):
        """Wyszukuje 'mpv' (preferowany) lub 'ffplay' w PATH."""
        
        # 1. Sprawdź 'mpv'
        self.player_executable = shutil.which("mpv")
        if self.player_executable:
            self.player_type = "mpv"
            print(f"Odtwarzacz audio: Znaleziono 'mpv' w {self.player_executable}")
            return

        # 2. Sprawdź 'ffplay'
        self.player_executable = shutil.which("ffplay")
        if self.player_executable:
            self.player_type = "ffplay"
            print(f"Odtwarzacz audio: Znaleziono 'ffplay' w {self.player_executable}")
            return

        # 3. Brak odtwarzacza
        print("BŁĄD KRYTYCZNY: Nie znaleziono odtwarzacza 'mpv' ani 'ffplay'.", file=sys.stderr)
        print("Proszę zainstalować 'mpv' (rekomendowane) lub 'ffmpeg' (dostarcza ffplay).", file=sys.stderr)
        print("Np. 'sudo apt install mpv'", file=sys.stderr)


    def run(self):
        if not self.player_executable:
            print("Odtwarzacz audio: Brak wymaganego odtwarzacza systemowego. Wątek zatrzymany.", file=sys.stderr)
            return

        print(f"Odtwarzacz audio uruchomiony (używa: {self.player_type}).")

        while not self.stop_event.is_set():
            try:
                # Pobierz plik z kolejki
                file_path = self.audio_queue.get(timeout=0.5)
            except queue.Empty:
                continue

            # Sprawdź czy nie było sygnału stop podczas oczekiwania
            if self.stop_event.is_set():
                break

            if not os.path.exists(file_path):
                print(f"OSTRZEŻENIE: Nie znaleziono pliku audio: {file_path}", file=sys.stderr)
                self.audio_queue.task_done()
                continue

            process = None
            try:
                # 1. Sprawdź rozmiar kolejki (ta sama logika)
                queue_size = self.audio_queue.qsize()

                if queue_size >= 3:
                    speed = 1.3
                elif queue_size == 2:
                    speed = 1.2
                elif queue_size == 1:
                    speed = 1.1
                else:
                    speed = 1.0

                print(
                    f"Odtwarzam: {os.path.basename(file_path)} (Kolejka: {queue_size}, Prędkość: {speed}x)")

                # 2. Zbuduj polecenie systemowe
                cmd = [self.player_executable]
                
                if self.player_type == "mpv":
                    cmd.extend([
                        f"--speed={speed}",      # Ustaw prędkość
                        "--no-video",           # Tryb audio
                        "--audio-display=no",   # Nie pokazuj GUI/konsoli mpv
                        "--volume=130",
                        "--really-quiet",       # Tłum wyjście konsoli
                        file_path
                    ])
                else:  # "ffplay"
                    cmd.extend([
                        "-autoexit",            # Wyjdź po zakończeniu
                        "-nodisp",              # Brak okna
                        "-loglevel", "quiet",   # Tłum wyjście konsoli
                        "-af", f"atempo={speed}", # Filtr prędkości audio (zachowuje ton)
                        file_path
                    ])

                # 3. Uruchom proces i czekaj na zakończenie
                # Używamy Popen i pętli poll(), aby móc zareagować na stop_event
                process = subprocess.Popen(
                    cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

                # Czekaj na zakończenie procesu, sprawdzając co chwilę stop_event
                while process.poll() is None and not self.stop_event.is_set():
                    time.sleep(0.05) # Krótka przerwa, aby nie obciążać CPU

                # Jeśli pętla się skończyła, sprawdź dlaczego
                if self.stop_event.is_set() and process.poll() is None:
                    # Przerwano z zewnątrz - zabij proces
                    print("Odtwarzacz audio: Sygnał stop, przerywam odtwarzanie.")
                    process.terminate()
                    try:
                        process.wait(timeout=0.5)
                    except subprocess.TimeoutExpired:
                        process.kill()

            except Exception as e:
                print(
                    f"BŁĄD: Nie można odtworzyć pliku {file_path} przez {self.player_type}: {e}", file=sys.stderr)
                if process and process.poll() is None:
                    process.kill() # Na wszelki wypadek
            finally:
                self.audio_queue.task_done()

        print("Odtwarzacz audio zatrzymany.")