import tkinter as tk
from tkinter import ttk

class ProcessingWindow(tk.Toplevel):
    def __init__(self, parent, title="Przetwarzanie"):
        super().__init__(parent)
        self.title(title)
        self.geometry("400x150")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        # Center relative to parent
        self.update_idletasks()
        try:
            x = parent.winfo_rootx() + (parent.winfo_width() // 2) - (self.winfo_width() // 2)
            y = parent.winfo_rooty() + (parent.winfo_height() // 2) - (self.winfo_height() // 2)
            self.geometry(f"+{x}+{y}")
        except Exception:
            pass

        main_f = ttk.Frame(self, padding=20)
        main_f.pack(fill=tk.BOTH, expand=True)

        self.lbl_status = ttk.Label(main_f, text="Trwa optymalizacja ustawień...\nTo może chwilę potrwać.", justify=tk.CENTER)
        self.lbl_status.pack(pady=10)

        self.progress = ttk.Progressbar(main_f, mode='indeterminate')
        self.progress.pack(fill=tk.X, pady=10)
        self.progress.start(10)

    def set_status(self, text):
        self.lbl_status.config(text=text)
        self.update_idletasks()
