
import io
import os
import queue
import sys
import threading
import time

import pygame
from pydub import AudioSegment

class PlayerThread(threading.Thread):
    """Wątek, który obsługuje odtwarzanie audio z kolejki z dynamiczną prędkością."""
    def __init__(self, stop_event: threading.Event, audio_queue):
        super().__init__(daemon=True)
        self.stop_event = stop_event
        self.audio_queue = audio_queue
        self.name = "PlayerThread"
        print("Inicjalizacja wątku odtwarzacza...")

    def run(self):
        pygame.mixer.init()
        print("Odtwarzacz audio uruchomiony.")
        
        while not self.stop_event.is_set():
            try:
                file_path = self.audio_queue.get(timeout=0.5)
            except queue.Empty:
                continue

            if not os.path.exists(file_path):
                print(f"OSTRZEŻENIE: Nie znaleziono pliku audio: {file_path}", file=sys.stderr)
                self.audio_queue.task_done()
                continue
            
            # Twórz bufor poza blokiem try, aby 'finally' zawsze miało do niego dostęp
            temp_wav = io.BytesIO()
            try:
                # 1. Sprawdź rozmiar kolejki
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

                # 2. Załaduj dźwięk przez pydub
                sound = AudioSegment.from_ogg(file_path)

                # 3. Przyspiesz, jeśli trzeba
                if speed > 1.0:
                    sound = sound.speedup(playback_speed=speed)

                # 4. Wyeksportuj do bufora (BEZ 'WITH')
                sound.export(temp_wav, format="wav")
                temp_wav.seek(0)

                # 5. Załaduj z bufora i odtwórz
                pygame.mixer.music.load(temp_wav)
                pygame.mixer.music.play()
                
                # 6. Czekaj na koniec odtwarzania (bufor 'temp_wav' jest wciąż otwarty)
                while pygame.mixer.music.get_busy() and not self.stop_event.is_set():
                    time.sleep(0.1)
                    
            except Exception as e:
                print(
                    f"BŁĄD: Nie można przetworzyć/odtworzyć pliku {file_path}: {e}", file=sys.stderr)
            finally:
                # 7. ZAWSZE zamknij bufor i oznacz zadanie jako wykonane
                temp_wav.close()
                self.audio_queue.task_done()
        
        pygame.mixer.quit()
        print("Odtwarzacz audio zatrzymany.")
