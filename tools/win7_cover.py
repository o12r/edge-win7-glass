"""
win7_cover.py - draw a real OpenGlass/DWM Win7 caption button strip ON TOP of
another window's own (Chromium-drawn) window buttons.

How it works: OpenGlass only paints a caption inside a window's *non-client*
area, so a caption can never overlap an app's client content. This creates a
tiny separate top-level window that consists of nothing but a caption
(WS_CAPTION, zero client height), keeps it glued to the top-right corner of the
target window, and makes it click-through (WS_EX_TRANSPARENT) so the real
buttons underneath still receive the clicks.

usage:  python win7_cover.py [--title SUBSTR] [--width 180] [--offset-y 0]
"""
import ctypes, ctypes.wintypes as wt, sys, time

u32 = ctypes.windll.user32
gdi = ctypes.windll.gdi32
u32.SetProcessDPIAware()

u32.DefWindowProcW.argtypes = [wt.HWND, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t]
u32.DefWindowProcW.restype = ctypes.c_ssize_t

WS_POPUP, WS_CAPTION, WS_SYSMENU = 0x80000000, 0x00C00000, 0x00080000
WS_VISIBLE, WS_CLIPCHILDREN = 0x10000000, 0x02000000
WS_EX_TOOLWINDOW, WS_EX_TRANSPARENT, WS_EX_LAYERED = 0x00000080, 0x00000020, 0x00080000
WS_EX_NOACTIVATE, WS_EX_TOPMOST = 0x08000000, 0x00000008
SW_HIDE, SW_SHOWNOACTIVATE = 0, 4

WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wt.HWND, ctypes.c_uint,
                             ctypes.c_size_t, ctypes.c_ssize_t)
CW = ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)


class WNDCLASS(ctypes.Structure):
    _fields_ = [("style", ctypes.c_uint), ("lpfnWndProc", WNDPROC),
                ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int),
                ("hInstance", wt.HINSTANCE), ("hIcon", wt.HICON), ("hCursor", wt.HANDLE),
                ("hbrBackground", wt.HBRUSH), ("lpszMenuName", wt.LPCWSTR),
                ("lpszClassName", wt.LPCWSTR)]


def arg(name, default):
    for i, a in enumerate(sys.argv):
        if a == name:
            return sys.argv[i + 1]
    return default


TITLE = arg("--title", "Edge")
WIDTH = int(arg("--width", "180"))
OFFY = int(arg("--offset-y", "0"))


_cb_ref = []


def _enum_chromium():
    hits = []

    def _cb(w, l):
        if not u32.IsWindowVisible(w):
            return True
        b = ctypes.create_unicode_buffer(512)
        u32.GetClassNameW(w, b, 512)
        if b.value == "Chrome_WidgetWin_1":
            t = ctypes.create_unicode_buffer(512)
            u32.GetWindowTextW(w, t, 512)
            if t.value:
                hits.append((w, t.value))
        return True

    cb = CW(_cb)
    _cb_ref.append(cb)          # keep the thunk alive during EnumWindows
    u32.EnumWindows(cb, 0)
    return hits


def find_target():
    deadline = time.time() + 40
    while time.time() < deadline:
        hits = _enum_chromium()
        for hh, t in hits:
            if TITLE.lower() in t.lower():
                return hh, t
        for hh, t in hits:
            if "Edge" in t or "Chromium" in t or "Chrome" in t:
                return hh, t
        time.sleep(0.5)
    return None, None


metrics = {}

def read_metrics():
    u32.GetSystemMetrics.restype = ctypes.c_int
    u32.GetSystemMetricsForDpi.restype = ctypes.c_int
    dpi = 96
    hwnd = u32.GetForegroundWindow()
    if hwnd:
        dpi = u32.GetDpiForWindow(hwnd) or 96
    for name, idx in (("cap", 4), ("cysize", 30), ("cxsizeframe", 32), ("cysizeframe", 33), ("padded", 92)):
        try:
            metrics[name] = u32.GetSystemMetricsForDpi(idx, dpi)
        except Exception:
            metrics[name] = u32.GetSystemMetrics(idx)
    metrics["dpi"] = dpi
    return metrics


state = {"hwnd": None, "target": None, "shown": False}


def wndproc(h, msg, wp, lp):
    # let Windows/DWM own everything about this window: it *is* a caption
    if msg == 0x0084:  # WM_NCHITTEST -> click-through, clicks land on the window below
        return -1      # HTTRANSPARENT
    if msg == 0x0010:  # WM_CLOSE
        return 0
    return u32.DefWindowProcW(h, msg, wp, lp)


def place():
    t = state["target"]
    if not t or not u32.IsWindow(t):
        t, _ = find_target()
        if not t:
            return False
        state["target"] = t
        print("re-targeted", t, flush=True)
    if u32.IsIconic(t) or not u32.IsWindowVisible(t):
        if state["shown"]:
            u32.ShowWindow(state["hwnd"], SW_HIDE)
            state["shown"] = False
        return True
    r = wt.RECT()
    u32.GetWindowRect(t, ctypes.byref(r))
    cap = metrics["cap"] + metrics["cysizeframe"] + metrics["padded"]
    x = r.right - metrics["cxsizeframe"] - (metrics["padded"] // 2) - WIDTH
    y = r.top + metrics["cysizeframe"] + cap + OFFY
    h = metrics["cysize"]
    u32.SetWindowPos(state["hwnd"], 0, x, y, WIDTH, h + metrics["cysizeframe"],
                     0x0014 | 0x0001)  # SWP_NOZORDER|SWP_NOACTIVATE|SWP_NOSIZE? no: keep size
    if not state["shown"]:
        u32.ShowWindow(state["hwnd"], SW_SHOWNOACTIVATE)
        state["shown"] = True
    return True


def main():
    read_metrics()
    print("metrics", metrics, flush=True)
    t, title = find_target()
    if not t:
        print("no target window found")
        return 1
    state["target"] = t
    print(f"target hwnd={t} title={title!r}", flush=True)

    inst = ctypes.windll.kernel32.GetModuleHandleW(None)
    wc = WNDCLASS()
    wc.lpfnWndProc = WNDPROC(wndproc)
    wc.hInstance = inst
    wc.hbrBackground = gdi.GetStockObject(4)     # BLACK_BRUSH
    wc.lpszClassName = "OGWin7Cover"
    u32.RegisterClassW(ctypes.byref(wc))

    ex = WS_EX_TOOLWINDOW | WS_EX_TRANSPARENT | WS_EX_LAYERED | WS_EX_NOACTIVATE
    style = WS_POPUP | WS_CAPTION | WS_SYSMENU
    h = u32.CreateWindowExW(ex, "OGWin7Cover", "", style,
                            0, 0, WIDTH, 60, t, None, inst, None)
    if not h:
        print("CreateWindowEx failed", ctypes.GetLastError())
        return 1
    state["hwnd"] = h
    print("overlay hwnd", h, flush=True)
    place()
    try:
        while True:
            if not place():
                break
            time.sleep(0.12)
    except KeyboardInterrupt:
        pass
    u32.DestroyWindow(h)
    return 0


if __name__ == "__main__":
    sys.exit(main())
