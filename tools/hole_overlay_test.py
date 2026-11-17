"""
hole_overlay_test.py - put a real OpenGlass caption strip on top of a hole that was cut
into another window, and compare it with the same strip sitting over opaque app pixels.

  python hole_overlay_test.py <x> <y> <w> <h> <tag>      (window-relative coords of the hole)

Prints the rect it used, then screenshots. Exits by itself.
"""
import ctypes, ctypes.wintypes as wt, sys, time, subprocess

u32 = ctypes.windll.user32
gdi = ctypes.windll.gdi32
u32.SetProcessDPIAware()
GWL_EXSTYLE = -20
CB = ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wt.HWND, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t)

WS_POPUP, WS_CAPTION, WS_SYSMENU = 0x80000000, 0x00C00000, 0x00080000
WS_VISIBLE = 0x10000000
WS_EX_TOOLWINDOW, WS_EX_TOPMOST, WS_EX_NOACTIVATE = 0x80, 0x08, 0x08000000


class RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long), ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


class WNDCLASS(ctypes.Structure):
    _fields_ = [("style", ctypes.c_uint), ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int), ("hInstance", wt.HINSTANCE), ("hIcon", wt.HICON),
                ("hCursor", wt.HANDLE), ("hbrBackground", wt.HBRUSH), ("lpszMenuName", wt.LPCWSTR),
                ("lpszClassName", wt.LPCWSTR)]


u32.GetWindowLongW.restype = ctypes.c_long
u32.DefWindowProcW.argtypes = [wt.HWND, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t]
u32.DefWindowProcW.restype = ctypes.c_ssize_t


def front_chromium():
    out = []

    def cb(h, l):
        if not u32.IsWindowVisible(h):
            return True
        b = ctypes.create_unicode_buffer(256)
        u32.GetClassNameW(h, b, 256)
        if b.value != "Chrome_WidgetWin_1":
            return True
        t = ctypes.create_unicode_buffer(512)
        u32.GetWindowTextW(h, t, 512)
        if not t.value or (u32.GetWindowLongW(h, GWL_EXSTYLE) & 0x80):
            return True
        out.append((h, t.value))
        return True

    u32.EnumWindows(CB(cb), 0)
    fg = u32.GetForegroundWindow()
    for h, t in out:
        if h == fg:
            return h, t
    return out[0] if out else (None, None)


def wndproc(h, msg, wp, lp):
    if msg == 0x0084:      # WM_NCHITTEST: behave like a caption
        return u32.DefWindowProcW(h, msg, wp, lp)
    if msg == 0x0010:
        u32.PostQuitMessage(0)
        return 0
    return u32.DefWindowProcW(h, msg, wp, lp)


def main():
    x, y, w, hh = (int(v) for v in sys.argv[1:5])
    tag = sys.argv[5] if len(sys.argv) > 5 else "hook"
    target, title = front_chromium()
    if not target:
        print("no chromium window")
        return 1
    r = RECT(); u32.GetWindowRect(target, ctypes.byref(r))
    px, py = r.left + x, r.top + y
    print(f"target {target} {title[:40]!r} window@{r.left},{r.top}", flush=True)

    inst = ctypes.windll.kernel32.GetModuleHandleW(None)
    wc = WNDCLASS()
    wc.lpfnWndProc = WNDPROC(wndproc)
    wc.hInstance = inst
    wc.hbrBackground = None
    wc.lpszClassName = "OGHoleOverlay"
    u32.RegisterClassW(ctypes.byref(wc))

    ov = u32.CreateWindowExW(WS_EX_TOOLWINDOW | WS_EX_TOPMOST | WS_EX_NOACTIVATE, "OGHoleOverlay", "",
                             WS_POPUP | WS_CAPTION | WS_SYSMENU, px, py, w, hh,
                             None, None, inst, None)
    print(f"overlay hwnd={ov} at {px},{py} {w}x{hh}", flush=True)
    u32.ShowWindow(ov, 4)   # SW_SHOWNOACTIVATE
    u32.SetWindowPos(ov, -1, px, py, w, hh, 0x0010 | 0x0001 | 0x0002)  # NOACTIVATE|NOSIZE|NOMOVE? keep
    deadline = time.time() + 3
    while time.time() < deadline:
        msg = wt.MSG()
        while u32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
            u32.TranslateMessage(ctypes.byref(msg))
            u32.DispatchMessageW(ctypes.byref(msg))
        time.sleep(0.05)

    out = rf"C:\Users\oscar\AppData\Local\hermes\cache\scratch\ho_{tag}.png"
    subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                    r"C:\Users\oscar\Projects\edge-win7-glass\tools\shotfull.ps1", out], capture_output=True)
    print("saved", out, flush=True)
    u32.DestroyWindow(ov)
    return 0


if __name__ == "__main__":
    sys.exit(main())
