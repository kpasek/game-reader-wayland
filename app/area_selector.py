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

        # Ustawienia pełnego ekranu i widoczności
        self.attributes('-fullscreen', True)
        self.attributes('-topmost', True)
        self.attributes('-alpha', 1.0)
        
        # Calculate scaling
        # We need to know the window size. Usually screen width/height.
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        img_w, img_h = screenshot.size
        
        self.scale_x = img_w / screen_w if screen_w else 1.0
        self.scale_y = img_h / screen_h if screen_h else 1.0
        
        # Prepare display image (resized if needed)
        self.display_img = screenshot
        if abs(self.scale_x - 1.0) > 0.01 or abs(self.scale_y - 1.0) > 0.01:
            self.display_img = screenshot.resize((screen_w, screen_h), Image.Resampling.LANCZOS)

        self.bg_img = ImageTk.PhotoImage(self.display_img)

        self.cv = tk.Canvas(self, cursor="cross", highlightthickness=0)
        self.cv.pack(fill=tk.BOTH, expand=True)
        self.cv.create_image(0, 0, image=self.bg_img, anchor=tk.NW)

        if existing_regions:
            for i, area_data in enumerate(existing_regions):
                # area_data can be dict with rect, id, colors
                # Handle nested rect or direct rect
                r = area_data.get('rect') if isinstance(area_data, dict) else area_data
                
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
                    continue
                
                if w <= 0 or h <= 0: continue
                
                # Scale from Physical to Logical (Window) for display
                x = int(x / self.scale_x)
                y = int(y / self.scale_y)
                w = int(w / self.scale_x)
                h = int(h / self.scale_y)
                
                # Determine color (default blue if missing or invalid)
                color = 'blue'
                colors = area_data.get('colors', [])
                if isinstance(area_data, dict) and colors and isinstance(colors, list) and len(colors) > 0:
                     color = colors[0]
                
                # Draw rect
                try:
                    self.cv.create_rectangle(x, y, x + w, y + h, outline=color, width=2, dash=(4, 4))
                    
                    # Draw label
                    aid = area_data.get('id', i+1) if isinstance(area_data, dict) else i+1
                    typ = area_data.get('type', '') if isinstance(area_data, dict) else ""
                    # Translate type for display
                    if typ == "continuous": typ = "Stały"
                    elif typ == "manual": typ = "Wyzwalany"
                    
                    label_txt = f"#{aid}"
                    if typ: label_txt += f" {typ}"
                    
                    # Label bg
                    self.cv.create_rectangle(x, y - 22, x + 80 + (len(typ)*6), y, fill=color, outline=color)
                    # Label text (black outline for contrast if needed, or just white)
                    self.cv.create_text(x + 5, y - 11, text=label_txt, fill="white", anchor=tk.W, font=("Arial", 10, "bold"))
                except Exception as e:
                    print(f"Error drawing region {i}: {e}")

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
            # Scale back to Physical for storage
            real_left = int(left * self.scale_x)
            real_top = int(top * self.scale_y)
            real_width = int(width * self.scale_x)
            real_height = int(height * self.scale_y)
            
            self.geometry = {'left': real_left, 'top': real_top, 'width': real_width, 'height': real_height}
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