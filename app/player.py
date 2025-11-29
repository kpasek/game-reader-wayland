import threading
import queue
import subprocess
import time
import os
import sys
import platform


class PlayerThread(threading.Thread):
    def __init__(self, stop_event, audio_queue, base_speed_callback=None, volume_callback=None):
        super().__init__(daemon=True)
        self.stop_event = stop_event
        self.audio_queue = audio_queue
        self.base_speed_callback = base_speed_callback
        self.volume_callback = volume_callback
        self.current_process = None

    def _get_startup_info(self):
        """
        Zwraca strukturę STARTUPINFO dla Windows, aby ukryć okno terminala
        procesu potomnego (ffplay).
        """
        if platform.system() == "Windows":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0  # SW_HIDE
            return startupinfo
        return None

    def run(self):
        while not self.stop_event.is_set():
            try:
                # Czekamy na plik audio w kolejce (z timeoutem, by sprawdzać stop_event)
                audio_file = self.audio_queue.get(timeout=0.5)
            except queue.Empty:
                continue

            if not os.path.exists(audio_file):
                print(f"Błąd: Plik audio nie istnieje: {audio_file}")
                continue

            # Pobieramy aktualne ustawienia
            speed = self.base_speed_callback() if self.base_speed_callback else 1.0
            volume = self.volume_callback() if self.volume_callback else 1.0

            # Budowanie komendy dla ffplay
            # -nodisp: brak okna wideo
            # -autoexit: zamknij po odtworzeniu
            # -af: filtry audio (prędkość, głośność)

            # Formatowanie filtra atempo (dla prędkości spoza zakresu 0.5-2.0 trzeba łączyć filtry,
            # ale tutaj zakładamy zakres 0.8-2.0 z GUI)
            filter_complex = f"atempo={speed},volume={volume}"

            cmd = [
                'ffplay',
                '-nodisp',
                '-autoexit',
                '-af', filter_complex,
                audio_file
            ]

            try:
                # Uruchomienie procesu z ukrytym oknem
                self.current_process = subprocess.Popen(
                    cmd,
                    startupinfo=self._get_startup_info(),
                    stdout=subprocess.DEVNULL,  # Wyślij logi w nicość
                    stderr=subprocess.DEVNULL  # Wyślij błędy w nicość
                )

                # Czekamy na zakończenie odtwarzania lub sygnał stop
                while self.current_process.poll() is None:
                    if self.stop_event.is_set():
                        self.current_process.terminate()
                        break
                    time.sleep(0.1)

            except Exception as e:
                print(f"Błąd odtwarzacza: {e}", file=sys.stderr)
            finally:
                self.current_process = None

    def stop(self):
        self.stop_event.set()
        if self.current_process:
            try:
                self.current_process.terminate()
            except:
                pass