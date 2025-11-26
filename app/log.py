import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import queue


class LogWindow(tk.Toplevel):
    def __init__(self, parent, log_queue):
        super().__init__(parent)
        self.title("Podgląd Logów OCR")
        self.geometry("1000x600")
        self.log_queue = log_queue
        self.is_open = True

        # Checkbox zapisu do pliku
        self.save_var = tk.BooleanVar(value=False)
        chk = ttk.Checkbutton(self, text="Zapisuj do pliku (dialog_match.log)", variable=self.save_var)
        chk.pack(anchor=tk.W, padx=5, pady=5)

        # Obszar tekstowy
        self.text_area = scrolledtext.ScrolledText(self, state='disabled')
        self.text_area.pack(fill=tk.BOTH, expand=True)

        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.update_logs()

    def on_close(self):
        self.is_open = False
        self.destroy()

    def update_logs(self):
        if not self.is_open: return

        while not self.log_queue.empty():
            try:
                data = self.log_queue.get_nowait()
                self._append_text(data)
            except queue.Empty:
                break
        self.after(500, self.update_logs)

    def _append_text(self, data):
        timestamp = data['time']
        ocr = data['ocr']
        match = data['match']  # (idx, score) lub None
        stats = data.get('stats', {})

        msg = f"[{timestamp}] OCR: {ocr}\n"

        # Wyświetlanie statystyk i monitora
        if stats:
            mon = stats.get('monitor', '?')
            t_cap = stats.get('cap_ms', 0)
            t_ocr = stats.get('ocr_ms', 0)
            t_match = stats.get('match_ms', 0)
            msg += f"   [Obszar: {mon} | Zrzut: {t_cap:.0f}ms | OCR: {t_ocr:.0f}ms | Match: {t_match:.0f}ms]\n"

        if match:
            msg += f"   >>> DOPASOWANIE ({match[1]}%): linia {match[0] + 1}: {data['line_text']}\n"
        else:
            msg += "   >>> Brak dopasowania\n"
        msg += "-" * 40 + "\n"

        self.text_area.config(state='normal')
        self.text_area.insert(tk.END, msg)
        self.text_area.see(tk.END)
        self.text_area.config(state='disabled')

        if self.save_var.get():
            try:
                with open("dialog_match.log", "a", encoding="utf-8") as f:
                    f.write(msg)
            except Exception:
                pass