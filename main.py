import threading
import time
import queue
import tkinter as tk

import pystray
from PIL import Image, ImageDraw

from tracker import ScreenTimeTracker
from ui import ScreenTimeUI
from settings import load_settings
from i18n import t
import paths


class ScreenTimeApp:
    def __init__(self):
        self.settings = load_settings()
        self.lang = self.settings.get("language", "en")
        self.tracker = ScreenTimeTracker(data_dir=paths.data_dir(), settings=self.settings)
        self.ui = ScreenTimeUI(self.tracker, settings=self.settings)
        self.icon = None
        self.running = True
        self.command_queue = queue.Queue()  # Thread-safe queue

    def create_image(self):
        size = 64
        background = "#151821"
        accent = "#5B8DEF"
        image = Image.new("RGB", (size, size), background)
        dc = ImageDraw.Draw(image)
        # A plain three-bar usage chart
        bars = [(14, 38), (27, 26), (40, 16)]
        for x, top in bars:
            dc.rectangle([x, top, x + 9, 50], fill=accent)
        return image

    def on_show_hide(self, icon, item):
        self.command_queue.put("SHOW_HIDE")

    def on_exit(self, icon, item):
        self.command_queue.put("EXIT")

    def process_queue(self):
        try:
            while not self.command_queue.empty():
                cmd = self.command_queue.get_nowait()
                if cmd == "SHOW_HIDE":
                    if self.ui.is_visible:
                        self.ui.hide()
                    else:
                        self.ui.show()
                elif cmd == "EXIT":
                    self.running = False
                    self.tracker.stop()  # This already calls save_data()
                    self.icon.stop()
                    if self.ui.root:
                        self.ui.root.destroy()
                    return

        except Exception as e:
            print(f"Queue processing error: {e}")

    def run(self):
        self.tracker.start()

        menu = pystray.Menu(
            pystray.MenuItem(t(self.lang, "app_title"), self.on_show_hide, default=True),
            pystray.MenuItem(t(self.lang, "close"), self.on_exit),
        )

        self.icon = pystray.Icon(
            "ScreenTime",
            self.create_image(),
            t(self.lang, "app_title"),
            menu,
        )

        tray_thread = threading.Thread(target=self.icon.run, daemon=True)
        tray_thread.start()

        try:
            while self.running:
                self.process_queue()

                if self.running:
                    self.ui.run_step()

                # No need to spin fast while the window is hidden
                time.sleep(0.02 if self.ui.is_visible else 0.12)
        except (tk.TclError, KeyboardInterrupt):
            pass
        finally:
            if self.running:
                self.tracker.stop()
                if self.icon:
                    self.icon.stop()


if __name__ == "__main__":
    app = ScreenTimeApp()
    app.run()
