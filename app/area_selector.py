import sys

try:
    import tkinter as tk
    from PIL import Image, ImageTk
except ImportError:
    print("Ostrzeżenie: Brak tkinter lub PIL.ImageTk - GUI może nie działać.", file=sys.stderr)
    tk = None
    Image = None
    ImageTk = None


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
            for i, area_data in enumerate(existing_regions):
                # area_data can be dict with rect, id, colors
                r = area_data.get('rect') if isinstance(area_data, dict) else area_data
                
                if not r or not isinstance(r, dict): continue
                
                x, y, w, h = r['left'], r['top'], r['width'], r['height']
                
                # Determine color
                color = 'blue'
                colors = area_data.get('colors', [])
                if isinstance(area_data, dict) and colors:
                    color = colors[0] # Primary color
                
                # Draw rect
                self.cv.create_rectangle(x, y, x + w, y + h, outline=color, width=2, dash=(4, 4))
                
                # Draw label background
                aid = area_data.get('id', i+1) if isinstance(area_data, dict) else i+1
                typ = area_data.get('type', '?') if isinstance(area_data, dict) else ""
                
                label_txt = f"Obszar #{aid}"
                if typ: label_txt += f" ({typ})"
                
                self.cv.create_rectangle(x, y - 25, x + 120, y, fill=color, outline=color)
                # Text contrast? Assuming white text is mostly fine on colored bg or blue default
                self.cv.create_text(x + 5, y - 12, text=label_txt, fill="white", anchor=tk.W,
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


class ColorSelector(tk.Toplevel):
    """
    Pełnoekranowe okno pozwalające kliknąć w punkt i pobrać jego kolor.
    Zapisuje wynik (hex) w self.selected_color.
    """

    def __init__(self, parent, screenshot: Image.Image):
        super().__init__(parent)
        self.screenshot = screenshot
        self.selected_color = None

        # Ustawienia pełnego ekranu
        self.attributes('-fullscreen', True)
        self.attributes('-topmost', True)
        self.attributes('-alpha', 1.0)

        self.bg_img = ImageTk.PhotoImage(screenshot)

        self.cv = tk.Canvas(self, cursor="crosshair", highlightthickness=0)
        self.cv.pack(fill=tk.BOTH, expand=True)
        self.cv.create_image(0, 0, image=self.bg_img, anchor=tk.NW)

        # Wyjście ESC
        self.bind("<Escape>", lambda e: self.destroy())
        # Kliknięcie
        self.cv.bind("<Button-1>", self.on_click)

    def on_click(self, event):
        x, y = event.x, event.y
        # Pobierz kolor piksela z oryginalnego obrazu PIL
        if 0 <= x < self.screenshot.width and 0 <= y < self.screenshot.height:
            rgb = self.screenshot.getpixel((x, y))
            # Upewnij się, że mamy RGB (mss/PIL czasem zwraca RGBA)
            if isinstance(rgb, tuple) and len(rgb) >= 3:
                r, g, b = rgb[0], rgb[1], rgb[2]
                self.selected_color = "#{:02x}{:02x}{:02x}".format(r, g, b)

        self.destroy()