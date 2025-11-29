import os
import queue
import sys
import threading
import time
import subprocess
import shutil


class PlayerThread(threading.Thread):
    """
    Wątek odtwarzający audio. Obsługuje mpv i ffplay.
    Dynamicznie zmienia prędkość odtwarzania w zależności od kolejki (catch-up).
    """

    def __init__(self, stop_event: threading.Event, audio_queue: queue.Queue,
                 base_speed_callback=None, volume_callback=None):
        super().__init__(daemon=True)
        self.name = "PlayerThread"
        self.stop_event = stop_event
        self.audio_queue = audio_queue
        self.base_speed_callback = base_speed_callback
        self.volume_callback = volume_callback

        self.player_exe = None
        self.player_type = None
        self._detect_player()

    def _detect_player(self):
        # 1. Sprawdź folder lokalny aplikacji (dla wersji portable na Windows)
        local_ffplay = os.path.join(os.getcwd(), "bin", "ffplay.exe")
        if os.path.exists(local_ffplay):
            self.player_exe = local_ffplay
            self.player_type = "ffplay"
            return

        # 2. Sprawdź systemowy PATH
        if shutil.which("mpv"):
            self.player_exe = shutil.which("mpv")
            self.player_type = "mpv"
        elif shutil.which("ffplay"):
            self.player_exe = shutil.which("ffplay")
            self.player_type = "ffplay"
        else:
            # Na Windowsie, jeśli brak mpv, warto wyświetlić popup zamiast cichego błędu w konsoli
            print("BŁĄD: Nie znaleziono odtwarzacza (mpv/ffplay).", file=sys.stderr)

    def run(self):
        if not self.player_exe: return
        print(f"PlayerThread startuje ({self.player_type}).")

        while not self.stop_event.is_set():
            try:
                # Czekamy krótko na plik, by móc sprawdzić stop_event
                file_path = self.audio_queue.get(timeout=0.5)
            except queue.Empty:
                continue

            if not os.path.exists(file_path):
                self.audio_queue.task_done()
                continue

            # Obliczanie parametrów
            base_speed = self.base_speed_callback() if self.base_speed_callback else 1.0
            volume = self.volume_callback() if self.volume_callback else 1.0

            # Algorytm nadrabiania zaległości
            q_size = self.audio_queue.qsize()
            catch_up_mult = 1.0
            if q_size >= 3:
                catch_up_mult = 1.3
            elif q_size >= 1:
                catch_up_mult = 1.15

            final_speed = max(0.5, min(base_speed * catch_up_mult, 3.0))

            self._play_file(file_path, final_speed, volume)
            self.audio_queue.task_done()

    def _play_file(self, path: str, speed: float, volume: float):
        """Uruchamia proces odtwarzacza."""
        cmd = [self.player_exe]

        if self.player_type == "mpv":
            vol_percent = int(volume * 100)
            cmd.extend([
                f"--speed={speed}", f"--volume={vol_percent}",
                "--no-video", "--audio-display=no", "--really-quiet", path
            ])
        else:  # ffplay
            # ffplay filter syntax: volume=1.5,atempo=1.2
            filters = f"volume={volume},atempo={speed}"
            cmd.extend([
                "-nodisp", "-autoexit", "-loglevel", "quiet",
                "-af", filters, path
            ])

        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            # Czekamy na koniec lub sygnał stop
            while proc.poll() is None:
                if self.stop_event.is_set():
                    proc.terminate()
                    break
                time.sleep(0.05)
        except Exception as e:
            print(f"Błąd odtwarzania: {e}")