from app.ctk_widgets import CTkToplevel, make_frame, make_label
import tkinter as tk
from tkinter import ttk


class ProcessingWindow(CTkToplevel):
    def __init__(self, parent, title="Przetwarzanie"):
        super().__init__(parent)
        self.title(title)
        self.geometry("500x200")
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

        main_f = make_frame(self, padding=20)
        main_f.pack(fill=tk.BOTH, expand=True)

        # Warn user that optimization may be long-running when progressbar is shown
        self.lbl_status = make_label(
            main_f,
            text=("Trwa optymalizacja ustawień...\n"),
        )
        self.lbl_status.pack(pady=10)

        # Progressbar via factory (fallback to ttk.Progressbar)
        self.progress = make_progressbar(main_f, mode='indeterminate')
        if self.progress:
            self.progress.pack(fill=tk.X, pady=10)
            try:
                self.progress.start(10)
            except Exception:
                pass

    def set_status(self, text):
        try:
            self.lbl_status.configure(text=text)
        except Exception:
            try:
                self.lbl_status.configure(text=text)
            except Exception:
                pass
        self.update_idletasks()
