#!/usr/bin/env python3
import sys
import os
import queue
import threading
import subprocess
import time
import argparse
import platform
from typing import Optional, Dict, List

try:
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox, scrolledtext, font
except ImportError:
    print("Błąd: Brak biblioteki tkinter.", file=sys.stderr)
    sys.exit(1)

# --- FIX WINDOWS 11 DPI SCALING ---
if platform.system() == "Windows":
    try:
        import ctypes

        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
# ----------------------------------

# --- PYNPUT HOTKEYS ---
try:
    from pynput import keyboard

    HAS_PYNPUT = True
except ImportError:
    HAS_PYNPUT = False
# ----------------------

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

# --- KONFIGURACJA STANDARDU (4K) ---
STANDARD_WIDTH = 3840
STANDARD_HEIGHT = 2160


class HelpWindow(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Pomoc i Instrukcja")
        self.geometry("600x520")

        # Używamy fontu systemowego dla lepszej czytelności
        default_font = font.nametofont("TkDefaultFont")
        base_font_family = default_font.actual()["family"]

        txt = scrolledtext.ScrolledText(self, wrap=tk.WORD, padx=15, pady=15, font=(base_font_family, 10))
        txt.pack(fill=tk.BOTH, expand=True)

        # Konfiguracja stylów (tagów)
        # spacing1 - odstęp nad, spacing3 - odstęp pod akapitem
        txt.tag_config('h1', font=(base_font_family, 12, 'bold'), spacing1=15, spacing3=5, foreground="#222222")
        txt.tag_config('bold', font=(base_font_family, 10, 'bold'))
        txt.tag_config('normal', spacing3=2)  # Lekki odstęp pod każdą linią tekstu

        # Budowanie treści - jawne \n na końcu linii jest kluczowe
        content = [
            ("JAK TO DZIAŁA?\n", 'h1'),
            ("Aplikacja wykonuje zrzuty ekranu w zdefiniowanych obszarach, rozpoznaje tekst (OCR) i porównuje go z plikiem napisów z gry. Gdy znajdzie dopasowanie, odtwarza odpowiedni plik audio.\n",
             'normal'),

            ("SKRÓTY KLAWISZOWE (Globalne)\n", 'h1'),
            ("Ctrl + F5", 'bold'), (" - Start / Stop czytania\n", 'normal'),
            ("Ctrl + F6", 'bold'), (" - Aktywacja Obszaru 3 (Adnotacje) na 2 sekundy.\n", 'normal'),
            ("Używane do czytania listów/książek w grze, gdy nie chcemy, aby OCR działał tam ciągle.\n", 'normal'),

            ("KONFIGURACJA OBSZARÓW\n", 'h1'),
            ("W menu 'Obszary ekranu' możesz zdefiniować do 3 stref:\n", 'normal'),
            ("• Obszar 1 i 2: ", 'bold'), ("Skanowane ciągle (np. góra i dół ekranu dla dialogów).\n", 'normal'),
            ("• Obszar 3: ", 'bold'), ("Skanowany TYLKO po wciśnięciu skrótu (Ctrl+F6).\n", 'normal'),

            ("FILTROWANIE TEKSTU\n", 'h1'),
            ("• Automatyczne usuwanie imion: ", 'bold'),
            ("Jeśli gra wyświetla format 'Geralt: Cześć', opcja ta wytnie imię, zostawiając tylko 'Cześć'.\n",
             'normal'),
            ("• Regex: ", 'bold'),
            ("Pozwala na zaawansowane wycinanie fragmentów tekstu przed dopasowaniem.\n", 'normal'),

            ("PORADY\n", 'h1'),
            ("- Jeśli gra ma niestandardową czcionkę, upewnij się, że obszar obejmuje tylko tekst.\n", 'normal'),
            ("- Upewnij się, że w tle nie ma innych okien zasłaniających grę (gra musi być widoczna na ekranie).\n",
             'normal')
        ]

        for text, tag in content:
            txt.insert(tk.END, text, tag)

        txt.config(state=tk.DISABLED)


class GameReaderApp:
    def __init__(self, root: tk.Tk, autostart_preset: Optional[str], game_cmd: list):
        self.root = root
        self.root.title("Game Reader")
        # Zmniejszony rozmiar okna
        self.root.geometry("700x500")

        self.config_mgr = ConfigManager()
        self.game_cmd = game_cmd
        self.game_process = None

        # Wątki
        self.reader_thread = None
        self.player_thread = None
        self.log_window = None
        self.help_window = None
        self.is_running = False

        # Zmienne UI
        self.var_preset = tk.StringVar()
        self.var_audio_dir = tk.StringVar()
        self.var_subs_file = tk.StringVar()
        self.var_names_file = tk.StringVar()

        self.var_regex_mode = tk.StringVar()
        self.var_custom_regex = tk.StringVar()
        self.var_auto_names = tk.BooleanVar(value=True)  # Nowy checkbox
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

        if HAS_PYNPUT:
            self._start_hotkey_listener()

    def _start_hotkey_listener(self):
        hotkeys = {
            '<ctrl>+<f5>': self._on_hotkey_start_stop,
            '<ctrl>+<f6>': self._on_hotkey_area3
        }
        try:
            self.listener = keyboard.GlobalHotKeys(hotkeys)
            self.listener.start()
        except Exception as e:
            print(f"Błąd inicjalizacji skrótów: {e}")

    def _on_hotkey_start_stop(self):
        self.root.after(0, self._toggle_start_stop_hotkey)

    def _on_hotkey_area3(self):
        self.root.after(0, self._trigger_area3_hotkey)

    def _toggle_start_stop_hotkey(self):
        if self.is_running:
            self.stop_reading()
        else:
            self.start_reading()

    def _trigger_area3_hotkey(self):
        if self.is_running and self.reader_thread:
            self.reader_thread.trigger_area_3(duration=2.0)

    def _init_gui(self):
        # --- MENU ---
        menubar = tk.Menu(self.root)

        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Ustawienia zaawansowane", command=self.open_settings)
        file_menu.add_separator()
        file_menu.add_command(label="Wyjdź", command=self.on_close)
        menubar.add_cascade(label="Plik", menu=file_menu)

        # Zmiana nazwy Profil -> Lektor
        preset_menu = tk.Menu(menubar, tearoff=0)
        preset_menu.add_command(label="Wczytaj inny profil...", command=self.browse_preset)

        area_menu = tk.Menu(preset_menu, tearoff=0)
        for i in range(3):
            sub = tk.Menu(area_menu, tearoff=0)
            suffix = " (CZASOWY - Ctrl+F6)" if i == 2 else ""
            sub.add_command(label=f"Definiuj Obszar {i + 1}{suffix}", command=lambda x=i: self.set_area(x))
            sub.add_command(label=f"Wyczyść Obszar {i + 1}", command=lambda x=i: self.clear_area(x))
            area_menu.add_cascade(label=f"Obszar {i + 1}{suffix}", menu=sub)
        preset_menu.add_cascade(label="Obszary ekranu", menu=area_menu)

        preset_menu.add_separator()
        preset_menu.add_command(label="Zmień folder audio", command=lambda: self.change_path('audio_dir'))
        preset_menu.add_command(label="Zmień plik napisów", command=lambda: self.change_path('text_file_path'))
        preset_menu.add_command(label="Zmień plik imion", command=lambda: self.change_path('names_file_path'))
        menubar.add_cascade(label="Lektor", menu=preset_menu)

        tools_menu = tk.Menu(menubar, tearoff=0)
        tools_menu.add_command(label="Podgląd logów", command=self.show_logs)
        menubar.add_cascade(label="Narzędzia", menu=tools_menu)

        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="Instrukcja / Skróty", command=self.show_help)
        menubar.add_cascade(label="Pomoc", menu=help_menu)

        self.root.config(menu=menubar)

        # --- GŁÓWNY PANEL ---
        panel = ttk.Frame(self.root, padding=10)
        panel.pack(fill=tk.BOTH, expand=True)

        ttk.Label(panel, text="Aktywny profil lektora:").pack(anchor=tk.W)
        self.cb_preset = ttk.Combobox(panel, textvariable=self.var_preset, state="readonly", width=60)
        self.cb_preset.pack(fill=tk.X, pady=5)
        self.cb_preset.bind("<<ComboboxSelected>>", self.on_preset_changed)

        # Regex i Filtry
        grp_regex = ttk.LabelFrame(panel, text="Filtracja tekstu", padding=5)
        grp_regex.pack(fill=tk.X, pady=10)

        f_reg = ttk.Frame(grp_regex)
        f_reg.pack(fill=tk.X)

        ttk.Label(f_reg, text="Regex:").pack(side=tk.LEFT)
        self.cb_regex = ttk.Combobox(f_reg, textvariable=self.var_regex_mode,
                                     values=list(self.regex_map.keys()), state="readonly", width=25)
        self.cb_regex.pack(side=tk.LEFT, padx=5)
        self.cb_regex.bind("<<ComboboxSelected>>", self.on_regex_changed)

        self.ent_regex = ttk.Entry(f_reg, textvariable=self.var_custom_regex, state="disabled")
        self.ent_regex.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        self.ent_regex.bind("<FocusOut>",
                            lambda e: self.config_mgr.update_setting('last_custom_regex', self.var_custom_regex.get()))

        # Nowy Checkbox
        f_opts = ttk.Frame(grp_regex)
        f_opts.pack(fill=tk.X, pady=(5, 0))
        chk_names = ttk.Checkbutton(f_opts, text="Automatyczne usuwanie imion (np. 'Geralt: Witaj')",
                                    variable=self.var_auto_names,
                                    command=lambda: self._save_preset_val("auto_remove_names",
                                                                          self.var_auto_names.get()))
        chk_names.pack(side=tk.LEFT)

        # Rozdzielczość
        ttk.Label(panel, text="Rozdzielczość gry (dla skalowania obszarów):").pack(anchor=tk.W, pady=(10, 0))
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
        self.btn_start = ttk.Button(frm_btn, text="START (Ctrl+F5)", command=self.start_reading)
        self.btn_start.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        self.btn_stop = ttk.Button(frm_btn, text="STOP (Ctrl+F5)", command=self.stop_reading, state="disabled")
        self.btn_stop.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)

    def _load_initial_state(self, autostart_path):
        recents = self.config_mgr.get('recent_presets', [])
        self.cb_preset['values'] = recents

        initial_preset = autostart_path if autostart_path else (recents[0] if recents else "")
        if initial_preset and os.path.exists(initial_preset):
            self.var_preset.set(initial_preset)
            self.on_preset_changed()
            if autostart_path:
                self.root.after(500, self.start_reading)

        self.var_regex_mode.set(self.config_mgr.get('last_regex_mode', "Standard (Imię: Dialog)"))
        self.var_custom_regex.set(self.config_mgr.get('last_custom_regex', ""))
        self.var_resolution.set(self.config_mgr.get('last_resolution_key', "1920x1080"))
        self.on_regex_changed()

    def on_preset_changed(self, event=None):
        path = self.var_preset.get()
        if not path or not os.path.exists(path): return

        data = self.config_mgr.load_preset(path)
        self.var_speed.set(data.get("audio_speed", 1.15))
        self.lbl_speed.config(text=f"{self.var_speed.get():.2f}x")

        self.var_volume.set(data.get("audio_volume", 1.0))
        self.lbl_vol.config(text=f"{self.var_volume.get():.2f}")

        # Wczytanie stanu checkboxa (domyślnie True)
        self.var_auto_names.set(data.get("auto_remove_names", True))

        if "regex_mode_name" in data:
            self.var_regex_mode.set(data["regex_mode_name"])
            if data["regex_mode_name"] == "Własny (Regex)":
                self.var_custom_regex.set(data.get("regex_pattern", ""))
            self.on_regex_changed()

        if "resolution" in data:
            self.var_resolution.set(data["resolution"])

    def on_regex_changed(self, event=None):
        mode = self.var_regex_mode.get()
        self.ent_regex.config(state="normal" if mode == "Własny (Regex)" else "disabled")
        self.config_mgr.update_setting('last_regex_mode', mode)

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
        preset_path = self.var_preset.get()
        if not preset_path: return

        if key == 'audio_dir':
            new_path = filedialog.askdirectory()
        else:
            new_path = filedialog.askopenfilename(filetypes=[("Text", "*.txt")])

        if new_path:
            self._save_preset_val(key, new_path)
            messagebox.showinfo("Sukces", "Zaktualizowano ścieżkę w profilu.")

    def _scale_rect(self, rect: Dict[str, int], scale_x: float, scale_y: float) -> Dict[str, int]:
        return {
            'left': int(rect['left'] * scale_x),
            'top': int(rect['top'] * scale_y),
            'width': int(rect['width'] * scale_x),
            'height': int(rect['height'] * scale_y)
        }

    def set_area(self, idx):
        preset_path = self.var_preset.get()
        if not preset_path: return messagebox.showerror("Błąd", "Wybierz profil.")

        self.root.withdraw()
        time.sleep(0.3)
        img = capture_fullscreen()
        if not img:
            self.root.deiconify()
            return

        screen_w, screen_h = img.size

        data = self.config_mgr.load_preset(preset_path)
        current_mons = data.get('monitor', [])
        if isinstance(current_mons, dict): current_mons = [current_mons]
        while len(current_mons) < 3: current_mons.append(None)

        preset_res_str = data.get('resolution', "1920x1080")
        try:
            p_w, p_h = map(int, preset_res_str.split('x'))
        except:
            p_w, p_h = 1920, 1080

        scale_to_screen_x = screen_w / p_w
        scale_to_screen_y = screen_h / p_h

        display_mons = []
        for m in current_mons:
            if m:
                display_mons.append(self._scale_rect(m, scale_to_screen_x, scale_to_screen_y))
            else:
                display_mons.append(None)

        sel = AreaSelector(self.root, img, existing_regions=display_mons)
        self.root.deiconify()

        if sel.geometry:
            scale_to_std_x = STANDARD_WIDTH / screen_w
            scale_to_std_y = STANDARD_HEIGHT / screen_h

            display_mons[idx] = sel.geometry

            final_mons = []
            for m in display_mons:
                if m:
                    final_mons.append(self._scale_rect(m, scale_to_std_x, scale_to_std_y))

            data['monitor'] = final_mons
            data['resolution'] = f"{STANDARD_WIDTH}x{STANDARD_HEIGHT}"

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
        self.config_mgr.save_app_config()

    def show_logs(self):
        if not self.log_window or not self.log_window.winfo_exists():
            self.log_window = LogWindow(self.root, log_queue)
        else:
            self.log_window.lift()

    def show_help(self):
        if not self.help_window or not self.help_window.winfo_exists():
            self.help_window = HelpWindow(self.root)
        else:
            self.help_window.lift()

    # --- START / STOP ---

    def start_reading(self):
        path = self.var_preset.get()
        if not path or not os.path.exists(path):
            return messagebox.showerror("Błąd", "Brak poprawnego profilu.")

        self.config_mgr.add_recent_preset(path)

        mode = self.var_regex_mode.get()
        pattern = self.var_custom_regex.get() if mode == "Własny (Regex)" else self.regex_map.get(mode, "")

        # Pobieramy stan checkboxa
        auto_remove_names = self.var_auto_names.get()

        res_str = self.var_resolution.get()
        target_res = None
        if "x" in res_str:
            try:
                target_res = tuple(map(int, res_str.split('x')))
            except:
                pass

        stop_event.clear()

        with audio_queue.mutex:
            audio_queue.queue.clear()

        self.player_thread = PlayerThread(
            stop_event, audio_queue,
            base_speed_callback=lambda: self.var_speed.get(),
            volume_callback=lambda: self.var_volume.get()
        )
        self.reader_thread = ReaderThread(
            path, pattern, self.config_mgr.settings, stop_event, audio_queue,
            target_resolution=target_res, log_queue=log_queue,
            auto_remove_names=auto_remove_names  # Przekazanie flagi
        )

        self.player_thread.start()
        self.reader_thread.start()

        self.is_running = True
        self._toggle_ui(True)

        if self.game_cmd and not self.game_process:
            try:
                self.game_process = subprocess.Popen(self.game_cmd)
            except Exception as e:
                messagebox.showerror("Błąd Gry", f"Nie udało się uruchomić gry: {e}")

    def stop_reading(self):
        self.is_running = False
        stop_event.set()
        if self.reader_thread: self.reader_thread.join(1.0)
        self._toggle_ui(False)

    def _toggle_ui(self, running):
        state = "disabled" if running else "normal"
        self.btn_start.config(state=state)
        self.btn_stop.config(state="normal" if running else "disabled")
        self.cb_preset.config(state="disabled" if running else "readonly")

    def on_close(self):
        self.is_running = False
        if self.reader_thread and self.reader_thread.is_alive():
            self.stop_reading()
        if self.game_process:
            self.game_process.terminate()
        if hasattr(self, 'listener'):
            self.listener.stop()
        self.root.destroy()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--preset', type=str, help="Ścieżka do profilu startowego")
    parser.add_argument('game_command', nargs=argparse.REMAINDER, help="Komenda gry")
    args = parser.parse_args()

    cmd = args.game_command
    if cmd and cmd[0] == '--': cmd.pop(0)

    root = tk.Tk()
    app = GameReaderApp(root, args.preset, cmd)
    root.mainloop()


if __name__ == "__main__":
    main()