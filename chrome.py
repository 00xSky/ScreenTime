"""Window frame: removes the Windows title bar so we can put our own
buttons in its place.

Instead of overrideredirect(True) we clear the WS_CAPTION bit. The window
thus stays on the taskbar, can still be minimized and resized from its
edges; only the white strip at the top goes away.
"""

import win32api
import win32con
import win32gui

_SWP = (win32con.SWP_FRAMECHANGED | win32con.SWP_NOMOVE |
        win32con.SWP_NOSIZE | win32con.SWP_NOZORDER | win32con.SWP_NOACTIVATE)


def handle(root):
    """OS-side handle of the Tk window."""
    try:
        return int(root.frame(), 16)
    except (ValueError, AttributeError):
        return None


def strip_titlebar(root):
    """Removes the title bar. Returns True on success."""
    hwnd = handle(root)
    if not hwnd:
        return False
    try:
        style = win32gui.GetWindowLong(hwnd, win32con.GWL_STYLE)
        style &= ~win32con.WS_CAPTION      # title strip and system buttons
        style |= win32con.WS_THICKFRAME    # keep edge resizing
        win32gui.SetWindowLong(hwnd, win32con.GWL_STYLE, style)
        win32gui.SetWindowPos(hwnd, 0, 0, 0, 0, 0, _SWP)
        return True
    except Exception:
        return False


def work_area(root):
    """Work area (excluding the taskbar) of the monitor under the cursor."""
    hwnd = handle(root)
    try:
        monitor = win32api.MonitorFromWindow(hwnd, win32con.MONITOR_DEFAULTTONEAREST)
        left, top, right, bottom = win32api.GetMonitorInfo(monitor)["Work"]
        return left, top, right - left, bottom - top
    except Exception:
        return (0, 0, root.winfo_screenwidth(), root.winfo_screenheight() - 48)


def bounds(root):
    """Outer rectangle of the window: (left, top, width, height)."""
    hwnd = handle(root)
    try:
        left, top, right, bottom = win32gui.GetWindowRect(hwnd)
        return left, top, right - left, bottom - top
    except Exception:
        return (root.winfo_x(), root.winfo_y(),
                root.winfo_width(), root.winfo_height())


def set_bounds(root, left, top, width, height):
    """Sets the outer rectangle directly.

    Tk's geometry() sets the inner area; since WS_THICKFRAME is kept, the
    invisible border in between had to be guessed. SetWindowPos takes
    the outer size directly, so no guessing is needed.
    """
    hwnd = handle(root)
    if not hwnd:
        return False
    try:
        win32gui.SetWindowPos(hwnd, 0, left, top, width, height,
                              win32con.SWP_NOZORDER | win32con.SWP_NOACTIVATE)
        return True
    except Exception:
        return False


def move_to(root, left, top):
    """Moves the window without touching its size or layout.

    Tk's geometry("+x+y") goes through the window manager layer and
    forces a layout pass; with the whole UI redrawn on every mouse move,
    dragging flickered. With SWP_NOSIZE, Tk does not even notice the move;
    only the window shifts.

    Sending WM_NCLBUTTONDOWN to hand the drag to Windows was an option,
    but SendMessage opens a nested message loop and releases the GIL, and
    Tk callbacks running inside that loop crash the interpreter.
    """
    hwnd = handle(root)
    if not hwnd:
        return False
    try:
        win32gui.SetWindowPos(hwnd, 0, int(left), int(top), 0, 0,
                              win32con.SWP_NOSIZE | win32con.SWP_NOZORDER |
                              win32con.SWP_NOACTIVATE)
        return True
    except Exception:
        return False


def minimize(root):
    hwnd = handle(root)
    try:
        win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)
    except Exception:
        try:
            root.iconify()
        except Exception:
            pass
