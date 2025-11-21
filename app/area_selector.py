
import sys

try:
    import tkinter as tk
except ImportError:
    print("Błąd: Nie znaleziono biblioteki 'tkinter'.", file=sys.stderr)
    print("Zazwyczaj jest dołączona do Pythona. W Debian/Ubuntu: sudo apt install python3-tk", file=sys.stderr)
    sys.exit(1)

try:
    from PIL import Image, ImageTk
except ImportError:
    print("Błąd: Nie znaleziono biblioteki 'Pillow'. Zainstaluj ją: pip install Pillow", file=sys.stderr)
    sys.exit(1)
    
class AreaSelector(tk.Toplevel):
    """Okno ze zrzutem ekranu do zaznaczania obszaru."""

    def __init__(self, parent, screenshot_image: Image.Image, current_geometry: dict = None):
        super().__init__(parent)
        self.parent = parent
        self.geometry = None  # (x, y, w, h)

        # Zmienne do rysowania
        self.start_x = None
        self.start_y = None
        self.rect = None

        # Konfiguracja okna
        self.attributes('-fullscreen', True)
        self.attributes('-topmost', True)

        self.bg_tk = ImageTk.PhotoImage(screenshot_image)

        self.canvas = tk.Canvas(self, cursor="cross")
        self.canvas.pack(fill=tk.BOTH, expand=True)

        self.canvas.create_image(0, 0, image=self.bg_tk, anchor=tk.NW)

        if current_geometry:
            cx = current_geometry.get('left', 0)
            cy = current_geometry.get('top', 0)
            cw = current_geometry.get('width', 0)
            ch = current_geometry.get('height', 0)
            
            # Rysujemy na niebiesko, przerywaną linią, żeby odróżnić od nowego zaznaczenia
            self.canvas.create_rectangle(
                cx, cy, cx + cw, cy + ch,
                outline='blue', width=2, dash=(2, 4), tags="current_area"
            )
            self.canvas.create_text(
                cx + 5, cy - 10, text="Aktualny obszar", fill="blue", anchor=tk.NW
            )

        self.canvas.bind("<ButtonPress-1>", self.on_mouse_down)
        self.canvas.bind("<B1-Motion>", self.on_mouse_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_mouse_up)

        self.bind("<Escape>", lambda e: self.destroy())

        print("Gotowy do wyboru obszaru. Narysuj prostokąt. Naciśnij Esc aby anulować.")
        self.grab_set()
        self.wait_window()

    def on_mouse_down(self, event):
        # Usuń stare zaznaczenie (czerwone) oraz wizualizację z presetu (niebieskie)
        if self.rect:
            self.canvas.delete(self.rect)
        self.canvas.delete("current_area") # Usuwa stary obszar po kliknięciu

        self.start_x = event.x
        self.start_y = event.y
        self.rect = self.canvas.create_rectangle(
            self.start_x, self.start_y, self.start_x, self.start_y, outline='red', width=3, dash=(5, 2))

    def on_mouse_drag(self, event):
        cur_x, cur_y = (event.x, event.y)
        self.canvas.coords(self.rect, self.start_x, self.start_y, cur_x, cur_y)  # type: ignore

    def on_mouse_up(self, event):
        end_x, end_y = (event.x, event.y)

        x = min(self.start_x, end_x)  # type: ignore
        y = min(self.start_y, end_y)  # type: ignore
        w = abs(self.start_x - end_x)
        h = abs(self.start_y - end_y)

        if w > 10 and h > 10:
            self.geometry = {'top': y, 'left': x, 'width': w, 'height': h}
            print(f"Wybrano geometrię: {self.geometry}")
        else:
            print("Wybór anulowany (za mały obszar).")
            self.geometry = None

        self.grab_release()
        self.destroy()
