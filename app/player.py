import os
import queue
import sys
import threading
import time
import subprocess
import shutil


class PlayerThread(threading.Thread):
    """
    Wątek obsługujący odtwarzanie audio z dynamiczną prędkością i głośnością.
    """

    def __init__(self, stop_event: threading.Event, audio_queue, base_speed_callback=None, volume_callback=None):
        super().__init__(daemon=True)
        self.stop_event = stop_event
        self.audio_queue = audio_queue
        self.base_speed_callback = base_speed_callback
        self.volume_callback = volume_callback  # Nowy callback do głośności
        self.name = "PlayerThread"
        self.player_executable = None
        self.player_type = None

        self.find_system_player()

        if not self.player_executable:
            self.stop_event.set()

    def find_system_player(self):
        self.player_executable = shutil.which("mpv")
        if self.player_executable:
            self.player_type = "mpv"
            print(f"Odtwarzacz audio: Znaleziono 'mpv' w {self.player_executable}")
            return

        self.player_executable = shutil.which("ffplay")
        if self.player_executable:
            self.player_type = "ffplay"
            print(f"Odtwarzacz audio: Znaleziono 'ffplay' w {self.player_executable}")
            return

        print("BŁĄD KRYTYCZNY: Nie znaleziono odtwarzacza 'mpv' ani 'ffplay'.", file=sys.stderr)

    def run(self):
        if not self.player_executable:
            return

        print(f"Odtwarzacz audio uruchomiony (używa: {self.player_type}).")

        while not self.stop_event.is_set():
            try:
                file_path = self.audio_queue.get(timeout=0.5)
            except queue.Empty:
                continue

            if self.stop_event.is_set():
                break

            if not os.path.exists(file_path):
                self.audio_queue.task_done()
                continue

            process = None
            try:
                queue_size = self.audio_queue.qsize()

                base_speed = self.base_speed_callback() if self.base_speed_callback else 1.3
                volume_factor = self.volume_callback() if self.volume_callback else 1.0  # Domyślnie 1.0

                if queue_size >= 3:
                    speed_multiplier = 1.3
                elif queue_size == 2:
                    speed_multiplier = 1.15
                else:
                    speed_multiplier = 1.0

                speed = base_speed * speed_multiplier
                speed = max(0.8, min(speed, 2.0))

                # Ograniczenie głośności (bezpiecznik)
                volume_factor = max(0.1, min(volume_factor, 2.0))

                print(
                    f"Odtwarzam: {os.path.basename(file_path)} (S: {speed:.2f}x, V: {volume_factor:.2f})")

                cmd = [self.player_executable]

                if self.player_type == "mpv":
                    mpv_vol = int(volume_factor * 100)
                    cmd.extend([
                        f"--speed={speed}",
                        "--no-video",
                        "--audio-display=no",
                        f"--volume={mpv_vol}",  # Ustawienie głośności
                        "--really-quiet",
                        file_path
                    ])
                else:  # "ffplay"
                    cmd.extend([
                        "-autoexit",
                        "-nodisp",
                        "-loglevel", "quiet",
                        "-af", f"volume={volume_factor},atempo={speed}",
                        file_path
                    ])

                process = subprocess.Popen(
                    cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

                while process.poll() is None and not self.stop_event.is_set():
                    time.sleep(0.05)

                if self.stop_event.is_set() and process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=0.5)
                    except subprocess.TimeoutExpired:
                        process.kill()

            except Exception as e:
                print(f"BŁĄD odtwarzania: {e}", file=sys.stderr)
                if process and process.poll() is None:
                    process.kill()
            finally:
                self.audio_queue.task_done()

        print("Odtwarzacz audio zatrzymany.")