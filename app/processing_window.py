from app.ctk_widgets import CTkToplevel, make_frame, make_label, make_progressbar
import tkinter as tk
from tkinter import ttk


class ProcessingWindow(CTkToplevel):
    def __init__(self, parent, title="Przetwarzanie"):
        super().__init__(parent)
        self.title(title)
        self.geometry("500x200")
        self.resizable(False, False)
        self.transient(parent)
        # Try to set grab only if parent is viewable; on some flows the
        # caller may have withdrawn or not yet mapped the root which causes
        # `grab_set()` to raise `TclError: grab failed: window not viewable`.
        try:
            if getattr(parent, 'winfo_viewable', None) and parent.winfo_viewable():
                self.grab_set()
        except Exception:
            # If grab fails, continue without modal grab — the processing
            # window is informational and the optimization continues in a
            # background thread.
            pass

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

        # Small label showing percent progress and current best score
        self.lbl_progress_info = make_label(main_f, text=("0% | Jakość ustawień: 0.0%"))
        self.lbl_progress_info.pack()

        # Internal flag to mark determinate progress initialization
        self._progress_determinate = False

    def set_progress(self, value: int, total: int = None, best_score: float = None):
        """
        Update progress bar. If `total` is provided on first call, switch the
        progress bar to determinate mode and set maximum.
        This method is safe to call from the main thread; callers from other
        threads should schedule via `after(0, ...)` on this window.
        """
        try:
            if not self.progress:
                return
            if total is not None and not self._progress_determinate:
                try:
                    # Configure determinate mode and maximum value
                    self.progress.config(mode='determinate', maximum=int(total))
                    self._progress_determinate = True
                    # Stop any indeterminate animation
                    try:
                        self.progress.stop()
                    except Exception:
                        pass
                except Exception:
                    pass
            # Set current value
            try:
                self.progress['value'] = int(value)
            except Exception:
                try:
                    self.progress.configure(value=int(value))
                except Exception:
                    pass
            # Update percent label and best score if provided
            try:
                pct = 0
                if total:
                    try:
                        pct = (int(value) / int(total)) * 100
                    except Exception:
                        pct = 0
                else:
                    pct = int(value)
                best_display = f"{(min(best_score, 100) if best_score is not None else 0):.1f}%"
                try:
                    self.lbl_progress_info.configure(text=f"{pct:.0f}% | Jakość ustawień: {best_display}")
                except Exception:
                    try:
                        self.lbl_progress_info.configure(text=f"{pct:.0f}% | Jakość ustawień: {best_display}")
                    except Exception:
                        pass
            except Exception:
                pass
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
