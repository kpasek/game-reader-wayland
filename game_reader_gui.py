#!/usr/bin/env python3
import sys
import os
import queue
import threading
import subprocess
import time
import argparse
from typing import Optional

try:
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox
except ImportError:
    print("Błąd: Brak biblioteki tkinter.", file=sys.stderr)
    sys.exit(1)

from app.config_manager import ConfigManager
from app.reader import ReaderThread
from app.player import PlayerThread
from app.log import LogWindow
from app.settings import SettingsDialog
from app.area_selector import AreaSelector
from app.capture import capture_fullscreen

# Global events/queues
stop_event = threading.Event()
audio_queue = queue.Queue()
log_queue = queue.Queue()


class GameReaderApp:
    def __init__(self, root: tk.Tk, autostart_preset: Optional[str], game_cmd: list):
        self.root = root
        self.root.title("Game Reader (Lektor Gier)")
        self.root.geometry("700x550")

        self.config_mgr = ConfigManager()
        self.game_cmd = game_cmd
        self.game_process = None

        # Wątki
        self.reader_thread = None
        self.player_thread = None
        self.log_window = None

        # Zmienne UI
        self.var_preset = tk.StringVar()
        self.var_audio_dir = tk.StringVar()
        self.var_subs_file = tk.StringVar()
        self.var_names_file = tk.StringVar()

        self.var_regex_mode = tk.StringVar()
        self.var_custom_regex = tk.StringVar()
        self.var_resolution = tk.StringVar()

        self.var_speed = tk.DoubleVar(value=1.15)
        self.var_volume = tk.DoubleVar(value=1.0)

        # Mapy
        self.regex_map = {
            "Brak": r"",
            "Standard (Imię: Dialog)": r"^(?i)({NAMES})\s*[:：\-; ]*",
            "Nawiasy ([Imię] Dialog)": r"^\[({NAMES})\]",
            "Imię na początku": r"^({NAMES})\s+",
            "Własny (Regex)": "CUSTOM"
        }

        self.resolutions = [
            "1920x1080", "2560x1440", "3840x2160",
            "1280x800", "2560x1600", "Niestandardowa"
        ]

        self._init_gui()
        self._load_initial_state(autostart_preset)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def _init_gui(self):
        # --- MENU ---
        menubar = tk.Menu(self.root)
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Ustawienia zaawansowane", command=self.open_settings)
        file_menu.add_separator()
        file_menu.add_command(label="Wyjdź", command=self.on_close)
        menubar.add_cascade(label="Plik", menu=file_menu)

        preset_menu = tk.Menu(menubar, tearoff=0)
        preset_menu.add_command(label="Wczytaj inny profil...", command=self.browse_preset)

        area_menu = tk.Menu(preset_menu, tearoff=0)
        for i in range(3):
            sub = tk.Menu(area_menu, tearoff=0)
            sub.add_command(label=f"Definiuj Obszar {i + 1}", command=lambda x=i: self.set_area(x))
            sub.add_command(label=f"Wyczyść Obszar {i + 1}", command=lambda x=i: self.clear_area(x))
            area_menu.add_cascade(label=f"Obszar {i + 1}", menu=sub)
        preset_menu.add_cascade(label="Obszary ekranu", menu=area_menu)

        preset_menu.add_separator()
        preset_menu.add_command(label="Zmień folder audio", command=lambda: self.change_path('audio_dir'))
        preset_menu.add_command(label="Zmień plik napisów", command=lambda: self.change_path('text_file_path'))
        preset_menu.add_command(label="Zmień plik imion", command=lambda: self.change_path('names_file_path'))
        menubar.add_cascade(label="Profil", menu=preset_menu)

        tools_menu = tk.Menu(menubar, tearoff=0)
        tools_menu.add_command(label="Podgląd logów", command=self.show_logs)
        menubar.add_cascade(label="Narzędzia", menu=tools_menu)

        self.root.config(menu=menubar)

        # --- GŁÓWNY PANEL ---
        panel = ttk.Frame(self.root, padding=10)
        panel.pack(fill=tk.BOTH, expand=True)

        ttk.Label(panel, text="Aktywny profil lektora:").pack(anchor=tk.W)
        self.cb_preset = ttk.Combobox(panel, textvariable=self.var_preset, state="readonly", width=60)
        self.cb_preset.pack(fill=tk.X, pady=5)
        self.cb_preset.bind("<<ComboboxSelected>>", self.on_preset_changed)

        # Regex
        grp_regex = ttk.LabelFrame(panel, text="Filtracja tekstu (Regex)", padding=5)
        grp_regex.pack(fill=tk.X, pady=10)

        f_reg = ttk.Frame(grp_regex)
        f_reg.pack(fill=tk.X)
        self.cb_regex = ttk.Combobox(f_reg, textvariable=self.var_regex_mode,
                                     values=list(self.regex_map.keys()), state="readonly", width=30)
        self.cb_regex.pack(side=tk.LEFT, padx=5)
        self.cb_regex.bind("<<ComboboxSelected>>", self.on_regex_changed)

        self.ent_regex = ttk.Entry(f_reg, textvariable=self.var_custom_regex, state="disabled")
        self.ent_regex.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        self.ent_regex.bind("<FocusOut>",
                            lambda e: self.config_mgr.update_setting('last_custom_regex', self.var_custom_regex.get()))

        # Rozdzielczość
        ttk.Label(panel, text="Rozdzielczość gry (dla skalowania obszarów):").pack(anchor=tk.W)
        self.cb_res = ttk.Combobox(panel, textvariable=self.var_resolution, values=self.resolutions)
        self.cb_res.pack(fill=tk.X, pady=5)
        self.cb_res.bind("<FocusOut>",
                         lambda e: self.config_mgr.update_setting('last_resolution_key', self.var_resolution.get()))

        # Audio Controls
        grp_audio = ttk.LabelFrame(panel, text="Kontrola Audio", padding=10)
        grp_audio.pack(fill=tk.X, pady=10)

        # Speed
        ttk.Label(grp_audio, text="Prędkość:").grid(row=0, column=0)
        s_speed = ttk.Scale(grp_audio, from_=0.8, to=2.0, variable=self.var_speed,
                            command=lambda v: self.lbl_speed.config(text=f"{float(v):.2f}x"))
        s_speed.grid(row=0, column=1, sticky="ew", padx=10)
        s_speed.bind("<ButtonRelease-1>",
                     lambda e: self._save_preset_val("audio_speed", round(self.var_speed.get(), 2)))
        self.lbl_speed = ttk.Label(grp_audio, text="1.15x", width=6)
        self.lbl_speed.grid(row=0, column=2)

        # Volume
        ttk.Label(grp_audio, text="Głośność:").grid(row=1, column=0)
        s_vol = ttk.Scale(grp_audio, from_=0.0, to=1.5, variable=self.var_volume,
                          command=lambda v: self.lbl_vol.config(text=f"{float(v):.2f}"))
        s_vol.grid(row=1, column=1, sticky="ew", padx=10)
        s_vol.bind("<ButtonRelease-1>",
                   lambda e: self._save_preset_val("audio_volume", round(self.var_volume.get(), 2)))
        self.lbl_vol = ttk.Label(grp_audio, text="1.00", width=6)
        self.lbl_vol.grid(row=1, column=2)

        grp_audio.columnconfigure(1, weight=1)

        # Buttons
        frm_btn = ttk.Frame(panel)
        frm_btn.pack(side=tk.BOTTOM, fill=tk.X, pady=10)
        self.btn_start = ttk.Button(frm_btn, text="START", command=self.start_reading)
        self.btn_start.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        self.btn_stop = ttk.Button(frm_btn, text="STOP", command=self.stop_reading, state="disabled")
        self.btn_stop.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)

    def _load_initial_state(self, autostart_path):
        # Ładowanie ostatnich presetów do comboboxa
        recents = self.config_mgr.get('recent_presets', [])
        self.cb_preset['values'] = recents

        # Wybór presetu
        initial_preset = autostart_path if autostart_path else (recents[0] if recents else "")
        if initial_preset and os.path.exists(initial_preset):
            self.var_preset.set(initial_preset)
            self.on_preset_changed()
            if autostart_path:
                self.root.after(500, self.start_reading)

        # Reszta ustawień globalnych
        self.var_regex_mode.set(self.config_mgr.get('last_regex_mode', "Standard (Imię: Dialog)"))
        self.var_custom_regex.set(self.config_mgr.get('last_custom_regex', ""))
        self.var_resolution.set(self.config_mgr.get('last_resolution_key', "1920x1080"))
        self.on_regex_changed()

    # --- LOGIKA GUI ---

    def on_preset_changed(self, event=None):
        path = self.var_preset.get()
        if not path or not os.path.exists(path): return

        data = self.config_mgr.load_preset(path)
        self.var_speed.set(data.get("audio_speed", 1.15))
        self.lbl_speed.config(text=f"{self.var_speed.get():.2f}x")

        self.var_volume.set(data.get("audio_volume", 1.0))
        self.lbl_vol.config(text=f"{self.var_volume.get():.2f}")

        # Odtwórz ustawienia Regexa z presetu, jeśli są
        if "regex_mode_name" in data:
            self.var_regex_mode.set(data["regex_mode_name"])
            if data["regex_mode_name"] == "Własny (Regex)":
                self.var_custom_regex.set(data.get("regex_pattern", ""))
            self.on_regex_changed()

    def on_regex_changed(self, event=None):
        mode = self.var_regex_mode.get()
        self.ent_regex.config(state="normal" if mode == "Własny (Regex)" else "disabled")

        # Zapisz zmianę trybu globalnie
        self.config_mgr.update_setting('last_regex_mode', mode)

        # Jeśli to nie custom, zapisz od razu do presetu pattern
        if mode != "Własny (Regex)":
            pattern = self.regex_map.get(mode, "")
            self._save_preset_val("regex_pattern", pattern)
            self._save_preset_val("regex_mode_name", mode)

    def _save_preset_val(self, key, val):
        path = self.var_preset.get()
        if path and os.path.exists(path):
            data = self.config_mgr.load_preset(path)
            data[key] = val
            self.config_mgr.save_preset(path, data)

    # --- AKCJE ---

    def browse_preset(self):
        path = filedialog.askopenfilename(filetypes=[("JSON", "*.json")])
        if path:
            self.config_mgr.add_recent_preset(path)
            self.cb_preset['values'] = self.config_mgr.get('recent_presets')
            self.var_preset.set(path)
            self.on_preset_changed()

    def change_path(self, key):
        """Generyczna zmiana ścieżki w presecie (audio/txt)."""
        preset_path = self.var_preset.get()
        if not preset_path: return

        if key == 'audio_dir':
            new_path = filedialog.askdirectory()
        else:
            new_path = filedialog.askopenfilename(filetypes=[("Text", "*.txt")])

        if new_path:
            self._save_preset_val(key, new_path)
            messagebox.showinfo("Sukces", "Zaktualizowano ścieżkę w profilu.")

    def set_area(self, idx):
        preset_path = self.var_preset.get()
        if not preset_path: return messagebox.showerror("Błąd", "Wybierz profil.")

        self.root.withdraw()
        time.sleep(0.3)
        img = capture_fullscreen()
        if not img:
            self.root.deiconify()
            return

        # Logika wyświetlania starych obszarów (z ConfigManager)
        data = self.config_mgr.load_preset(preset_path)
        current_mons = data.get('monitor', [])
        if isinstance(current_mons, dict): current_mons = [current_mons]
        while len(current_mons) < 3: current_mons.append(None)

        # Przeskaluj obszary do wyświetlenia na zrzucie (jeśli screenshot jest inny niż 1080p)
        # (Tutaj uproszczona logika - zakładamy, że wyświetlamy to, co widać)

        sel = AreaSelector(self.root, img, existing_regions=[m for i, m in enumerate(current_mons) if m and i != idx])
        self.root.deiconify()

        if sel.geometry:
            # Skalowanie do 1080p przed zapisem
            sw, sh = img.size
            sx = 1920 / sw
            sy = 1080 / sh

            final_geo = {
                'left': int(sel.geometry['left'] * sx),
                'top': int(sel.geometry['top'] * sy),
                'width': int(sel.geometry['width'] * sx),
                'height': int(sel.geometry['height'] * sy)
            }
            current_mons[idx] = final_geo
            data['monitor'] = [m for m in current_mons if m]
            data['resolution'] = "1920x1080"  # Wymuszamy standard
            self.config_mgr.save_preset(preset_path, data)

    def clear_area(self, idx):
        preset_path = self.var_preset.get()
        if not preset_path: return
        data = self.config_mgr.load_preset(preset_path)
        mons = data.get('monitor', [])
        if isinstance(mons, dict): mons = [mons]

        if idx < len(mons):
            mons[idx] = None
            data['monitor'] = [m for m in mons if m]
            self.config_mgr.save_preset(preset_path, data)
            messagebox.showinfo("Info", f"Wyczyszczono obszar {idx + 1}")

    def open_settings(self):
        SettingsDialog(self.root, self.config_mgr.settings)
        self.config_mgr.save_app_config()  # Zapisz po zamknięciu dialogu

    def show_logs(self):
        if not self.log_window or not self.log_window.winfo_exists():
            self.log_window = LogWindow(self.root, log_queue)
        else:
            self.log_window.lift()

    # --- START / STOP ---

    def start_reading(self):
        path = self.var_preset.get()
        if not path or not os.path.exists(path):
            return messagebox.showerror("Błąd", "Brak poprawnego profilu.")

        self.config_mgr.add_recent_preset(path)

        # Regex
        mode = self.var_regex_mode.get()
        pattern = self.var_custom_regex.get() if mode == "Własny (Regex)" else self.regex_map.get(mode, "")

        # Rozdzielczość
        res_str = self.var_resolution.get()
        target_res = None
        if "x" in res_str:
            try:
                target_res = tuple(map(int, res_str.split('x')))
            except:
                pass

        stop_event.clear()

        # Czyszczenie kolejki audio
        with audio_queue.mutex:
            audio_queue.queue.clear()

        # Start wątków
        self.player_thread = PlayerThread(
            stop_event, audio_queue,
            base_speed_callback=lambda: self.var_speed.get(),
            volume_callback=lambda: self.var_volume.get()
        )
        self.reader_thread = ReaderThread(
            path, pattern, self.config_mgr.settings, stop_event, audio_queue,
            target_resolution=target_res, log_queue=log_queue
        )

        self.player_thread.start()
        self.reader_thread.start()

        self._toggle_ui(True)

        # Autostart Gry
        if self.game_cmd and not self.game_process:
            try:
                self.game_process = subprocess.Popen(self.game_cmd)
            except Exception as e:
                messagebox.showerror("Błąd Gry", f"Nie udało się uruchomić gry: {e}")

    def stop_reading(self):
        stop_event.set()
        if self.reader_thread: self.reader_thread.join(1.0)
        self._toggle_ui(False)

    def _toggle_ui(self, running):
        state = "disabled" if running else "normal"
        self.btn_start.config(state=state)
        self.btn_stop.config(state="normal" if running else "disabled")
        self.cb_preset.config(state="disabled" if running else "readonly")

    def on_close(self):
        if self.reader_thread and self.reader_thread.is_alive():
            self.stop_reading()
        if self.game_process:
            self.game_process.terminate()
        self.root.destroy()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--preset', type=str, help="Ścieżka do profilu startowego")
    parser.add_argument('game_command', nargs=argparse.REMAINDER, help="Komenda gry")
    args = parser.parse_args()

    # Czyszczenie argumentów dla steam
    cmd = args.game_command
    if cmd and cmd[0] == '--': cmd.pop(0)

    root = tk.Tk()
    app = GameReaderApp(root, args.preset, cmd)
    root.mainloop()


if __name__ == "__main__":
    main()