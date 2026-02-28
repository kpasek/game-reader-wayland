"""Wrappers/fabryki widgetów oparte na customtkinter z fallbackiem na tkinter/ttk.

Umożliwia stopniową podmianę widgetów na CTk bez łamania kompatybilności.
Wszystkie funkcje akceptują podstawowe argumenty `text`, `command`, `variable` itd.
Widgety wspierają konfigurację koloru tekstu przez `fg` lub `text_color`.
"""
from typing import Any, Optional
import customtkinter as ctk

import tkinter as tk
from tkinter import ttk


def _apply_text_color(widget, text_color: Optional[str]):
    if not text_color:
        return
    try:
        # Prefer CTk's `text_color` kwarg; fall back to foreground/fg if needed.
        try:
            widget.configure(text_color=text_color)
            return
        except Exception:
            pass
        try:
            widget.configure(foreground=text_color)
            return
        except Exception:
            pass
        try:
            widget.configure(fg=text_color)
            return
        except Exception:
            pass
    except Exception:
        pass


def make_frame(master, **kwargs):
    # CTkFrame does not support `padding` kwarg (used by ttk).
    padding = kwargs.pop('padding', None)
    # Default to transparent background for a unified look
    kwargs.setdefault('fg_color', 'transparent')
    ctk_kwargs = {k: v for k, v in kwargs.items()}

    class _PaddingFrame(ctk.CTkFrame):
        def __init__(self, parent, pad=None, **kw):
            super().__init__(parent, **kw)
            self._pad = pad

        def _pad_values(self):
            if not self._pad:
                return {}
            # Accept int, (x,y) or (l,t,r,b)
            if isinstance(self._pad, int):
                return {'padx': self._pad, 'pady': self._pad}
            if isinstance(self._pad, (list, tuple)):
                if len(self._pad) == 2:
                    return {'padx': self._pad[0], 'pady': self._pad[1]}
                if len(self._pad) == 4:
                    # left,right,top,bottom -> horiz sum, vert sum
                    horiz = int(self._pad[0]) + int(self._pad[2])
                    vert = int(self._pad[1]) + int(self._pad[3])
                    return {'padx': horiz, 'pady': vert}
            return {}

        def pack(self, *args, **kwargs):
            pad = self._pad_values()
            for k, v in pad.items():
                kwargs.setdefault(k, v)
            return super().pack(*args, **kwargs)

        def grid(self, *args, **kwargs):
            pad = self._pad_values()
            for k, v in pad.items():
                kwargs.setdefault(k, v)
            return super().grid(*args, **kwargs)

        def place(self, *args, **kwargs):
            return super().place(*args, **kwargs)

    return _PaddingFrame(master, pad=padding, **ctk_kwargs)


def make_label(master, text: str = None, text_color: Optional[str] = None, **kwargs):
    w = ctk.CTkLabel(master, text=text, **kwargs)
    _apply_text_color(w, text_color)
    return w


def make_button(master, text: str = None, command: Any = None, text_color: Optional[str] = None, **kwargs):
    # Default modern styling
    kwargs.setdefault('height', 40)
    kwargs.setdefault('corner_radius', 12)
    kwargs.setdefault('font', ("Arial", 12, "bold"))
    w = ctk.CTkButton(master, text=text, command=command, **kwargs)
    _apply_text_color(w, text_color)
    return w


def make_scale(master, from_: float = 0.0, to: float = 1.0, variable=None, command=None, **kwargs):
    # Filter out kwargs unsupported by CTkSlider
    c_kwargs = {k: v for k, v in kwargs.items() if k not in ('orient', 'resolution', 'length')}
    # Default to transparent for slider container
    c_kwargs.setdefault('fg_color', 'transparent')

    class _SliderContainer(ctk.CTkFrame):
        def __init__(self, parent, **inner_kwargs):
            super().__init__(parent, **inner_kwargs)
            # Slider itself should have a bg inherited
            self._slider = ctk.CTkSlider(self, from_=from_, to=to, variable=variable, command=command)
            self._slider.pack(fill=tk.BOTH, expand=True)

        def bind(self, *args, **kwargs):
            return self._slider.bind(*args, **kwargs)

        def configure(self, *args, **kwargs):
            try:
                return self._slider.configure(*args, **{k: v for k, v in kwargs.items() if k in ('from_', 'to', 'variable', 'command')})
            except Exception:
                return None

        def __getattr__(self, item):
            return getattr(self._slider, item)

    return _SliderContainer(master, **c_kwargs)


# Backwards-compat alias: some modules call make_slider
def make_slider(master, **kwargs):
    # Map parameters pass-through to make_scale
    return make_scale(master, **kwargs)


def make_combobox(master, textvariable=None, values=None, state='readonly', width=None, **kwargs):
    # Prefer CTk's combo widget for visual consistency. Wrap it so clicks
    # on the whole control open the dropdown and common methods are proxied.
    params = {}
    if textvariable is not None:
        params['variable'] = textvariable
    params['values'] = values or []
    # Ensure transparency for combo container
    kwargs.setdefault('fg_color', 'transparent')
    params.update({k: v for k, v in kwargs.items() if k != 'fg_color'})

    class _ComboContainer(ctk.CTkFrame):
        def __init__(self, parent, **wrapper_kwargs):
            super().__init__(parent, **wrapper_kwargs)
            # Try to create CTkComboBox; if it fails, fallback to ttk.Combobox.
            try:
                self._combobox = ctk.CTkComboBox(self, **params)
            except Exception:
                cb_params = {}
                if textvariable is not None:
                    cb_params['textvariable'] = textvariable
                cb_params['values'] = values or []
                if width is not None:
                    cb_params['width'] = width
                cb_params.update(kwargs)
                cb_params['state'] = state
                self._combobox = ttk.Combobox(self, **cb_params)

            self._combobox.pack(fill=tk.X, expand=True)

            def _open(evt=None):
                try:
                    # Try to programmatically open the dropdown by simulating a click
                    self._combobox.event_generate('<Button-1>', x=1, y=1)
                except Exception:
                    try:
                        self._combobox.event_generate('<Down>')
                    except Exception:
                        pass

            # Bind clicks on both container and combobox to open dropdown.
            self.bind('<Button-1>', _open)
            try:
                self._combobox.bind('<Button-1>', _open)
            except Exception:
                pass

        def bind(self, *args, **kwargs):
            return self._combobox.bind(*args, **kwargs)

        def configure(self, *args, **kwargs):
            return self._combobox.configure(*args, **kwargs)

        def __getattr__(self, item):
            return getattr(self._combobox, item)

    return _ComboContainer(master)


def make_listbox(master, **kwargs):
    """Return a tk.Listbox. Kept as tk.Listbox because CTk has no direct
    Listbox equivalent; wrapping happens at the caller level if needed."""
    # Style the listbox to match CTk appearance mode.
    mode = None
    try:
        mode = ctk.get_appearance_mode()
    except Exception:
        mode = 'Dark'

    if mode == 'Dark':
        bg = '#2b2b2b'
        fg = '#eaeaea'
        sel_bg = '#1f6aa5'
        sel_fg = '#ffffff'
    else:
        bg = '#ffffff'
        fg = '#000000'
        sel_bg = '#1f6aa5'
        sel_fg = '#ffffff'

    params = {'bg': bg, 'fg': fg, 'selectbackground': sel_bg, 'selectforeground': sel_fg}
    params.update(kwargs)
    lb = tk.Listbox(master, **params)
    return lb


def make_entry(master, textvariable=None, **kwargs):
    # Create entry without textvariable first to avoid triggering
    # CTkEntry's textvariable callback before internal widgets exist.
    params = {k: v for k, v in kwargs.items()}
    entry = ctk.CTkEntry(master, **params)
    if textvariable is not None:
        try:
            # Defer setting textvariable until next event loop tick so
            # internal `self._entry` exists and callbacks won't run into
            # invalid widget names.
            master.after(0, lambda: entry.configure(textvariable=textvariable))
        except Exception:
            try:
                entry.configure(textvariable=textvariable)
            except Exception:
                pass
    return entry


def make_checkbutton(master, text: str = None, variable=None, command=None, **kwargs):
    params = {'text': text}
    if variable is not None:
        params['variable'] = variable
    if command is not None:
        params['command'] = command
    params.update(kwargs)
    return ctk.CTkCheckBox(master, **params)


# Expose some names for convenience
CTkFrame = ctk.CTkFrame
CTkLabel = ctk.CTkLabel
CTkToplevel = ctk.CTkToplevel


def make_labelframe(master, text: str = None, padding=None, **kwargs):
    wrapper = ctk.CTkFrame(master, **{k: v for k, v in kwargs.items() if k != 'padding'})
    if text is not None:
        lbl = ctk.CTkLabel(wrapper, text=text)
        lbl.pack(side='top', anchor='w', padx=6, pady=(4, 2))
    return wrapper


def make_separator(master, orient='horizontal', **kwargs):
    return ttk.Separator(master, orient=orient, **kwargs)


def make_scrollbar(master, orient='vertical', command=None, **kwargs):
    params = {'orient': orient}
    if command is not None:
        params['command'] = command
    params.update(kwargs)
    return ttk.Scrollbar(master, **params)


def make_notebook(master, **kwargs):
    return ctk.CTkTabview(master, **kwargs)


def make_progressbar(master, mode='indeterminate', **kwargs):
    return ttk.Progressbar(master, mode=mode, **kwargs)


def make_notebook_tab(notebook, text: str):
    """Create and return a tab/frame for the given notebook/tabview.

    For CTkTabview, `notebook.add(text)` is used and the internal tab frame
    is returned. For ttk.Notebook, a new frame is created and added.
    """
    notebook.add(text)
    internal = notebook.tab(text)
    try:
        if isinstance(internal, tk.Widget):
            container = ctk.CTkFrame(internal)
            container.pack(fill=tk.BOTH, expand=True)
            return container
    except Exception:
        pass
    frame = ctk.CTkFrame(notebook)
    frame.pack(fill=tk.BOTH, expand=True)
    return frame
