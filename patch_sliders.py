import re

with open("app/optimization_wizard.py", "r") as f:
    content = f.read()

# 1. Update text labels to reflect new ranges
content = content.replace('Kolor: Tolerancja kolorów [1-255]', 'Kolor: Tolerancja kolorów [1-100]')
content = content.replace('Jasność: Próg jasności [0-255]', 'Jasność: Próg jasności [100-255]')
content = content.replace('Pogrubienie czcionki [px]', 'Pogrubienie czcionki [0-3 px]')

# 2. Update widget limits in _make_range_slider calls
content = re.sub(r'self._make_range_slider\(lf_color, self.var_color_tol_min, self.var_color_tol_max, 1, 255\)', 
                 r'self._make_range_slider(lf_color, self.var_color_tol_min, self.var_color_tol_max, 1, 100)', content)

content = re.sub(r'self._make_range_slider\(lf_bright, self.var_bright_min, self.var_bright_max, 0, 255\)', 
                 r'self._make_range_slider(lf_bright, self.var_bright_min, self.var_bright_max, 100, 255)', content)

content = re.sub(r'self._make_range_slider\(lf_common, self.var_thick_min, self.var_thick_max, 0, 5, \)',
                 r'self._make_range_slider(lf_common, self.var_thick_min, self.var_thick_max, 0, 3, step=1)', content)

content = re.sub(r'self._make_range_slider\(lf_common, self.var_scale_min, self.var_scale_max, 0.1, 2.0, step=0.05\)',
                 r'self._make_range_slider(lf_common, self.var_scale_min, self.var_scale_max, 0.1, 2.0, step=0.05)', content)

# Update var_bright_min default value from 0.3 which was my mistake, or 0, to 100. Actually it depends on current state.
content = re.sub(r'self.var_bright_min = tk.IntVar\(value=.*?\)', r'self.var_bright_min = tk.IntVar(value=100)', content)

# 3. Rewrite _make_range_slider method to use sliders
old_slider_method = """    def _make_range_slider(self, parent, var_min, var_max, min_val, max_val, is_grid=False, row=0, step=1):
        f = make_frame(parent)
        if is_grid:
            f
            parent.columnconfigure(0, weight=1)
        else:
            f.pack(fill=tk.X, padx=5)

        make_label(f, text="Min:").pack(side=tk.LEFT)
        make_entry(f, textvariable=var_min, width=40).pack(side=tk.LEFT, padx=5)
        
        make_label(f, text="Max:").pack(side=tk.LEFT, padx=(10, 0))
        make_entry(f, textvariable=var_max, width=40).pack(side=tk.LEFT, padx=5)"""

new_slider_method = """    def _make_range_slider(self, parent, var_min, var_max, min_val, max_val, is_grid=False, row=0, step=1):
        f = make_frame(parent, fg_color="transparent")
        f.pack(fill=tk.X, padx=10, pady=5)

        is_float = isinstance(step, float)
        fmt = "{:.2f}" if is_float else "{:.0f}"

        lbl_min = make_label(f, text="Min:")
        lbl_min.grid(row=0, column=0, padx=(0, 10))
        scale_min = make_scale(f, from_=min_val, to=max_val, variable=var_min)
        scale_min.grid(row=0, column=1, sticky='ew', padx=5, pady=2)
        val_min = make_label(f, text=fmt.format(var_min.get()), width=40)
        val_min.grid(row=0, column=2, padx=(10, 0))

        lbl_max = make_label(f, text="Max:")
        lbl_max.grid(row=1, column=0, padx=(0, 10))
        scale_max = make_scale(f, from_=min_val, to=max_val, variable=var_max)
        scale_max.grid(row=1, column=1, sticky='ew', padx=5, pady=2)
        val_max = make_label(f, text=fmt.format(var_max.get()), width=40)
        val_max.grid(row=1, column=2, padx=(10, 0))

        f.columnconfigure(1, weight=1)

        def update_labels(*args):
            # enforce limits (cross-over)
            if var_min.get() > var_max.get():
                if args and len(args) > 0 and args[0] == str(var_min): # min driven
                    var_min.set(var_max.get())
                else:
                    var_max.set(var_min.get())
                    
            if not is_float:
                # Snap to int
                var_min.set(int(round(var_min.get())))
                var_max.set(int(round(var_max.get())))
                
            val_min.configure(text=fmt.format(var_min.get()))
            val_max.configure(text=fmt.format(var_max.get()))

        scale_min.configure(command=lambda v: update_labels())
        scale_max.configure(command=lambda v: update_labels())
        # Initial update
        update_labels()"""

if old_slider_method in content:
    content = content.replace(old_slider_method, new_slider_method)
else:
    print("WARNING: Could not find old slider method exact match!")
    # Trying regex fallback
    import re
    patt = re.compile(r'def _make_range_slider.*?(?=def _build_instruction_tab)', re.DOTALL | re.MULTILINE)
    content = patt.sub(new_slider_method + "\n\n    ", content)

with open("app/optimization_wizard.py", "w") as f:
    f.write(content)
