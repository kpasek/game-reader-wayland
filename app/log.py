import tkinter as tk
from tkinter import  scrolledtext
import queue


class LogWindow(tk.Toplevel):
    def __init__(self, parent, log_queue):
        super().__init__(parent)
        self.title("Podgląd Logów OCR")
        self.geometry("1000x600")
        self.log_queue = log_queue
        self.is_open = True
        self.max_lines = 2000

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
        timestamp = data.get('time', '')
        ocr = data.get('ocr')
        match = data.get('match')
        stats = data.get('stats', {})
        line_text = data.get('line_text', '')

        if ocr is None:
            msg = f"[{timestamp}] {line_text}\n"
            msg += "-" * 40 + "\n"
        else:
            mon_info = ""
            if stats:
                mon = stats.get('monitor', '?')
                # stats['monitor'] is usually "#1", so display becomes "[Obszar #1] "
                mon_info = f"[Obszar {mon}] "

            msg = f"[{timestamp}] {mon_info}OCR: {ocr}\n"
            if stats:
                mon = stats.get('monitor', '?') # Kept variable if needed, but not used in msg below
                t_cap = stats.get('cap_ms', 0)
                t_pre = stats.get('pre_ms', 0)
                t_ocr = stats.get('ocr_ms', 0)
                t_match = stats.get('match_ms', 0)

                # Bardziej zwarty format
                msg += f"   [Czasy: Cap:{t_cap:.0f} | Pre:{t_pre:.0f} | OCR:{t_ocr:.0f} | Match:{t_match:.0f} ms]\n"

            if match:
                msg += f"   >>> MATCH ({match[1]}%): {line_text}\n"
            else:
                msg += "   >>> Brak dopasowania\n"
            msg += "-" * 40 + "\n"

        self.text_area.config(state='normal')
        self.text_area.insert(tk.END, msg)

        num_lines = int(self.text_area.index('end-1c').split('.')[0])
        if num_lines > self.max_lines:
            diff = num_lines - self.max_lines
            self.text_area.delete("1.0", f"{diff}.0")

        self.text_area.see(tk.END)
        self.text_area.config(state='disabled')