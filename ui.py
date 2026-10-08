import os
import tkinter as tk
from tkinter import filedialog
from collections import defaultdict
from datetime import datetime, timedelta

import theme
import charts
import chrome
import heatmap as heatmap_widgets
import insights
from i18n import t, months, weekdays, LANGUAGES
from appnames import display_name, is_system, category_of, CATEGORY_ORDER
from settings import load_settings, save_settings
import paths
from utils import (format_duration, format_percent, format_delta, format_axis,
                   format_date, parse_date, export_csv, group_digits)

PERIODS = [("today", "period_today"), ("week", "period_week"),
           ("month", "period_month"), ("all", "period_all")]

REFRESH_MS = 2000
WINDOW_W, WINDOW_H = 1400, 880
SIDEBAR_W = 364
DASH = "—"


class ScreenTimeUI:
    def __init__(self, tracker, settings=None):
        self.tracker = tracker
        self.settings = settings if settings is not None else load_settings()
        self.lang = self.settings.get("language", "en")
        self.pal = theme.palette(self.settings.get("theme", "dark"))
        self.period = self.settings.get("period", "week")

        self.root = tk.Tk()
        self.root.withdraw()
        try:
            # Replaces Tk's feather in the taskbar and Alt+Tab; default= covers
            # the settings window too
            self.root.iconbitmap(default=paths.resource(os.path.join("assets", "ScreenTime.ico")))
        except tk.TclError:
            pass
        self.is_visible = False
        self.tooltip = charts.Tooltip(self.root, self.pal)

        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *a: self._on_search())

        self.selected_app = None
        self._refresh_job = None
        # Widgets are rebuilt only when the set/order of apps changes
        self._rows_key = None
        self._rows = []
        self._cat_key = None
        self._cat_rows = []
        self._insight_key = None
        self._insight_rows = []
        self._previous_stats = {}

        # Our own window frame
        self._drag_origin = None
        self._drag_bounds = None
        self._maximized = False
        self._restore_bounds = None

        self.root.title(t(self.lang, "app_title"))
        self.root.minsize(1120, 720)
        self.root.protocol("WM_DELETE_WINDOW", self.hide)
        self.root.bind("<Escape>", lambda e: self._on_escape())
        self.root.bind("<Control-f>", lambda e: self.search_entry.focus_set())

        self._center()
        chrome.strip_titlebar(self.root)
        self.build()

    # -- scaffold ----------------------------------------------------------

    def _center(self):
        self.root.update_idletasks()
        width = min(WINDOW_W, self.root.winfo_screenwidth() - 80)
        height = min(WINDOW_H, self.root.winfo_screenheight() - 120)
        x = max(0, (self.root.winfo_screenwidth() - width) // 2)
        y = max(0, (self.root.winfo_screenheight() - height) // 3)
        self.root.geometry(f"{width}x{height}+{x}+{y}")

    def build(self):
        """Builds the window from scratch. Called again on theme/language change."""
        for child in self.root.winfo_children():
            if child is not getattr(self.tooltip, "window", None):
                child.destroy()

        self._rows_key = None
        self._rows = []
        self._cat_key = None
        self._cat_rows = []
        self._insight_key = None
        self._insight_rows = []
        self.tooltip.set_palette(self.pal)

        self.root.configure(bg=self.pal["bg"])
        self.root.title(t(self.lang, "app_title"))

        shell = tk.Frame(self.root, bg=self.pal["bg"])
        shell.pack(fill=tk.BOTH, expand=True, padx=theme.SPACE["lg"],
                   pady=(theme.SPACE["sm"], theme.SPACE["md"]))

        self._build_window_buttons(shell)
        self._build_header(shell)

        body = tk.Frame(shell, bg=self.pal["bg"])
        body.pack(fill=tk.BOTH, expand=True, pady=(theme.SPACE["md"], 0))

        sidebar = self._card(body, width=SIDEBAR_W)
        sidebar.pack(side=tk.LEFT, fill=tk.Y)
        sidebar.pack_propagate(False)
        self._build_sidebar(sidebar)

        self.content = tk.Frame(body, bg=self.pal["bg"])
        self.content.pack(side=tk.LEFT, fill=tk.BOTH, expand=True,
                          padx=(theme.SPACE["sm"], 0))

        self.overview = tk.Frame(self.content, bg=self.pal["bg"])
        self.detail = tk.Frame(self.content, bg=self.pal["bg"])
        self._build_overview(self.overview)
        self._build_detail(self.detail)
        self.overview.pack(fill=tk.BOTH, expand=True)

        self._build_footer(shell)
        self.refresh()

    def _card(self, parent, **kw):
        return tk.Frame(parent, bg=self.pal["surface"],
                        highlightbackground=self.pal["border"],
                        highlightthickness=1, bd=0, **kw)

    def _padded(self, card, pad=None):
        inner = tk.Frame(card, bg=self.pal["surface"])
        inner.pack(fill=tk.BOTH, expand=True,
                   padx=pad or theme.SPACE["md"], pady=pad or theme.SPACE["md"])
        return inner

    def _label(self, parent, text="", size="body", color="text", bg=None, **kw):
        return tk.Label(parent, text=text, font=theme.font(size),
                        fg=self.pal[color], bg=bg or self.pal["surface"],
                        anchor="w", **kw)

    def _section_title(self, parent, key, note=None):
        row = tk.Frame(parent, bg=self.pal["surface"])
        row.pack(fill=tk.X)
        self._label(row, t(self.lang, key), "label", "text").pack(side=tk.LEFT)
        if note:
            self._label(row, note, "caption", "text_faint").pack(side=tk.RIGHT)
        return row

    # -- title bar ---------------------------------------------------------

    def _build_window_buttons(self, parent):
        """Our own minimize / maximize / close buttons, top right."""
        bar = tk.Frame(parent, bg=self.pal["bg"])
        bar.pack(fill=tk.X)
        self._drag_targets(bar)

        for glyph, command, danger in (("✕", self.hide, True),
                                       ("□", self.toggle_maximize, False),
                                       ("−", self.minimize, False)):
            btn = tk.Label(bar, text=glyph, font=theme.font("caption"),
                           bg=self.pal["bg"], fg=self.pal["text_faint"],
                           padx=9, pady=3, cursor="hand2")
            btn.pack(side=tk.RIGHT)
            btn.bind("<Button-1>", lambda e, c=command: c())
            hover = self.pal["negative"] if danger else self.pal["text"]
            btn.bind("<Enter>", lambda e, b=btn, c=hover: b.configure(fg=c))
            btn.bind("<Leave>", lambda e, b=btn: b.configure(fg=self.pal["text_faint"]))

    def _build_header(self, parent):
        header = tk.Frame(parent, bg=self.pal["bg"])
        header.pack(fill=tk.X, pady=(theme.SPACE["xs"], 0))
        self._drag_targets(header)

        left = tk.Frame(header, bg=self.pal["bg"])
        left.pack(side=tk.LEFT)

        segment = tk.Frame(left, bg=self.pal["surface_2"],
                           highlightbackground=self.pal["border"],
                           highlightthickness=1)
        segment.pack(anchor="w")
        self.period_buttons = {}
        for key, label_key in PERIODS:
            btn = tk.Label(segment, text=t(self.lang, label_key),
                           font=theme.font("body"), padx=16, pady=6,
                           bg=self.pal["surface_2"], fg=self.pal["text_dim"],
                           cursor="hand2")
            btn.pack(side=tk.LEFT)
            btn.bind("<Button-1>", lambda e, k=key: self.set_period(k))
            self.period_buttons[key] = btn
        self._paint_period()

        right = tk.Frame(header, bg=self.pal["bg"])
        right.pack(side=tk.RIGHT)
        self._icon_button(right, "⚙", self.open_settings).pack(side=tk.RIGHT)
        self._icon_button(right, "↓", self.do_export).pack(
            side=tk.RIGHT, padx=(0, theme.SPACE["xs"]))

        search_wrap = tk.Frame(right, bg=self.pal["surface_2"],
                               highlightbackground=self.pal["border"],
                               highlightthickness=1)
        search_wrap.pack(side=tk.RIGHT, padx=theme.SPACE["md"])
        tk.Label(search_wrap, text="⌕", font=theme.font("label"),
                 fg=self.pal["text_faint"], bg=self.pal["surface_2"]).pack(
            side=tk.LEFT, padx=(8, 2))
        self.search_entry = tk.Entry(search_wrap, textvariable=self.search_var,
                                     font=theme.font("body"), width=20,
                                     bg=self.pal["surface_2"], fg=self.pal["text"],
                                     insertbackground=self.pal["text"],
                                     relief="flat", bd=0, highlightthickness=0)
        self.search_entry.pack(side=tk.LEFT, ipady=5, padx=(0, 8))
        self.search_hint = tk.Label(search_wrap, text=t(self.lang, "search"),
                                    font=theme.font("body"),
                                    bg=self.pal["surface_2"],
                                    fg=self.pal["text_faint"])
        self._sync_hint()

        # Keep the title dead center: placed with place(), the center does not
        # shift even when the left and right groups change width
        title = tk.Label(header, text=t(self.lang, "app_title"),
                         font=theme.font("display", "bold"),
                         fg=self.pal["text"], bg=self.pal["bg"])
        title.place(relx=0.5, rely=0.5, anchor="center")
        self._drag_targets(title)

    def _icon_button(self, parent, glyph, command):
        btn = tk.Label(parent, text=glyph, font=theme.font("title"),
                       bg=self.pal["surface_2"], fg=self.pal["text_dim"],
                       width=3, pady=4, cursor="hand2",
                       highlightbackground=self.pal["border"], highlightthickness=1)
        btn.bind("<Button-1>", lambda e: command())
        btn.bind("<Enter>", lambda e: btn.configure(fg=self.pal["text"]))
        btn.bind("<Leave>", lambda e: btn.configure(fg=self.pal["text_dim"]))
        return btn

    # -- window frame ------------------------------------------------------

    def _drag_targets(self, *widgets):
        """With no title bar, the window is dragged from these areas."""
        for widget in widgets:
            widget.bind("<Button-1>", self._start_drag, add="+")
            widget.bind("<B1-Motion>", self._do_drag, add="+")
            widget.bind("<ButtonRelease-1>", self._end_drag, add="+")
            widget.bind("<Double-Button-1>", lambda e: self.toggle_maximize(), add="+")

    def _start_drag(self, event):
        if self._maximized:
            return
        self._drag_origin = (event.x_root, event.y_root)
        self._drag_bounds = chrome.bounds(self.root)
        self.tooltip.hide()
        # Hold data refresh while dragging; running it mid-drag stutters
        self._cancel_refresh()

    def _do_drag(self, event):
        if self._maximized or not self._drag_origin:
            return
        origin_x, origin_y = self._drag_origin
        left, top, _width, _height = self._drag_bounds
        chrome.move_to(self.root,
                       left + (event.x_root - origin_x),
                       top + (event.y_root - origin_y))

    def _end_drag(self, _event):
        if self._drag_origin is None:
            return
        self._drag_origin = None
        self._schedule()

    def minimize(self):
        chrome.minimize(self.root)

    def toggle_maximize(self):
        if self._maximized:
            if self._restore_bounds:
                chrome.set_bounds(self.root, *self._restore_bounds)
            self._maximized = False
            return

        self.root.update_idletasks()
        self._restore_bounds = chrome.bounds(self.root)
        self._maximized = chrome.set_bounds(self.root, *chrome.work_area(self.root))

    def _sync_hint(self):
        hint = getattr(self, "search_hint", None)
        if hint is None:
            return
        try:
            if self.search_var.get():
                hint.place_forget()
            else:
                hint.place(in_=self.search_entry, x=1, rely=0.5, anchor="w")
        except tk.TclError:
            pass

    def _query(self):
        return self.search_var.get().strip().lower()

    def _on_search(self):
        self._sync_hint()
        self.refresh()

    def _on_escape(self):
        if self.selected_app:
            self.show_overview()
        else:
            self.hide()

    def _paint_period(self):
        for key, btn in self.period_buttons.items():
            active = key == self.period
            btn.configure(bg=self.pal["accent"] if active else self.pal["surface_2"],
                          fg="#FFFFFF" if active else self.pal["text_dim"])

    def set_period(self, key):
        self.period = key
        self.settings["period"] = key
        save_settings(self.settings)
        self._paint_period()
        self.refresh()

    # -- left panel --------------------------------------------------------

    def _build_sidebar(self, card):
        inner = tk.Frame(card, bg=self.pal["surface"])
        inner.pack(fill=tk.BOTH, expand=True, padx=theme.SPACE["md"],
                   pady=theme.SPACE["md"])

        head = tk.Frame(inner, bg=self.pal["surface"])
        head.pack(fill=tk.X)
        self._label(head, t(self.lang, "sidebar_title"), "label", "text").pack(side=tk.LEFT)
        self.sidebar_count = self._label(head, "", "caption", "text_faint")
        self.sidebar_count.pack(side=tk.RIGHT)

        self.all_apps_btn = tk.Label(inner, text=t(self.lang, "all_apps"),
                                     font=theme.font("small"), anchor="w",
                                     bg=self.pal["surface"], fg=self.pal["text_dim"],
                                     cursor="hand2", pady=6)
        self.all_apps_btn.pack(fill=tk.X, pady=(theme.SPACE["sm"], 2))
        self.all_apps_btn.bind("<Button-1>", lambda e: self.show_overview())

        tk.Frame(inner, bg=self.pal["border"], height=1).pack(
            fill=tk.X, pady=(0, theme.SPACE["sm"]))

        self.rows_host = self._scrollable(inner)

    def _scrollable(self, parent):
        wrap = tk.Frame(parent, bg=self.pal["surface"])
        wrap.pack(fill=tk.BOTH, expand=True)

        canvas = tk.Canvas(wrap, bg=self.pal["surface"], highlightthickness=0, bd=0)
        bar = charts.SlimScrollbar(wrap, self.pal, command=canvas.yview, width=6)
        inner = tk.Frame(canvas, bg=self.pal["surface"])

        window = canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=bar.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        bar.pack(side=tk.RIGHT, fill=tk.Y, padx=(6, 0))

        inner.bind("<Configure>",
                   lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>",
                    lambda e: canvas.itemconfigure(window, width=e.width))

        def on_wheel(event):
            canvas.yview_scroll(-1 * (event.delta // 120), "units")

        canvas.bind("<Enter>", lambda e: canvas.bind_all("<MouseWheel>", on_wheel))
        canvas.bind("<Leave>", lambda e: canvas.unbind_all("<MouseWheel>"))
        return inner

    # -- right content -----------------------------------------------------

    def _build_overview(self, parent):
        self._build_stats(parent)

        heat_card = self._card(parent)
        heat_card.pack(fill=tk.X, pady=(theme.SPACE["sm"], 0))
        heat_inner = self._padded(heat_card)
        self._section_title(heat_inner, "heatmap_title", t(self.lang, "heatmap_note"))
        self.heatmap = heatmap_widgets.Heatmap(heat_inner, self.pal, height=200)
        self.heatmap.set_labels(t(self.lang, "heatmap_less"),
                                t(self.lang, "heatmap_more"),
                                t(self.lang, "no_record"))
        self.heatmap.pack(fill=tk.X, pady=(theme.SPACE["sm"], 0))

        row = tk.Frame(parent, bg=self.pal["bg"])
        row.pack(fill=tk.X, pady=(theme.SPACE["sm"], 0))

        cat_card = self._card(row)
        cat_card.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        cat_inner = self._padded(cat_card)
        self._section_title(cat_inner, "categories")
        self.category_bar = charts.CompositionBar(cat_inner, self.pal, height=9)
        self.category_bar.pack(fill=tk.X, pady=(theme.SPACE["sm"], theme.SPACE["sm"]))
        self.category_host = tk.Frame(cat_inner, bg=self.pal["surface"])
        self.category_host.pack(fill=tk.BOTH, expand=True)

        day_card = self._card(row)
        day_card.pack(side=tk.LEFT, fill=tk.BOTH, expand=True,
                      padx=(theme.SPACE["sm"], 0))
        day_inner = self._padded(day_card)
        self._section_title(day_inner, "weekday_title")
        self.weekday = heatmap_widgets.WeekdayProfile(day_inner, self.pal, height=112)
        self.weekday.pack(fill=tk.BOTH, expand=True, pady=(theme.SPACE["sm"], 0))

        ins_card = self._card(parent)
        ins_card.pack(fill=tk.BOTH, expand=True, pady=(theme.SPACE["sm"], 0))
        ins_inner = self._padded(ins_card)
        self._section_title(ins_inner, "insights_title")
        self.insight_host = tk.Frame(ins_inner, bg=self.pal["surface"])
        self.insight_host.pack(fill=tk.X, pady=(theme.SPACE["sm"], 0))

    def _build_stats(self, parent):
        row = tk.Frame(parent, bg=self.pal["bg"])
        row.pack(fill=tk.X)

        self.stat_values = {}
        self.stat_notes = {}
        for index, key in enumerate(["stat_total", "stat_average",
                                     "stat_top", "stat_apps"]):
            card = self._card(row)
            card.pack(side=tk.LEFT, fill=tk.BOTH, expand=True,
                      padx=(0 if index == 0 else theme.SPACE["sm"], 0))
            inner = self._padded(card)
            self._label(inner, t(self.lang, key).upper(), "caption",
                        "text_faint").pack(anchor="w")
            value = self._label(inner, DASH, "stat", "text")
            value.pack(anchor="w", pady=(6, 0))
            note = self._label(inner, "", "small", "text_dim")
            note.pack(anchor="w", pady=(2, 0))
            self.stat_values[key] = value
            self.stat_notes[key] = note

    def _build_detail(self, parent):
        card = self._card(parent)
        card.pack(fill=tk.BOTH, expand=True)
        inner = self._padded(card, theme.SPACE["lg"])

        back = tk.Label(inner, text="←  " + t(self.lang, "back"),
                        font=theme.font("body"), bg=self.pal["surface"],
                        fg=self.pal["text_dim"], cursor="hand2")
        back.pack(anchor="w")
        back.bind("<Button-1>", lambda e: self.show_overview())

        self.detail_title = self._label(inner, "", "stat", "text")
        self.detail_title.pack(anchor="w", pady=(theme.SPACE["md"], 0))
        self.detail_meta = self._label(inner, "", "body", "text_dim")
        self.detail_meta.pack(anchor="w", pady=(4, 0))

        self.detail_heat = heatmap_widgets.Heatmap(inner, self.pal, height=200)
        self.detail_heat.set_labels(t(self.lang, "heatmap_less"),
                                    t(self.lang, "heatmap_more"),
                                    t(self.lang, "no_record"))
        self.detail_heat.pack(fill=tk.X, pady=(theme.SPACE["lg"], 0))

        self.detail_chart = charts.BarChart(inner, self.pal, height=170)
        self.detail_chart.pack(fill=tk.BOTH, expand=True,
                               pady=(theme.SPACE["md"], theme.SPACE["sm"]))

        self.detail_facts = tk.Frame(inner, bg=self.pal["surface"])
        self.detail_facts.pack(fill=tk.X)

    def _build_footer(self, parent):
        self.footer = tk.Label(parent, text="", font=theme.font("caption"),
                               fg=self.pal["text_faint"], bg=self.pal["bg"],
                               anchor="w")
        self.footer.pack(fill=tk.X, pady=(theme.SPACE["sm"], 0))

    # -- view switching ----------------------------------------------------

    def show_overview(self):
        self.selected_app = None
        self.detail.pack_forget()
        self.overview.pack(fill=tk.BOTH, expand=True)
        self._paint_selection()
        self.refresh()

    def show_detail(self, app):
        self.selected_app = app
        self.overview.pack_forget()
        self.detail.pack(fill=tk.BOTH, expand=True)
        self._paint_selection()
        self.refresh()

    def _paint_selection(self):
        active = self.selected_app is None
        self.all_apps_btn.configure(
            bg=self.pal["surface_2"] if active else self.pal["surface"],
            fg=self.pal["text"] if active else self.pal["text_dim"])
        for row in self._rows:
            if row.get("placeholder"):
                continue
            self._row_hover(row, row["app"] == self.selected_app)

    # -- data ---------------------------------------------------------------

    def _visible_stats(self, stats):
        if not self.settings.get("hide_system", True):
            return dict(stats)
        return {k: v for k, v in stats.items() if not is_system(k)}

    def _history_days(self, app=None):
        """Every day from the first record to today: (date, seconds) or (date, None)."""
        tracked = self.tracker.get_tracked_dates()
        if not tracked:
            return []
        first = self.tracker.parse(tracked[0])
        if first is None:
            return []

        days = []
        current = first.date()
        today = datetime.now().date()
        while current <= today:
            date_str = current.strftime("%d%m%y")
            if self.tracker.has_record(date_str):
                totals = self.tracker.day_totals(date_str)
                if app is not None:
                    days.append((current, totals.get(app, 0)))
                else:
                    days.append((current, sum(self._visible_stats(totals).values())))
            else:
                days.append((current, None))
            current += timedelta(days=1)
        return days

    def _weekday_averages(self, dates):
        buckets = [[] for _ in range(7)]
        for date_str in dates:
            if not self.tracker.has_record(date_str):
                continue
            parsed = self.tracker.parse(date_str)
            if parsed is None:
                continue
            totals = self._visible_stats(self.tracker.day_totals(date_str))
            buckets[parsed.weekday()].append(sum(totals.values()))
        return [(sum(values) / len(values)) if values else 0 for values in buckets]

    def _period_bounds(self, dates):
        if not dates or self.period == "all":
            return None
        first, last = self.tracker.parse(dates[0]), self.tracker.parse(dates[-1])
        if first is None or last is None:
            return None
        return (first.date(), last.date())

    # -- drawing ------------------------------------------------------------

    def refresh(self):
        if not self.root or not self.is_visible:
            return
        try:
            if self.selected_app:
                self._render_detail()
            else:
                self._render_overview()
        except tk.TclError:
            return
        self._schedule()

    def _cancel_refresh(self):
        if self._refresh_job is not None:
            try:
                self.root.after_cancel(self._refresh_job)
            except Exception:
                pass
            self._refresh_job = None

    def _schedule(self):
        self._cancel_refresh()
        if self.is_visible:
            self._refresh_job = self.root.after(REFRESH_MS, self.refresh)

    def _render_overview(self):
        dates = self.tracker.period_dates(self.period)
        stats = self._visible_stats(self.tracker.aggregate(dates))
        total = sum(stats.values())
        ranked = sorted(stats.items(), key=lambda x: x[1], reverse=True)

        previous_dates = self.tracker.previous_period_dates(self.period)
        self._previous_stats = self._visible_stats(
            self.tracker.aggregate(previous_dates)) if previous_dates else {}

        self._render_stat_cards(dates, stats, total, ranked)
        self._render_sidebar(ranked, total)
        self._render_heatmap(self.heatmap, None, dates)
        self._render_categories(stats, total)
        self._render_weekday(dates)
        self._render_insights(dates, stats)
        self._render_footer()

    # -- summary cards -----------------------------------------------------

    def _render_stat_cards(self, dates, stats, total, ranked):
        recorded = [d for d in dates if self.tracker.has_record(d)]
        active = [d for d in recorded
                  if sum(self._visible_stats(self.tracker.day_totals(d)).values()) > 0]
        average = total / len(active) if active else 0

        self._set_text(self.stat_values["stat_total"],
                       format_duration(total) if total else DASH)
        self._set_text(self.stat_values["stat_average"],
                       format_duration(average) if average else DASH)

        if ranked:
            top_app, top_seconds = ranked[0]
            self._set_text(self.stat_values["stat_top"], display_name(top_app))
            share = (top_seconds / total * 100) if total else 0
            self._set_text(self.stat_notes["stat_top"],
                           f"{format_duration(top_seconds)} · "
                           f"{format_percent(share, self.lang)}")
        else:
            self._set_text(self.stat_values["stat_top"], DASH)
            self._set_text(self.stat_notes["stat_top"], "")

        self._set_text(self.stat_values["stat_apps"], str(len(stats)) if stats else DASH)

        # Days without a record stay out of the average, but are shown
        missing = len(dates) - len(recorded)
        gap_key = "gap_days_one" if missing == 1 else "gap_days"
        self._set_text(self.stat_notes["stat_apps"],
                       t(self.lang, gap_key, n=missing) if missing else "")
        self._set_text(self.stat_notes["stat_average"],
                       t(self.lang, "active_days", n=len(active), total=len(dates))
                       if len(dates) > 1 else "")

        previous_total = sum(self._previous_stats.values())
        if previous_total and total:
            change = (total - previous_total) / previous_total * 100
            key = "vs_yesterday" if self.period == "today" else "vs_previous"
            self._set_text(self.stat_notes["stat_total"],
                           f"{format_delta(change, self.lang)}  {t(self.lang, key)}")
            self.stat_notes["stat_total"].configure(
                fg=self.pal["positive"] if change < 0 else self.pal["negative"])
        else:
            self._set_text(self.stat_notes["stat_total"], "")

    # -- left panel list ---------------------------------------------------

    def _render_sidebar(self, ranked, total):
        query = self._query()
        filtered = [(app, seconds) for app, seconds in ranked
                    if not query or query in display_name(app).lower()
                    or query in app.lower()]

        self._set_text(self.sidebar_count, str(len(filtered)))

        key = (query, tuple(app for app, _s in filtered))
        if key != self._rows_key:
            self._rows_key = key
            self._build_rows(filtered, query)
            self._paint_selection()

        peak = filtered[0][1] if filtered else 1
        for (app, seconds), row in zip(filtered, self._rows):
            self._update_row(row, seconds, total, peak)

    def _build_rows(self, filtered, query):
        for row in self._rows:
            row["frame"].destroy()
        self._rows = []

        if not filtered:
            message = t(self.lang, "no_match", q=query) if query else t(self.lang, "no_data")
            empty = tk.Frame(self.rows_host, bg=self.pal["surface"])
            empty.pack(fill=tk.X, pady=theme.SPACE["xl"])
            tk.Label(empty, text=message, font=theme.font("small"),
                     bg=self.pal["surface"], fg=self.pal["text_dim"],
                     wraplength=280).pack()
            self._rows = [{"frame": empty, "placeholder": True}]
            return

        for index, (app, _seconds) in enumerate(filtered):
            self._rows.append(self._build_row(index + 1, app))

    def _build_row(self, rank, app):
        row = tk.Frame(self.rows_host, bg=self.pal["surface"], cursor="hand2")
        row.pack(fill=tk.X, pady=1)

        top = tk.Frame(row, bg=self.pal["surface"])
        top.pack(fill=tk.X, padx=8, pady=(5, 3))
        name = tk.Label(top, text=display_name(app), font=theme.font("body"),
                        bg=self.pal["surface"], fg=self.pal["text"], anchor="w")
        name.pack(side=tk.LEFT)
        time_label = tk.Label(top, text="", font=theme.font("body"),
                              bg=self.pal["surface"], fg=self.pal["text_dim"],
                              anchor="e")
        time_label.pack(side=tk.RIGHT)
        share_label = tk.Label(top, text="", font=theme.font("caption"),
                               bg=self.pal["surface"], fg=self.pal["text_faint"],
                               anchor="e")
        share_label.pack(side=tk.RIGHT, padx=(0, theme.SPACE["sm"]))

        bottom = tk.Frame(row, bg=self.pal["surface"])
        bottom.pack(fill=tk.X, padx=8, pady=(0, 7))

        # The right-hand label must be packed FIRST: if the expanding gauge is
        # packed first it takes all remaining space and leaves none for the label
        delta_label = tk.Label(bottom, text="", font=theme.font("caption"),
                               bg=self.pal["surface"], fg=self.pal["text_faint"],
                               anchor="e")
        delta_label.pack(side=tk.RIGHT)

        gauge = tk.Canvas(bottom, height=4, bg=self.pal["surface"],
                          highlightthickness=0, bd=0)
        gauge.pack(side=tk.LEFT, fill=tk.X, expand=True,
                   padx=(0, theme.SPACE["sm"]))
        gauge._ratio = 0.0

        def draw_gauge(_e=None):
            gauge.delete("all")
            width = gauge.winfo_width()
            if width < 4:
                return
            gauge.create_rectangle(0, 0, width, 4, fill=self.pal["surface_2"],
                                   outline="")
            gauge.create_rectangle(0, 0, max(2, width * gauge._ratio), 4,
                                   fill=self.pal["accent"], outline="")

        gauge.bind("<Configure>", draw_gauge)
        gauge.bind("<<Redraw>>", draw_gauge)

        record = {"frame": row, "app": app, "gauge": gauge, "time": time_label,
                  "share": share_label, "delta": delta_label, "seconds": 0,
                  "members": [row, top, bottom, name, time_label, gauge,
                              share_label, delta_label]}

        for widget in record["members"]:
            widget.bind("<Button-1>", lambda e, a=app: self.show_detail(a))
            widget.bind("<Enter>", lambda e, r=record: self._row_hover(r, True))
            widget.bind("<Leave>", lambda e, r=record: self._row_hover(r, False))

        # Duration is written in days; show minutes in the tooltip
        self.tooltip.attach(row, lambda r=record: self._row_tooltip(r))
        self.tooltip.attach(name, lambda r=record: self._row_tooltip(r))
        self.tooltip.attach(time_label, lambda r=record: self._row_tooltip(r))
        return record

    def _row_tooltip(self, record):
        seconds = record["seconds"]
        minutes = group_digits(int(seconds // 60), self.lang)
        return (f"{display_name(record['app'])}\n"
                f"{format_duration(seconds, precise=True)}\n"
                f"{t(self.lang, 'tooltip_minutes', n=minutes)}")

    def _update_row(self, record, seconds, total, peak):
        if record.get("placeholder"):
            return
        record["seconds"] = seconds
        self._set_text(record["time"], format_duration(seconds))
        share = (seconds / total * 100) if total else 0
        self._set_text(record["share"], format_percent(share, self.lang))

        self._update_delta(record, seconds)

        # The ratio stays linear: if one app dwarfs the others, the bar should
        # show that. The exact value is already printed beside it as a percentage.
        #
        # Always store the ratio: on first draw the canvas is not laid out yet,
        # its width is 1 and nothing can be drawn. Once it gets its real width,
        # <Configure> fires and draws with the stored ratio.
        gauge = record["gauge"]
        ratio = (seconds / peak) if peak else 0
        if abs(ratio - getattr(gauge, "_ratio", -1)) > 0.004:
            gauge._ratio = ratio
            gauge.event_generate("<<Redraw>>")

    def _update_delta(self, record, seconds):
        """Change against the previous period.

        When the previous value is a few seconds, the ratio comes out absurdly
        large (like +809900%). In that case a "new" badge is shown instead,
        and large increases are capped at a readable ceiling.
        """
        label = record["delta"]
        previous = self._previous_stats.get(record["app"], 0)

        if not self._previous_stats:
            self._set_text(label, "")
            return

        if previous < 60:
            if seconds >= 60:
                self._set_text(label, t(self.lang, "badge_new"))
                label.configure(fg=self.pal["accent"])
            else:
                self._set_text(label, "")
            return

        change = (seconds - previous) / previous * 100
        if change > 999:
            text = "› " + format_delta(999, self.lang)
        elif abs(change) < 1:
            text = ""
        else:
            text = format_delta(change, self.lang)
        self._set_text(label, text)
        label.configure(fg=self.pal["positive"] if change < 0 else self.pal["negative"])

    def _row_hover(self, record, entering):
        selected = record["app"] == self.selected_app
        color = self.pal["surface_2"] if (entering or selected) else self.pal["surface"]
        for widget in record["members"]:
            try:
                widget.configure(bg=color)
            except tk.TclError:
                pass

    # -- heatmap, categories, day-of-week profile --------------------------

    def _render_heatmap(self, widget, app, dates):
        days = self._history_days(app)
        widget.set_data(days, months(self.lang), weekdays(self.lang),
                        value_fmt=format_duration,
                        date_fmt=lambda d: f"{d.day} {months(self.lang)[d.month - 1]}",
                        highlight=self._period_bounds(dates))

    def _render_categories(self, stats, total):
        totals = defaultdict(int)
        for app, seconds in stats.items():
            totals[category_of(app)] += seconds

        colors = self.pal["series"]
        ordered = [(name, totals[name]) for name in CATEGORY_ORDER if totals.get(name)]
        ordered.sort(key=lambda x: -x[1])

        segments = [(t(self.lang, f"cat_{name}"), seconds,
                     colors[index % len(colors)])
                    for index, (name, seconds) in enumerate(ordered)]
        self.category_bar.set_data(segments)

        key = tuple((name, color) for (name, _s, color) in segments)
        if key != self._cat_key:
            self._cat_key = key
            self._build_category_rows(segments)

        for (label, seconds, _color), widgets in zip(segments, self._cat_rows):
            share = (seconds / total * 100) if total else 0
            self._set_text(widgets["time"], format_duration(seconds))
            self._set_text(widgets["share"], format_percent(share, self.lang))

    def _build_category_rows(self, segments):
        for widgets in self._cat_rows:
            widgets["frame"].destroy()
        self._cat_rows = []

        for label, _seconds, color in segments:
            row = tk.Frame(self.category_host, bg=self.pal["surface"])
            row.pack(fill=tk.X, pady=2)
            dot = tk.Canvas(row, width=8, height=8, bg=self.pal["surface"],
                            highlightthickness=0)
            dot.create_rectangle(0, 1, 8, 8, fill=color, outline="")
            dot.pack(side=tk.LEFT, pady=(3, 0))
            tk.Label(row, text="  " + label, font=theme.font("small"),
                     bg=self.pal["surface"], fg=self.pal["text_dim"],
                     anchor="w").pack(side=tk.LEFT)
            share = tk.Label(row, text="", font=theme.font("caption"),
                             bg=self.pal["surface"], fg=self.pal["text_faint"],
                             width=7, anchor="e")
            share.pack(side=tk.RIGHT)
            time_label = tk.Label(row, text="", font=theme.font("small"),
                                  bg=self.pal["surface"], fg=self.pal["text_dim"],
                                  anchor="e")
            time_label.pack(side=tk.RIGHT, padx=(0, theme.SPACE["sm"]))
            self._cat_rows.append({"frame": row, "time": time_label, "share": share})

    def _render_weekday(self, dates):
        self.weekday.set_data(self._weekday_averages(dates), weekdays(self.lang),
                              value_fmt=format_axis)

    def _render_insights(self, dates, stats):
        found = insights.build(self.tracker, self.period, self.lang,
                               self.settings.get("hide_system", True), dates, stats)
        key = tuple(text for _tone, text in found)
        if key == self._insight_key:
            return
        self._insight_key = key

        for widgets in self._insight_rows:
            widgets.destroy()
        self._insight_rows = []

        tones = {"good": self.pal["positive"], "warn": self.pal["negative"],
                 "info": self.pal["accent"], "flat": self.pal["text_faint"]}
        for tone, text in found:
            row = tk.Frame(self.insight_host, bg=self.pal["surface"])
            row.pack(fill=tk.X, pady=3)
            dot = tk.Canvas(row, width=6, height=6, bg=self.pal["surface"],
                            highlightthickness=0)
            dot.create_oval(0, 0, 6, 6, fill=tones.get(tone, self.pal["accent"]),
                            outline="")
            dot.pack(side=tk.LEFT, pady=(4, 0))
            tk.Label(row, text="  " + text, font=theme.font("small"),
                     bg=self.pal["surface"], fg=self.pal["text_dim"],
                     anchor="w", justify="left", wraplength=880).pack(side=tk.LEFT)
            self._insight_rows.append(row)

    # -- detail -------------------------------------------------------------

    def _render_detail(self):
        app = self.selected_app
        dates = self.tracker.period_dates(self.period)
        series = self.tracker.daily_series(dates, app=app)
        total = sum(value for _d, value in series)
        period_total = sum(self._visible_stats(self.tracker.aggregate(dates)).values())
        active = [(d, v) for d, v in series if v > 0]
        month_names = months(self.lang)

        self._set_text(self.detail_title, display_name(app))
        share = (total / period_total * 100) if period_total else 0
        minutes = group_digits(int(total // 60), self.lang)
        self._set_text(self.detail_meta,
                       f"{format_duration(total, precise=True)}   ·   "
                       f"{t(self.lang, 'detail_share', pct=format_percent(share, self.lang))}"
                       f"   ·   {t(self.lang, 'tooltip_minutes', n=minutes)}")

        self._render_heatmap(self.detail_heat, app, dates)

        points = [(d, v, format_date(d, month_names)) for d, v in series]
        self.detail_chart.set_data(points, value_fmt=format_duration,
                                   axis_fmt=format_axis)

        facts = []
        if active:
            facts.append(t(self.lang, "detail_average",
                           time=format_duration(total / len(active))))
            facts.append(t(self.lang, "detail_active", n=len(active), total=len(dates)))
            peak_date, peak_value = max(active, key=lambda x: x[1])
            facts.append(t(self.lang, "detail_peak",
                           date=format_date(peak_date, month_names),
                           time=format_duration(peak_value)))

        if len(self.detail_facts.winfo_children()) != len(facts):
            for child in self.detail_facts.winfo_children():
                child.destroy()
            for index, text in enumerate(facts):
                tk.Label(self.detail_facts, text=text, font=theme.font("small"),
                         bg=self.pal["surface"], fg=self.pal["text_dim"]).pack(
                    side=tk.LEFT, padx=(0 if index == 0 else theme.SPACE["lg"], 0))
        else:
            for child, text in zip(self.detail_facts.winfo_children(), facts):
                self._set_text(child, text)

    def _render_footer(self):
        tracked = self.tracker.get_tracked_dates()
        if not tracked:
            self._set_text(self.footer, "")
            return
        label = format_date(tracked[0], months(self.lang), short=False)
        self._set_text(self.footer,
                       t(self.lang, "footer", date=label, days=len(tracked)))

    @staticmethod
    def _set_text(widget, value):
        try:
            if widget.cget("text") != value:
                widget.configure(text=value)
        except tk.TclError:
            pass

    # -- settings ----------------------------------------------------------

    def open_settings(self):
        win = tk.Toplevel(self.root)
        win.title(t(self.lang, "settings"))
        win.configure(bg=self.pal["bg"])
        win.resizable(False, False)
        win.transient(self.root)

        body = tk.Frame(win, bg=self.pal["bg"])
        body.pack(fill=tk.BOTH, expand=True, padx=theme.SPACE["lg"],
                  pady=theme.SPACE["lg"])

        def section(title_key):
            tk.Label(body, text=t(self.lang, title_key).upper(),
                     font=theme.font("caption"), bg=self.pal["bg"],
                     fg=self.pal["text_faint"], anchor="w").pack(
                fill=tk.X, pady=(theme.SPACE["md"], theme.SPACE["xs"]))

        def choice_row(options, current, on_pick):
            wrap = tk.Frame(body, bg=self.pal["surface_2"],
                            highlightbackground=self.pal["border"],
                            highlightthickness=1)
            wrap.pack(anchor="w")
            buttons = {}
            for value, label in options:
                btn = tk.Label(wrap, text=label, font=theme.font("body"),
                               padx=14, pady=5, cursor="hand2")
                btn.pack(side=tk.LEFT)
                buttons[value] = btn

            def paint():
                for value, btn in buttons.items():
                    active = value == current[0]
                    btn.configure(bg=self.pal["accent"] if active else self.pal["surface_2"],
                                  fg="#FFFFFF" if active else self.pal["text_dim"])

            for value, btn in buttons.items():
                def pick(_e, v=value):
                    current[0] = v
                    paint()
                    on_pick(v)
                btn.bind("<Button-1>", pick)
            paint()

        section("theme")
        choice_row([("dark", t(self.lang, "theme_dark")),
                    ("light", t(self.lang, "theme_light"))],
                   [self.settings.get("theme", "dark")],
                   lambda v: self._apply_theme(v, win))

        section("language")
        choice_row(LANGUAGES, [self.lang], lambda v: self._apply_language(v, win))

        section("idle")
        choice_row([(True, t(self.lang, "idle_on")), (False, t(self.lang, "idle_off"))],
                   [bool(self.settings.get("idle_enabled", True))],
                   lambda v: self._apply_setting("idle_enabled", v))
        tk.Label(body, text=t(self.lang, "idle_hint",
                              n=self.settings.get("idle_timeout", 60)),
                 font=theme.font("small"), bg=self.pal["bg"],
                 fg=self.pal["text_faint"], anchor="w",
                 wraplength=380, justify="left").pack(fill=tk.X, pady=(6, 0))

        timeout_row = tk.Frame(body, bg=self.pal["bg"])
        timeout_row.pack(anchor="w", pady=(theme.SPACE["sm"], 0))
        tk.Label(timeout_row, text=t(self.lang, "idle_timeout"),
                 font=theme.font("small"), bg=self.pal["bg"],
                 fg=self.pal["text_dim"]).pack(side=tk.LEFT,
                                               padx=(0, theme.SPACE["sm"]))
        host = tk.Frame(timeout_row, bg=self.pal["bg"])
        host.pack(side=tk.LEFT)
        current_timeout = int(self.settings.get("idle_timeout", 60))
        buttons = {}
        for value in (30, 60, 120, 300):
            btn = tk.Label(host, text=t(self.lang, "seconds", n=value),
                           font=theme.font("small"), padx=10, pady=3, cursor="hand2",
                           highlightbackground=self.pal["border"], highlightthickness=1)
            btn.pack(side=tk.LEFT, padx=(0, 4))
            buttons[value] = btn

        def paint_timeout(chosen):
            for value, btn in buttons.items():
                active = value == chosen
                btn.configure(bg=self.pal["accent"] if active else self.pal["surface_2"],
                              fg="#FFFFFF" if active else self.pal["text_dim"])

        for value, btn in buttons.items():
            btn.bind("<Button-1>", lambda e, v=value: (
                self._apply_setting("idle_timeout", v), paint_timeout(v)))
        paint_timeout(current_timeout)

        section("hide_system")
        choice_row([(True, t(self.lang, "idle_on")), (False, t(self.lang, "idle_off"))],
                   [bool(self.settings.get("hide_system", True))],
                   lambda v: self._apply_setting("hide_system", v, redraw=True))
        tk.Label(body, text=t(self.lang, "hide_system_hint"),
                 font=theme.font("small"), bg=self.pal["bg"],
                 fg=self.pal["text_faint"], anchor="w",
                 wraplength=380, justify="left").pack(fill=tk.X, pady=(6, 0))

        tk.Label(body, text=f"{t(self.lang, 'data_folder')}: "
                            f"{os.path.abspath(self.tracker.data_dir)}",
                 font=theme.font("caption"), bg=self.pal["bg"],
                 fg=self.pal["text_faint"], anchor="w",
                 wraplength=380, justify="left").pack(fill=tk.X,
                                                      pady=(theme.SPACE["lg"], 0))

        close = tk.Label(body, text=t(self.lang, "close"), font=theme.font("body"),
                         bg=self.pal["surface_2"], fg=self.pal["text"],
                         padx=18, pady=6, cursor="hand2",
                         highlightbackground=self.pal["border"], highlightthickness=1)
        close.pack(anchor="e", pady=(theme.SPACE["lg"], 0))
        close.bind("<Button-1>", lambda e: win.destroy())

        win.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - win.winfo_width()) // 2
        win.geometry(f"+{max(0, x)}+{max(0, self.root.winfo_y() + 120)}")
        self.settings_window = win

    def _apply_setting(self, key, value, redraw=False):
        self.settings[key] = value
        save_settings(self.settings)
        if redraw:
            self._rows_key = None
            self._cat_key = None
            self.refresh()

    def _apply_theme(self, name, window=None):
        self.settings["theme"] = name
        save_settings(self.settings)
        self.pal = theme.palette(name)
        if window is not None:
            window.destroy()
        self.build()

    def _apply_language(self, code, window=None):
        self.settings["language"] = code
        save_settings(self.settings)
        self.lang = code
        if window is not None:
            window.destroy()
        self.build()

    # -- export ------------------------------------------------------------

    def do_export(self):
        dates = self.tracker.period_dates(self.period)
        stamp = datetime.now().strftime("%Y%m%d")
        path = filedialog.asksaveasfilename(
            parent=self.root, title=t(self.lang, "export"),
            defaultextension=".csv",
            initialfile=f"screentime_{self.period}_{stamp}.csv",
            filetypes=[("CSV", "*.csv")])
        if not path:
            return
        try:
            export_csv(path, self.tracker, dates,
                       hide_system=self.settings.get("hide_system", True))
            self._set_text(self.footer, t(self.lang, "export_done", path=path))
        except Exception as error:
            self._set_text(self.footer, str(error))

    # -- window state ------------------------------------------------------

    def show(self):
        if self.is_visible:
            return
        self.is_visible = True
        self.root.deiconify()
        chrome.strip_titlebar(self.root)
        self.root.lift()
        self.root.attributes("-topmost", True)
        self.root.attributes("-topmost", False)
        self.refresh()

    def hide(self):
        self.is_visible = False
        self.tooltip.hide()
        self._cancel_refresh()
        self.root.withdraw()

    def run_step(self):
        if self.root:
            try:
                self.root.update()
            except tk.TclError:
                pass
