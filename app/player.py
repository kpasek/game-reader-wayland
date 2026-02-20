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

        self.ffplay_cmd = "ffplay"
        if platform.system() == "Linux":
            # Sprawdzenie czy w głównym katalogu znajduje się plik ffplay
            local_ffplay = os.path.abspath(os.path.join("lib", "ffplay"))
            if os.path.exists(local_ffplay):
                self.ffplay_cmd = local_ffplay

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
                # Czekamy na dane w kolejce
                data = self.audio_queue.get(timeout=0.5)
            except queue.Empty:
                continue

            # Obsługa formatu danych (Tuple vs String dla kompatybilności)
            if isinstance(data, tuple):
                audio_file, dynamic_multiplier = data
            else:
                audio_file = data
                dynamic_multiplier = 1.0

            if not os.path.exists(audio_file):
                print(f"Błąd: Plik audio nie istnieje: {audio_file}")
                continue

            # Pobieramy bazowe ustawienia z GUI
            base_speed = self.base_speed_callback() if self.base_speed_callback else 1.0
            base_volume = self.volume_callback() if self.volume_callback else 1.0

            # Wyliczamy ostateczną prędkość
            final_speed = base_speed * dynamic_multiplier

            # Zabezpieczenie dla filtra atempo (limit ffplay to 0.5 - 100.0)
            final_speed = max(0.5, min(final_speed, 100.0))

            # Budowanie komendy dla ffplay
            # Używamy final_speed w filtrze atempo
            filter_complex = f"atempo={final_speed:.2f},volume={base_volume:.2f},alimiter=limit=0.95"

            cmd = [
                self.ffplay_cmd,
                '-nodisp',
                '-autoexit',
                '-af', filter_complex,
                audio_file
            ]

            try:
                # Uruchomienie procesu z ukrytym oknem
                pass # Player log removed
                self.current_process = subprocess.Popen(
                    cmd,
                    startupinfo=self._get_startup_info(),
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
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