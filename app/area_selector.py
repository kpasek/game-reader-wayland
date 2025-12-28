import sys

try:
    import tkinter as tk
    from PIL import Image, ImageTk
except ImportError:
    sys.exit(1)


class AreaSelector(tk.Toplevel):
    """
    Pełnoekranowe okno pozwalające zaznaczyć prostokątny obszar myszką.
    Zwraca słownik geometrii w self.geometry.
    """

    def __init__(self, parent, screenshot: Image.Image, existing_regions: list = None):
        super().__init__(parent)
        self.geometry = None
        self.start_x = None
        self.start_y = None
        self.rect_id = None

        # Ustawienia pełnego ekranu i widoczności
        self.attributes('-fullscreen', True)
        self.attributes('-topmost', True)
        self.attributes('-alpha', 1.0)

        self.bg_img = ImageTk.PhotoImage(screenshot)

        self.cv = tk.Canvas(self, cursor="cross", highlightthickness=0)
        self.cv.pack(fill=tk.BOTH, expand=True)
        self.cv.create_image(0, 0, image=self.bg_img, anchor=tk.NW)

        if existing_regions:
            for i, r in enumerate(existing_regions):
                if not r: continue
                x, y, w, h = r['left'], r['top'], r['width'], r['height']

                # Rysuj ramkę
                self.cv.create_rectangle(x, y, x + w, y + h, outline='blue', width=2, dash=(4, 4))
                # Rysuj tło etykiety dla czytelności
                self.cv.create_rectangle(x, y - 20, x + 80, y, fill='blue', outline='blue')
                self.cv.create_text(x + 5, y - 10, text=f"Obszar {i + 1}", fill="white", anchor=tk.W,
                                    font=("Arial", 10, "bold"))

        self.cv.bind("<ButtonPress-1>", self.on_press)
        self.cv.bind("<B1-Motion>", self.on_drag)
        self.cv.bind("<ButtonRelease-1>", self.on_release)
        self.bind("<Escape>", lambda e: self.destroy())

        # Informacja dla usera
        self.lbl_info = tk.Label(self, text="Zaznacz obszar myszką (ESC aby anulować)", bg="yellow", font=("Arial", 12))
        self.lbl_info.place(x=10, y=10)

        # Focus i czekanie na okno
        self.focus_force()
        self.wait_visibility()
        self.grab_set()
        self.wait_window()

    def on_press(self, event):
        if self.rect_id: self.cv.delete(self.rect_id)
        self.start_x = event.x
        self.start_y = event.y
        self.rect_id = self.cv.create_rectangle(self.start_x, self.start_y, self.start_x, self.start_y, outline='red',
                                                width=2)

    def on_drag(self, event):
        self.cv.coords(self.rect_id, self.start_x, self.start_y, event.x, event.y)

    def on_release(self, event):
        if not self.start_x or not self.start_y:
            return

        x1, y1 = self.start_x, self.start_y
        x2, y2 = event.x, event.y

        left, top = min(x1, x2), min(y1, y2)
        width, height = abs(x1 - x2), abs(y1 - y2)

        # Minimalny rozmiar, żeby uniknąć przypadkowych kliknięć
        if width > 10 and height > 10:
            self.geometry = {'left': left, 'top': top, 'width': width, 'height': height}
        self.destroy()