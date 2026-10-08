"""UI components: charts, thin scrollbar, tooltip.

All drawn by hand on a Canvas, no external dependencies.
"""

import tkinter as tk
from datetime import timedelta

import theme


class Tooltip:
    """Small info bubble that appears next to the cursor."""

    def __init__(self, root, palette):
        self.root = root
        self.palette = palette
        self.window = None
        self.label = None

    def set_palette(self, palette):
        self.palette = palette
        self.hide()

    def show(self, text, x, y):
        if not text:
            return self.hide()
        if self.window is None:
            self.window = tk.Toplevel(self.root)
            self.window.wm_overrideredirect(True)
            self.window.wm_attributes("-topmost", True)
            self.label = tk.Label(self.window, text=text,
                                  font=theme.font("small"),
                                  bg=self.palette["surface_3"],
                                  fg=self.palette["text"],
                                  padx=9, pady=5, justify="left")
            self.label.pack()
        else:
            self.label.configure(text=text, bg=self.palette["surface_3"],
                                 fg=self.palette["text"])
        try:
            self.window.wm_geometry(f"+{int(x) + 14}+{int(y) + 18}")
            self.window.deiconify()
        except tk.TclError:
            pass

    def hide(self):
        if self.window is not None:
            try:
                self.window.withdraw()
            except tk.TclError:
                self.window = None

    def attach(self, widget, provider):
        """provider() -> text to show (or None)."""
        widget.bind("<Enter>", lambda e: self.show(provider(), e.x_root, e.y_root),
                    add="+")
        widget.bind("<Motion>", lambda e: self.show(provider(), e.x_root, e.y_root),
                    add="+")
        widget.bind("<Leave>", lambda e: self.hide(), add="+")


class BarChart(tk.Canvas):
    """Bar chart of daily totals. Shows the value on hover."""

    PAD_TOP = 14
    PAD_BOTTOM = 24
    PAD_RIGHT = 34
    PAD_LEFT = 2

    def __init__(self, parent, palette, height=160, on_hover=None, **kw):
        super().__init__(parent, height=height, highlightthickness=0, bd=0,
                         bg=palette["surface"], **kw)
        self.palette = palette
        self.points = []            # [(date_str, value, label)]
        self.value_fmt = str
        self.axis_fmt = str
        self.highlight_last = True
        self.on_hover = on_hover
        self._hover_index = None
        self._bars = []

        self.bind("<Configure>", lambda e: self.redraw())
        self.bind("<Motion>", self._on_motion)
        self.bind("<Leave>", self._on_leave)

    def set_palette(self, palette):
        self.palette = palette
        self.configure(bg=palette["surface"])
        self.redraw()

    @staticmethod
    def _signature(points):
        """Changes too small to see must not trigger a redraw.

        Today's bar grows by a tiny fraction of a pixel every second; rounded
        to 30 seconds, the chart redraws about once a minute.
        """
        return tuple((key, round(value / 30), label) for key, value, label in points)

    def set_data(self, points, value_fmt=None, axis_fmt=None):
        points = list(points)
        if value_fmt:
            self.value_fmt = value_fmt
        if axis_fmt:
            self.axis_fmt = axis_fmt

        signature = self._signature(points)
        changed = signature != getattr(self, "_data_signature", None)
        self.points = points
        if not changed:
            return
        self._data_signature = signature
        self._hover_index = None
        self.redraw()

    # -- drawing -----------------------------------------------------------

    def _nice_max(self, raw_max):
        if raw_max <= 0:
            return 3600
        steps = [900, 1800, 3600, 7200, 10800, 14400, 21600, 28800, 36000,
                 43200, 57600, 72000, 86400]
        for step in steps:
            if raw_max <= step:
                return step
        return ((int(raw_max) // 86400) + 1) * 86400

    def redraw(self):
        self.delete("all")
        self._bars = []
        width = self.winfo_width()
        height = self.winfo_height()
        if width < 40 or height < 40:
            return

        pal = self.palette
        plot_left = self.PAD_LEFT
        plot_right = width - self.PAD_RIGHT
        plot_top = self.PAD_TOP
        plot_bottom = height - self.PAD_BOTTOM
        plot_w = plot_right - plot_left
        plot_h = plot_bottom - plot_top
        if plot_w <= 0 or plot_h <= 0:
            return

        if not self.points:
            self.create_text(width / 2, height / 2, text="", fill=pal["text_faint"])
            return

        top_value = self._nice_max(max((v for _, v, _ in self.points), default=0))

        # horizontal grid lines and axis labels
        for fraction in (0.0, 0.5, 1.0):
            y = plot_bottom - plot_h * fraction
            self.create_line(plot_left, y, plot_right, y,
                             fill=pal["border"], width=1)
            if fraction > 0:
                self.create_text(plot_right + 8, y, anchor="w",
                                 text=self.axis_fmt(top_value * fraction),
                                 fill=pal["text_faint"], font=theme.font("caption"))

        count = len(self.points)
        slot = plot_w / count
        gap = 3 if slot > 12 else (2 if slot > 6 else 1)
        bar_w = max(1.0, slot - gap)

        base = pal["accent"]
        idle = theme.mix(base, pal["surface"], 0.55)

        for index, (key, value, _label) in enumerate(self.points):
            x0 = plot_left + slot * index + gap / 2
            x1 = x0 + bar_w
            ratio = (value / top_value) if top_value else 0
            bar_h = plot_h * min(1.0, ratio)
            y0 = plot_bottom - bar_h
            is_last = self.highlight_last and index == count - 1
            color = base if is_last else idle
            if value <= 0:
                # a thin baseline so an empty day does not vanish entirely
                self.create_line(x0, plot_bottom, x1, plot_bottom,
                                 fill=pal["border"], width=1)
            else:
                self.create_rectangle(x0, y0, x1, plot_bottom,
                                      fill=color, outline="")
            self._bars.append((x0 - gap / 2, x0 + slot - gap / 2, index))

        self._draw_x_labels(plot_left, plot_bottom, slot, count, pal)

        if self._hover_index is not None:
            self._draw_tooltip(self._hover_index, plot_left, plot_top,
                               plot_bottom, slot, width)

    def _draw_x_labels(self, plot_left, plot_bottom, slot, count, pal):
        max_labels = 7
        step = max(1, count // max_labels)
        for index in range(count - 1, -1, -step):
            key, _value, label = self.points[index]
            x = plot_left + slot * index + slot / 2
            self.create_text(x, plot_bottom + 12, text=label, anchor="n",
                             fill=pal["text_faint"], font=theme.font("caption"))

    def _draw_tooltip(self, index, plot_left, plot_top, plot_bottom, slot, width):
        pal = self.palette
        key, value, label = self.points[index]
        x = plot_left + slot * index + slot / 2

        self.create_line(x, plot_top, x, plot_bottom,
                         fill=theme.mix(pal["text_faint"], pal["surface"], 0.5),
                         width=1)

        text = f"{label}   {self.value_fmt(value)}"
        pad = 7
        est_w = max(70, len(text) * 6 + pad * 2)
        box_x0 = min(max(x - est_w / 2, 2), width - est_w - 2)
        box_y0 = plot_top - 2
        self.create_rectangle(box_x0, box_y0, box_x0 + est_w, box_y0 + 22,
                              fill=pal["surface_3"], outline=pal["border"])
        self.create_text(box_x0 + est_w / 2, box_y0 + 11, text=text,
                         fill=pal["text"], font=theme.font("caption"))

    # -- interaction -------------------------------------------------------

    def _on_motion(self, event):
        found = None
        for x0, x1, index in self._bars:
            if x0 <= event.x <= x1:
                found = index
                break
        if found != self._hover_index:
            self._hover_index = found
            self.redraw()
            if self.on_hover:
                self.on_hover(self.points[found] if found is not None else None)

    def _on_leave(self, _event):
        if self._hover_index is not None:
            self._hover_index = None
            self.redraw()
            if self.on_hover:
                self.on_hover(None)


class CompositionBar(tk.Canvas):
    """Single-row stacked bar showing the period's composition."""

    def __init__(self, parent, palette, height=10, **kw):
        super().__init__(parent, height=height, highlightthickness=0, bd=0,
                         bg=palette["surface"], **kw)
        self.palette = palette
        self.segments = []          # [(label, value, color)]
        self.bind("<Configure>", lambda e: self.redraw())

    def set_palette(self, palette):
        self.palette = palette
        self.configure(bg=palette["surface"])
        self.redraw()

    def set_data(self, segments):
        segments = list(segments)
        total = sum(value for _l, value, _c in segments) or 1
        signature = tuple((label, round(value / total, 4), color)
                          for label, value, color in segments)
        self.segments = segments
        if signature == getattr(self, "_data_signature", None):
            return
        self._data_signature = signature
        self.redraw()

    def redraw(self):
        self.delete("all")
        width = self.winfo_width()
        height = self.winfo_height()
        if width < 20 or height < 4:
            return

        total = sum(value for _l, value, _c in self.segments)
        if total <= 0:
            self.create_rectangle(0, 0, width, height,
                                  fill=self.palette["surface_2"], outline="")
            return

        x = 0.0
        gap = 2
        for index, (_label, value, color) in enumerate(self.segments):
            share = value / total
            seg_w = max(2.0, width * share - gap)
            self.create_rectangle(x, 0, x + seg_w, height, fill=color, outline="")
            x += seg_w + gap


class SlimScrollbar(tk.Canvas):
    """Thin, theme-aware scrollbar. Hides itself when the content fits."""

    MIN_THUMB = 24

    def __init__(self, parent, palette, command=None, width=6, **kw):
        super().__init__(parent, width=width, highlightthickness=0, bd=0,
                         bg=palette["surface"], **kw)
        self.palette = palette
        self.command = command
        self._first, self._last = 0.0, 1.0
        self._drag = None

        self.bind("<Configure>", lambda e: self.redraw())
        self.bind("<Button-1>", self._on_press)
        self.bind("<B1-Motion>", self._on_drag)
        self.bind("<ButtonRelease-1>", lambda e: setattr(self, "_drag", None))
        self.bind("<Enter>", lambda e: self.redraw(hot=True))
        self.bind("<Leave>", lambda e: self.redraw(hot=False))

    def set(self, first, last):
        """Tkinter yscrollcommand interface."""
        try:
            self._first, self._last = float(first), float(last)
        except (TypeError, ValueError):
            return
        self.redraw()

    def _thumb_bounds(self):
        height = self.winfo_height()
        span = max(0.0, self._last - self._first)
        thumb_h = max(self.MIN_THUMB, height * span)
        travel = height - thumb_h
        y0 = travel * (self._first / (1 - span)) if span < 1 else 0
        return y0, y0 + thumb_h

    def redraw(self, hot=False):
        self.delete("all")
        width = self.winfo_width()
        height = self.winfo_height()
        if height < 12 or width < 2:
            return
        if self._last - self._first >= 0.999:
            return  # no bar when the content fits entirely

        y0, y1 = self._thumb_bounds()
        color = self.palette["text_faint"] if hot else self.palette["surface_3"]
        self.create_rectangle(1, y0, width - 1, y1, fill=color, outline="")

    def _on_press(self, event):
        y0, y1 = self._thumb_bounds()
        if y0 <= event.y <= y1:
            self._drag = (event.y, self._first)
        else:
            self._move_to(event.y - (y1 - y0) / 2)

    def _on_drag(self, event):
        if not self._drag:
            return
        start_y, start_first = self._drag
        height = max(1, self.winfo_height())
        span = max(0.0, self._last - self._first)
        travel = max(1.0, height - max(self.MIN_THUMB, height * span))
        delta = (event.y - start_y) / travel * (1 - span)
        self._apply(start_first + delta)

    def _move_to(self, y):
        height = max(1, self.winfo_height())
        self._apply(y / height)

    def _apply(self, fraction):
        if self.command:
            self.command("moveto", max(0.0, min(1.0, fraction)))
