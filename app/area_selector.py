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

        self.attributes('-fullscreen', True)
        self.attributes('-topmost', True)

        self.bg_img = ImageTk.PhotoImage(screenshot)

        self.cv = tk.Canvas(self, cursor="cross", highlightthickness=0)
        self.cv.pack(fill=tk.BOTH, expand=True)
        self.cv.create_image(0, 0, image=self.bg_img, anchor=tk.NW)

        # Rysowanie istniejących obszarów (podgląd)
        if existing_regions:
            for i, r in enumerate(existing_regions):
                if not r: continue
                x, y, w, h = r['left'], r['top'], r['width'], r['height']
                self.cv.create_rectangle(x, y, x + w, y + h, outline='blue', width=2, dash=(4, 4))
                self.cv.create_text(x + 5, y - 10, text=f"Obszar {i + 1}", fill="blue", anchor=tk.NW)

        self.cv.bind("<ButtonPress-1>", self.on_press)
        self.cv.bind("<B1-Motion>", self.on_drag)
        self.cv.bind("<ButtonRelease-1>", self.on_release)
        self.bind("<Escape>", lambda e: self.destroy())

        # Informacja dla usera
        self.lbl_info = tk.Label(self, text="Zaznacz obszar myszką (ESC aby anulować)", bg="yellow", font=("Arial", 12))
        self.lbl_info.place(x=10, y=10)

        self.wait_visibility()
        self.grab_set()
        self.wait_window()

    def on_press(self, event):
        if self.rect_id: self.cv.delete(self.rect_id)
        self.start_x = event.x
        self.start_y = event.y
        self.rect_id = self.cv.create_rectangle(self.start_x, self.start_y, self.start_x, self.start_y, outline='red',
                                                width=3)

    def on_drag(self, event):
        self.cv.coords(self.rect_id, self.start_x, self.start_y, event.x, event.y)

    def on_release(self, event):
        x1, y1 = self.start_x, self.start_y
        x2, y2 = event.x, event.y

        left, top = min(x1, x2), min(y1, y2)
        width, height = abs(x1 - x2), abs(y1 - y2)

        if width > 10 and height > 10:
            self.geometry = {'left': left, 'top': top, 'width': width, 'height': height}
        self.destroy()