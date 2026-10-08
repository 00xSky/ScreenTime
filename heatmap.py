"""Intensity heatmap and day-of-week profile.

The heatmap has three distinct states and each looks different:
  - no record      : empty square, thin outline only
  - record, zero   : lightest fill
  - usage         : four levels by intensity

Levels are set by percentiles; on skewed data a linear scale pushes
everything into the lightest tone and leaves a single dark square.
"""

import tkinter as tk
from datetime import timedelta

import theme

DASH = "—"


class Heatmap(tk.Canvas):
    """Daily intensity map laid out like the GitHub contribution graph."""

    LABEL_W = 30
    HEAD_H = 18
    SCALE_H = 20
    GAP = 4
    MIN_CELL = 6
    MAX_CELL = 40

    def __init__(self, parent, palette, height=196, **kw):
        super().__init__(parent, height=height, highlightthickness=0, bd=0,
                         bg=palette["surface"], **kw)
        self.palette = palette
        self.days = []              # [(date, seconds|None)]
        self.month_labels = []
        self.weekday_labels = []
        self.value_fmt = str
        self.date_fmt = str
        self.highlight = None       # (start, end) | None
        self.scale_low = "less"
        self.scale_high = "more"
        self.no_record = DASH
        self.on_hover = None
        self._cells = []            # (x0, y0, x1, y1, index)
        self._hover = None
        self._hover_xy = (0, 0)
        self._signature = None

        self.bind("<Configure>", lambda e: self.redraw())
        self.bind("<Motion>", self._on_motion)
        self.bind("<Leave>", self._on_leave)

    def set_palette(self, palette):
        self.palette = palette
        self.configure(bg=palette["surface"])
        self._signature = None
        self.redraw()

    def set_labels(self, low, high, no_record):
        self.scale_low, self.scale_high, self.no_record = low, high, no_record

    def set_data(self, days, month_labels, weekday_labels,
                 value_fmt=None, date_fmt=None, highlight=None):
        signature = (tuple((d, None if v is None else round(v / 60))
                           for d, v in days), highlight)
        self.days = list(days)
        self.month_labels = month_labels
        self.weekday_labels = weekday_labels
        self.highlight = highlight
        if value_fmt:
            self.value_fmt = value_fmt
        if date_fmt:
            self.date_fmt = date_fmt
        if signature == self._signature:
            return
        self._signature = signature
        self._hover = None
        self.redraw()

    # -- color levels ------------------------------------------------------

    def _thresholds(self):
        values = sorted(v for _d, v in self.days if v)
        if not values:
            return []
        return [values[int(len(values) * q)] for q in (0.25, 0.5, 0.75)]

    def _level_colors(self):
        pal = self.palette
        base, soft = pal["accent"], pal["accent_soft"]
        return [pal["surface_2"], soft,
                theme.mix(soft, base, 0.45),
                theme.mix(soft, base, 0.75), base]

    @staticmethod
    def _level(value, thresholds):
        if not value:
            return 0
        level = 1
        for edge in thresholds:
            if value > edge:
                level += 1
        return min(level, 4)

    # -- drawing -----------------------------------------------------------

    def redraw(self):
        self.delete("all")
        self._cells = []
        width = self.winfo_width()
        height = self.winfo_height()
        if width < 80 or not self.days:
            return

        pal = self.palette
        first_date = self.days[0][0]
        grid_start = first_date - timedelta(days=first_date.weekday())
        weeks = ((self.days[-1][0] - grid_start).days // 7) + 1

        # The grid fills the card's width exactly: the step stays fractional,
        # so no gap is left at the right edge when the window is resized.
        available = width - self.LABEL_W - 4
        step = available / max(1, weeks)
        cell = max(self.MIN_CELL, min(self.MAX_CELL, step - self.GAP))
        step = cell + self.GAP
        top = self.HEAD_H

        # Height follows the cell size derived from the width. The canvas
        # reports the height it wants and the layout follows.
        needed = int(self.HEAD_H + 7 * step + self.SCALE_H)
        if abs(self.winfo_reqheight() - needed) > 1:
            self.configure(height=needed)
            return  # a new <Configure> will redraw at this size

        thresholds = self._thresholds()
        colors = self._level_colors()
        ring = theme.mix(pal["accent"], pal["surface"], 0.3)

        seen_months = set()
        last_label_x = -999
        for index, (date, value) in enumerate(self.days):
            column = (date - grid_start).days // 7
            x0 = self.LABEL_W + column * step
            y0 = top + date.weekday() * step
            x1, y1 = x0 + cell, y0 + cell

            if value is None:
                # No record: an unfilled, visible gap. It must be distinguishable
                # from zero usage, otherwise "I never opened it that day" and
                # "the program was not running that day" look the same.
                self.create_rectangle(x0, y0, x1, y1, fill=pal["surface"],
                                      outline=theme.mix(pal["border"],
                                                        pal["text_faint"], 0.55),
                                      width=1)
            else:
                outline, border = "", 0
                if self.highlight and self.highlight[0] <= date <= self.highlight[1]:
                    outline, border = ring, 1
                self.create_rectangle(x0, y0, x1, y1,
                                      fill=colors[self._level(value, thresholds)],
                                      outline=outline, width=border)
            self._cells.append((x0, y0, x1, y1, index))

            # Label the first visible week of each month. If the first day falls
            # mid-month (data starting on 27 Jan, say) that month still gets a label.
            key = (date.year, date.month)
            if key not in seen_months and (date.day <= 7 or
                                           (index == 0 and date.day <= 20)):
                seen_months.add(key)
                # If a month start sits right next to a mid-month first day,
                # the labels overlap; leave at least one label width
                if x0 - last_label_x >= 26:
                    last_label_x = x0
                    self.create_text(x0, top - 7, anchor="w",
                                     text=self.month_labels[date.month - 1],
                                     fill=pal["text_faint"],
                                     font=theme.font("caption"))

        for row in (0, 2, 4):
            self.create_text(self.LABEL_W - 7, top + row * step + cell / 2,
                             anchor="e", text=self.weekday_labels[row],
                             fill=pal["text_faint"], font=theme.font("caption"))

        self._draw_scale(self.LABEL_W, top + 7 * step + 6, colors, width)

        if self._hover is not None:
            self._draw_tooltip(width, height)

    def _draw_scale(self, x, y, colors, width):
        """less [][][][][] more"""
        pal = self.palette
        size = 9
        self.create_text(x, y + size / 2, anchor="w", text=self.scale_low,
                         fill=pal["text_faint"], font=theme.font("caption"))
        left = x + 22
        for color in colors:
            self.create_rectangle(left, y, left + size, y + size,
                                  fill=color, outline="")
            left += size + 3
        self.create_text(left + 2, y + size / 2, anchor="w", text=self.scale_high,
                         fill=pal["text_faint"], font=theme.font("caption"))

    def _draw_tooltip(self, width, height):
        pal = self.palette
        date, value = self.days[self._hover]
        shown = self.value_fmt(value) if value is not None else self.no_record
        text = f"{self.date_fmt(date)}   {shown}"

        est_w = max(96, len(text) * 6 + 18)
        # Just above the cursor; must not overlap the month label strip
        x = min(max(4, self._hover_xy[0] - est_w / 2), width - est_w - 4)
        y = self._hover_xy[1] - 24
        if y < self.HEAD_H:
            y = min(self._hover_xy[1] + 12, height - 20)
        self.create_rectangle(x, y, x + est_w, y + 18, fill=pal["surface_3"],
                              outline=pal["border"])
        self.create_text(x + est_w / 2, y + 9, text=text, fill=pal["text"],
                         font=theme.font("caption"))

    # -- interaction -------------------------------------------------------

    def _on_motion(self, event):
        found = None
        for x0, y0, x1, y1, index in self._cells:
            if x0 <= event.x <= x1 and y0 <= event.y <= y1:
                found = index
                break
        self._hover_xy = (event.x, event.y)
        if found != self._hover:
            self._hover = found
            self.redraw()
            if self.on_hover:
                self.on_hover(self.days[found] if found is not None else None)

    def _on_leave(self, _event):
        if self._hover is not None:
            self._hover = None
            self.redraw()
            if self.on_hover:
                self.on_hover(None)


class WeekdayProfile(tk.Canvas):
    """Average usage by day of week. The busiest day is highlighted."""

    PAD_BOTTOM = 18

    def __init__(self, parent, palette, height=130, **kw):
        super().__init__(parent, height=height, highlightthickness=0, bd=0,
                         bg=palette["surface"], **kw)
        self.palette = palette
        self.values = []
        self.labels = []
        self.value_fmt = str
        self._signature = None
        self.bind("<Configure>", lambda e: self.redraw())

    def set_palette(self, palette):
        self.palette = palette
        self.configure(bg=palette["surface"])
        self._signature = None
        self.redraw()

    def set_data(self, values, labels, value_fmt=None):
        signature = tuple(round(v / 60) for v in values)
        self.values = list(values)
        self.labels = list(labels)
        if value_fmt:
            self.value_fmt = value_fmt
        if signature == self._signature:
            return
        self._signature = signature
        self.redraw()

    def redraw(self):
        self.delete("all")
        width = self.winfo_width()
        height = self.winfo_height()
        if width < 60 or height < 40 or not self.values:
            return

        pal = self.palette
        top_value = max(self.values) or 1
        peak_index = self.values.index(max(self.values))
        plot_h = height - self.PAD_BOTTOM - 16
        slot = width / len(self.values)
        bar_w = min(slot - 10, 34)
        quiet = theme.mix(pal["accent"], pal["surface"], 0.6)

        for index, value in enumerate(self.values):
            cx = slot * index + slot / 2
            y1 = height - self.PAD_BOTTOM
            y0 = y1 - max(2, plot_h * (value / top_value))
            self.create_rectangle(cx - bar_w / 2, y0, cx + bar_w / 2, y1,
                                  fill=pal["accent"] if index == peak_index else quiet,
                                  outline="")
            self.create_text(cx, height - 8, text=self.labels[index],
                             fill=pal["text_dim"] if index == peak_index
                             else pal["text_faint"],
                             font=theme.font("caption"))
            if index == peak_index:
                self.create_text(cx, y0 - 9, text=self.value_fmt(value),
                                 fill=pal["text_dim"], font=theme.font("caption"))
