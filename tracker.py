import time
import threading
import win32gui
import win32process
import win32api
import psutil
import json
import os
from collections import defaultdict
from datetime import datetime, timedelta

DATE_FORMAT = "%d%m%y"

# Shell processes not counted as usage: time on the lock screen is not usage
NEVER_TRACKED = {"lockapp", "logonui"}


class ScreenTimeTracker:
    def __init__(self, data_dir="data", settings=None):
        self.data_dir = data_dir
        if not os.path.exists(self.data_dir):
            os.makedirs(self.data_dir)

        self.settings = settings if settings is not None else {}
        self.current_date = self._get_date_string()
        self.data_file = self._get_file_path(self.current_date)
        self.data = self._load_data()
        self.running = False
        self.thread = None
        self.lock = threading.Lock()
        self.last_save_time = time.time()
        # Past days' files never change again; each is read once and kept here
        self.history_cache = {}
        self.is_idle = False

    # -- day and file ------------------------------------------------------

    def _get_date_string(self):
        return datetime.now().strftime(DATE_FORMAT)

    def _get_file_path(self, date_str):
        return os.path.join(self.data_dir, f"{date_str}.json")

    def _load_data(self, date_str=None):
        file_path = self._get_file_path(date_str) if date_str else self.data_file
        if os.path.exists(file_path):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    return defaultdict(int, json.load(f))
            except Exception:
                return defaultdict(int)
        return defaultdict(int)

    def save_data(self):
        with self.lock:
            try:
                with open(self.data_file, "w", encoding="utf-8") as f:
                    json.dump(dict(self.data), f, ensure_ascii=False, indent=4)
                self.last_save_time = time.time()
            except Exception:
                pass

    def check_date_rollover(self):
        new_date = self._get_date_string()
        if new_date != self.current_date:
            self.save_data()
            with self.lock:
                self.current_date = new_date
                self.data_file = self._get_file_path(self.current_date)
                self.data = self._load_data()

    # -- measurement -------------------------------------------------------

    def _idle_seconds(self):
        """Time since the last keyboard/mouse input."""
        try:
            return max(0.0, (win32api.GetTickCount() - win32api.GetLastInputInfo()) / 1000.0)
        except Exception:
            return 0.0

    def get_active_window_info(self):
        try:
            window = win32gui.GetForegroundWindow()
            if not window or not win32gui.IsWindow(window):
                return None

            if win32gui.IsIconic(window):
                return None

            _, pid = win32process.GetWindowThreadProcessId(window)
            if pid <= 0:
                return None

            try:
                process = psutil.Process(pid)
                if not process.is_running():
                    return None

                app_name = process.name().lower().replace(".exe", "")
                if app_name in NEVER_TRACKED:
                    return None

                if app_name == "msedge":
                    return "Edge"
                elif app_name == "chrome":
                    return "Chrome"
                elif app_name == "explorer":
                    return "Windows Gezgini"

                return app_name.capitalize()
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                return None
        except Exception:
            return None

    def _track_loop(self):
        while self.running:
            try:
                self.check_date_rollover()

                if self.settings.get("idle_enabled", True):
                    timeout = max(10, int(self.settings.get("idle_timeout", 60)))
                    self.is_idle = self._idle_seconds() >= timeout
                else:
                    self.is_idle = False

                if not self.is_idle:
                    app_name = self.get_active_window_info()
                    if app_name:
                        with self.lock:
                            self.data[app_name] += 1

                if time.time() - self.last_save_time > 60:
                    self.save_data()
            except Exception:
                pass

            time.sleep(1)

    def start(self):
        if not self.running:
            self.running = True
            self.thread = threading.Thread(target=self._track_loop, daemon=True)
            self.thread.start()

    def stop(self):
        self.running = False
        self.save_data()

    # -- reading ----------------------------------------------------------

    def get_stats(self):
        """Today's in-memory counters."""
        with self.lock:
            return dict(self.data)

    def day_totals(self, date_str):
        """Totals for a single day. Today comes from memory, the past from the cache."""
        if date_str == self.current_date:
            return self.get_stats()

        cached = self.history_cache.get(date_str)
        if cached is not None:
            return cached

        totals = {}
        file_path = self._get_file_path(date_str)
        if os.path.exists(file_path):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                if isinstance(loaded, dict):
                    totals = loaded
            except Exception:
                totals = {}

        # The day rollover check may not have run yet; never cache today
        if date_str != self._get_date_string():
            self.history_cache[date_str] = totals
        return totals

    def get_tracked_dates(self, max_age=30.0):
        """Days that have a record file, oldest first. Briefly cached."""
        now = time.time()
        cached = getattr(self, "_dates_cache", None)
        if cached is not None and now - cached[0] < max_age:
            return cached[1]

        found = []
        try:
            filenames = os.listdir(self.data_dir)
        except OSError:
            return []

        for filename in filenames:
            if not filename.endswith(".json"):
                continue
            stem = filename[:-5]
            try:
                parsed = datetime.strptime(stem, DATE_FORMAT)
            except ValueError:
                continue  # files that are not days, such as usage_data.json
            found.append((parsed, stem))

        found.sort()
        dates = [stem for _parsed, stem in found]
        self._dates_cache = (now, dates)
        return dates

    @staticmethod
    def parse(date_str):
        try:
            return datetime.strptime(date_str, DATE_FORMAT)
        except (ValueError, TypeError):
            return None

    def has_record(self, date_str):
        """Whether that day has a record file. 'No data' and 'zero' are different things."""
        if date_str == self.current_date:
            return True
        return date_str in set(self.get_tracked_dates())

    def period_dates(self, period):
        """Days of the period, oldest first."""
        today = datetime.now()
        today_str = today.strftime(DATE_FORMAT)

        if period == "today":
            return [today_str]
        if period == "week":
            span = 7
        elif period == "month":
            span = 30
        else:
            # All time = CALENDAR range from the first record to today.
            # Returning only days that have a file ignored days without a record
            # (e.g. April) and led to wrong results like
            # "182 of 182 days active".
            tracked = self.get_tracked_dates()
            if not tracked:
                return [today_str]
            first = datetime.strptime(tracked[0], DATE_FORMAT)
            span = (today.date() - first.date()).days + 1
            return [(first + timedelta(days=i)).strftime(DATE_FORMAT)
                    for i in range(max(1, span))]

        return [(today - timedelta(days=i)).strftime(DATE_FORMAT)
                for i in range(span - 1, -1, -1)]

    def previous_period_dates(self, period):
        """The previous period of equal length, for comparison."""
        today = datetime.now()
        if period == "today":
            return [(today - timedelta(days=1)).strftime(DATE_FORMAT)]
        if period == "week":
            span, offset = 7, 7
        elif period == "month":
            span, offset = 30, 30
        else:
            return []
        return [(today - timedelta(days=offset + i)).strftime(DATE_FORMAT)
                for i in range(span - 1, -1, -1)]

    def aggregate(self, date_strs):
        """Per-app totals over the given days."""
        totals = defaultdict(int)
        for date_str in date_strs:
            for app, seconds in self.day_totals(date_str).items():
                totals[app] += seconds
        return dict(totals)

    def daily_series(self, date_strs, app=None):
        """[(day, seconds), ...] oldest first. If app is given, only that app."""
        series = []
        for date_str in date_strs:
            day = self.day_totals(date_str)
            if app is None:
                series.append((date_str, sum(day.values())))
            else:
                series.append((date_str, day.get(app, 0)))
        return series

    def get_historical_stats(self, days):
        """Backward compatibility: totals of the last `days` days."""
        today = datetime.now()
        dates = [(today - timedelta(days=i)).strftime(DATE_FORMAT) for i in range(days)]
        return self.aggregate(dates)
