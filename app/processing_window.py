from app.ctk_widgets import CTkToplevel, make_frame, make_label, make_progressbar
import tkinter as tk
from tkinter import ttk
import queue


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
        
        # Thread-safe communication
        self.queue = queue.Queue()
        self.after(100, self._poll_queue)
        
        # Stop signal for background processing
        import multiprocessing
        self.stop_event = multiprocessing.Event()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _on_close(self):
        """Handle window closure by signaling background thread to stop."""
        self.stop_event.set()
        self.destroy()

    def _poll_queue(self):
        """Periodically check for updates from the background thread."""
        try:
            while True:
                msg = self.queue.get_nowait()
                msg_type = msg.get("type")
                if msg_type == "progress":
                    self._update_progress_ui(msg.get("value"), msg.get("total"), msg.get("best_score"))
                elif msg_type == "status":
                    self._update_status_ui(msg.get("text"))
                elif msg_type == "complete":
                    if msg.get("callback"):
                        msg.get("callback")()
                self.queue.task_done()
        except queue.Empty:
            pass
        finally:
            # Continue polling even if window is closed (after handles errors)
            try:
                self.after(100, self._poll_queue)
            except Exception:
                pass

    def set_progress(self, value: int, total: int = None, best_score: float = None):
        """Thread-safe method to update progress via queue."""
        self.queue.put({"type": "progress", "value": value, "total": total, "best_score": best_score})

    def set_status(self, text: str):
        """Thread-safe method to update status via queue."""
        self.queue.put({"type": "status", "text": text})

    def _update_progress_ui(self, value: int, total: int = None, best_score: float = None):
        """Internal method to update UI components - must be called from main thread."""
        try:
            if not self.progress:
                return
            if total is not None and not self._progress_determinate:
                try:
                    self.progress.config(mode='determinate', maximum=int(total))
                    self._progress_determinate = True
                    try: self.progress.stop()
                    except Exception: pass
                except Exception: pass
            
            try:
                self.progress['value'] = int(value)
            except Exception:
                try: self.progress.configure(value=int(value))
                except Exception: pass

            pct = 0
            if total:
                pct = (int(value) / int(total)) * 100
            else:
                pct = int(value)
            best_display = f"{(min(best_score, 100) if best_score is not None else 0):.1f}%"
            self.lbl_progress_info.configure(text=f"{pct:.0f}% | Jakość ustawień: {best_display}")
        except Exception:
            pass

    def _update_status_ui(self, text: str):
        """Internal method to update status label - must be called from main thread."""
        try:
            self.lbl_status.configure(text=text)
        except Exception:
            pass
        self.update_idletasks()
