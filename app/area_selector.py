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
    Zwraca słownik geometrii w self.geometry (współrzędne względem oryginalnego screenshotu).
    """

    def __init__(self, parent, screenshot: Image.Image, existing_regions: list = None):
        super().__init__(parent)
        self.geometry = None
        self.start_x = None
        self.start_y = None
        self.rect_id = None
        self.original_screenshot = screenshot # Original physical image
        # NIE przeliczamy do 4K – AreaSelector operuje na pikselach ekranu

        # Ustawienia pełnego ekranu i widoczności
        self.attributes('-fullscreen', True)
        self.attributes('-topmost', True)
        self.attributes('-alpha', 1.0)
        

        # Calculate scaling
        # We need to know the window size. Usually screen width/height.
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        img_w, img_h = screenshot.size
        print(f"[AreaSelector] screen_w={screen_w}, screen_h={screen_h}, img_w={img_w}, img_h={img_h}")
        self.scale_x = img_w / screen_w if screen_w else 1.0
        self.scale_y = img_h / screen_h if screen_h else 1.0
        print(f"[AreaSelector] scale_x={self.scale_x}, scale_y={self.scale_y}")

        # NIE zapisujemy rozdzielczości do presetów!

        # Prepare display image (resized if needed)
        self.display_img = screenshot
        if abs(self.scale_x - 1.0) > 0.01 or abs(self.scale_y - 1.0) > 0.01:
            self.display_img = screenshot.resize((screen_w, screen_h), Image.Resampling.LANCZOS)

        self.bg_img = ImageTk.PhotoImage(self.display_img)

        # self.cv = tk.Canvas(self, cursor="cross", highlightthickness=0)
        # self.cv.pack(fill=tk.BOTH, expand=True)
        # self.cv.create_image(0, 0, image=self.bg_img, anchor=tk.NW)
        self.cv = tk.Canvas(self, cursor="cross", highlightthickness=0)
        self.cv.pack(fill=tk.BOTH, expand=True)
        self.cv.create_image(0, 0, image=self.bg_img, anchor=tk.NW)

        if existing_regions:
            import traceback
            print(f"[AreaSelector][LOG] Otrzymane existing_regions: type={type(existing_regions)}, value={existing_regions}")
            traceback.print_stack(limit=4)
            for i, area_data in enumerate(existing_regions):
                print(f"[AreaSelector][LOG] existing_regions[{i}]: type={type(area_data)}, value={area_data}")
                # area_data can be:
                # - dict wrapper {'rect': {...}, 'id':..., 'colors':...}
                # - direct rect dict {left, top, width, height} (legacy)
                # - list/tuple (x,y,w,h)
                # Detect wrapper vs direct rect robustly
                r = None
                if isinstance(area_data, dict):
                    if 'rect' in area_data and area_data.get('rect') is not None:
                        r = area_data.get('rect')
                        print(f"[AreaSelector][LOG] Detected wrapper dict with 'rect' for region #{i}")
                    else:
                        # Might be a direct rect dict (has left/top/width/height)
                        if any(k in area_data for k in ('left', 'top', 'width', 'height', 'x', 'y', 'w', 'h')):
                            r = area_data
                            print(f"[AreaSelector][LOG] Detected direct rect dict for region #{i}")
                        else:
                            r = None
                else:
                    r = area_data
                print(f"[AreaSelector][LOG] existing_regions[{i}] rect: type={type(r)}, value={r}")
                # Normalize r to (x, y, w, h)
                x, y, w, h = 0, 0, 0, 0
                if isinstance(r, dict):
                    x = r.get('left', r.get('x', 0))
                    y = r.get('top', r.get('y', 0))
                    w = r.get('width', r.get('w', 0))
                    h = r.get('height', r.get('h', 0))
                elif isinstance(r, (list, tuple)) and len(r) >= 4:
                    x, y, w, h = r[0], r[1], r[2], r[3]
                else:
                    print(f"[AreaSelector][LOG] Pomijam region #{i} (nieprawidłowy format): {r}")
                    continue
                if w <= 0 or h <= 0:
                    print(f"[AreaSelector][LOG] Pomijam region #{i} (zerowy rozmiar): x={x}, y={y}, w={w}, h={h}")
                    continue
                # NIE przeliczamy do 4K! Rysujemy to co dostajemy (ekran)
                x_log = int(x)
                y_log = int(y)
                w_log = int(w)
                h_log = int(h)
                color = 'blue'
                colors = area_data.get('colors', []) if isinstance(area_data, dict) else []
                if colors and isinstance(colors, list) and len(colors) > 0:
                    color = colors[0]
                screen_w = self.winfo_screenwidth()
                screen_h = self.winfo_screenheight()
                print(f"[AreaSelector][LOG] create_rectangle: x={x_log}, y={y_log}, x2={x_log + w_log}, y2={y_log + h_log}, color={color}, screen_w={screen_w}, screen_h={screen_h}")
                if x_log < 0 or y_log < 0 or x_log + w_log > screen_w or y_log + h_log > screen_h:
                    print(f"[AreaSelector][WARN] Prostokąt #{i} wykracza poza ekran: x={x_log}, y={y_log}, w={w_log}, h={h_log}, screen_w={screen_w}, screen_h={screen_h}")
                try:
                    rect_id = self.cv.create_rectangle(x_log, y_log, x_log + w_log, y_log + h_log, outline=color, width=2, dash=(4, 4))
                    print(f"[AreaSelector][LOG] Rysuję region #{i}: x={x}, y={y}, w={w}, h={h} (ekran), kolor={color}, rect_id={rect_id}")
                    aid = area_data.get('id', i+1) if isinstance(area_data, dict) else i+1
                    typ = area_data.get('type', '') if isinstance(area_data, dict) else ""
                    print(f"[AreaSelector][LOG] Region #{i} typ: {typ}")
                except Exception as e:
                    print(f"[AreaSelector][ERR] Error drawing region {i}: {e}")
                    traceback.print_exc()
                    # Label bg
                    self.cv.create_rectangle(x, y - 22, x + 80 + (len(str(typ))*6), y, fill=color, outline=color)
                    # Label text (black outline for contrast if needed, or just white)
                    self.cv.create_text(x + 5, y - 11, text=str(aid), fill="white", anchor=tk.W, font=("Arial", 10, "bold"))

        self.cv.bind("<ButtonPress-1>", self.on_press)
        self.cv.bind("<B1-Motion>", self.on_drag)
        self.cv.bind("<ButtonRelease-1>", self.on_release)
        self.bind("<Escape>", lambda e: self.destroy())

        # Informacja dla usera
        self.lbl_info = tk.Label(self, text="Zaznacz obszar myszką (ESC aby anulować)", bg="yellow", font=("Arial", 12))
        self.lbl_info.place(x=10, y=10)

        # Focus i czekanie na okno
        self.update() # Ensure window is created
        self.focus_force()
        try:
             self.wait_visibility()
             self.grab_set()
             self.wait_window()
        except tk.TclError:
             pass # Window destroyed or bad path

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
            self.geometry = {
                'left': int(left),
                'top': int(top),
                'width': int(width),
                'height': int(height)
            }
            print(f"[AreaSelector] Zaznaczenie (ekran): left={left}, top={top}, width={width}, height={height}")
        self.destroy()


class ColorSelector(tk.Toplevel):
    def __init__(self, parent, screenshot: Image.Image):
        super().__init__(parent)
        self.original_screenshot = screenshot # Physical
        self.selected_color = None
        
        # ZOOM CONFIG
        self.zoom_level = 8
        self.view_size = 160  # Size of the magnifier window (pixels)
        
        self.attributes('-fullscreen', True)
        self.attributes('-topmost', True)
        self.attributes('-alpha', 1.0)
        
        # Scale handling
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        img_w, img_h = screenshot.size
        
        self.scale_x = img_w / screen_w if screen_w else 1.0
        self.scale_y = img_h / screen_h if screen_h else 1.0
        
        self.display_img = screenshot
        if abs(self.scale_x - 1.0) > 0.01 or abs(self.scale_y - 1.0) > 0.01:
            self.display_img = screenshot.resize((screen_w, screen_h), Image.Resampling.LANCZOS)
        
        self.bg_photo = ImageTk.PhotoImage(self.display_img)
        
        self.cv = tk.Canvas(self, cursor="crosshair", highlightthickness=0)
        self.cv.pack(fill=tk.BOTH, expand=True)
        self.cv.create_image(0, 0, image=self.bg_photo, anchor=tk.NW)
        
        # Magnifier Window (Canvas)
        self.mag_cv = tk.Canvas(self, width=self.view_size, height=self.view_size, 
                             highlightthickness=2, highlightbackground="#000000", bg="black")
        self.mag_cv.place(x=-1000, y=-1000) # Hide initially
        
        self.bind("<Escape>", lambda e: self.destroy())
        self.cv.bind("<Button-1>", self.on_click)
        self.cv.bind("<Motion>", self.on_move)
        
        self.focus_force()
        self.wait_visibility()
        self.grab_set()
        self.wait_window()

    def on_move(self, event):
        # Coordinates in logical screen space (window space)
        win_x, win_y = event.x, event.y
        
        # Coordinates in original image space (physical)
        phys_x = int(win_x * self.scale_x)
        phys_y = int(win_y * self.scale_y)
        
        # Show magnifier offset from cursor
        offset = 20
        mx, my = win_x + offset, win_y + offset
        
        # Keep magnifier inside screen
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        
        if mx + self.view_size > screen_w:
            mx = win_x - offset - self.view_size
        if my + self.view_size > screen_h:
            my = win_y - offset - self.view_size
            
        self.mag_cv.place(x=mx, y=my)
        
        # Extract pixel data from ORIGINAL screenshot using physical coords.
        phys_w, phys_h = self.original_screenshot.size
        
        radius = (self.view_size // self.zoom_level) // 2
        
        box_left = phys_x - radius
        box_top = phys_y - radius
        box_right = phys_x + radius + 1
        box_bottom = phys_y + radius + 1
        
        safe_box = (
            max(0, box_left), 
            max(0, box_top), 
            min(phys_w, box_right), 
            min(phys_h, box_bottom)
        )
        
        if safe_box[2] <= safe_box[0] or safe_box[3] <= safe_box[1]:
             return
             
        region = self.original_screenshot.crop(safe_box)
        
        target_w = region.width * self.zoom_level
        target_h = region.height * self.zoom_level
        
        resized = region.resize((target_w, target_h), Image.Resampling.NEAREST)
        self.mag_img = ImageTk.PhotoImage(resized) 
        
        self.mag_cv.delete("all")
        self.mag_cv.create_image(self.view_size//2, self.view_size//2, image=self.mag_img, anchor=tk.CENTER)
        
        # Draw red box
        cx, cy = self.view_size // 2, self.view_size // 2
        box_half = self.zoom_level // 2
        
        self.mag_cv.create_rectangle(cx - box_half, cy - box_half, 
                                     cx + box_half, cy + box_half, 
                                     outline="red", width=2)
        
        # Show Color HEX
        try:
             # Use safe clamps for getpixel just in case
             px = max(0, min(phys_x, phys_w - 1))
             py = max(0, min(phys_y, phys_h - 1))
             rgb = self.original_screenshot.getpixel((px, py))
             if isinstance(rgb, tuple):
                 hex_col = "#{:02x}{:02x}{:02x}".format(rgb[0], rgb[1], rgb[2])
                 tx, ty = self.view_size // 2, self.view_size - 15
                 self.mag_cv.create_text(tx+1, ty+1, text=hex_col, fill="black", font=("Arial", 11, "bold"))
                 self.mag_cv.create_text(tx, ty, text=hex_col, fill="white", font=("Arial", 11, "bold"))
        except Exception: 
            pass

    def on_click(self, event):
        win_x, win_y = event.x, event.y
        phys_x = int(win_x * self.scale_x)
        phys_y = int(win_y * self.scale_y)
        
        if 0 <= phys_x < self.original_screenshot.width and 0 <= phys_y < self.original_screenshot.height:
            rgb = self.original_screenshot.getpixel((phys_x, phys_y))
            if isinstance(rgb, tuple) and len(rgb) >= 3:
                r, g, b = rgb[0], rgb[1], rgb[2]
                self.selected_color = "#{:02x}{:02x}{:02x}".format(r, g, b)

        self.destroy()