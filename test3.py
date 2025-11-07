import cv2
import pytesseract
import numpy as np
import subprocess
from rapidfuzz import fuzz, process

# ⚙️ konfiguracja
TARGET_REGION = (100, 800, 900, 200)  # x, y, width, height
DIALOG_FILE = "subtitles.txt"
AUDIO_DIR = "audio/"
THRESHOLD = 85  # dopasowanie procentowe
CAPTURE_INTERVAL = 0.5

# 🔊 komenda do odtwarzania audio
def play_audio(name):
    subprocess.Popen(["ffplay", "-nodisp", "-autoexit", f"{AUDIO_DIR}/{name}.ogg"],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

# 📄 wczytanie dialogów
with open(DIALOG_FILE, "r", encoding="utf-8") as f:
    dialogs = [line.strip() for line in f if line.strip()]

# 🎥 GStreamer — PipeWire capture (z portalu)
cap = cv2.VideoCapture("pipewiresrc ! videoconvert ! appsink", cv2.CAP_GSTREAMER)

if not cap.isOpened():
    raise RuntimeError("❌ Nie udało się otworzyć PipeWire streamu")

print("✅ Stream uruchomiony, trwa OCR...")

last_match = None
while True:
    ret, frame = cap.read()
    if not ret:
        continue

    # 📍 przycięcie fragmentu
    x, y, w, h = TARGET_REGION
    roi = frame[y:y+h, x:x+w]

    # 🔤 OCR
    text = pytesseract.image_to_string(roi, lang="pol").strip()
    if not text:
        continue

    # 🧠 dopasowanie do dialogów
    match, score, _ = process.extractOne(text, dialogs, scorer=fuzz.token_set_ratio)
    if score >= THRESHOLD and match != last_match:
        print(f"🟢 Dopasowano: {match} ({score}%)")
        # play_audio(match)
        last_match = match
