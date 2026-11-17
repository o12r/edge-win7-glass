"""
holes_demo.py - the corrected demo: window-region holes in the browser's tab strip
background, with a high-contrast backdrop so "glass" is unmistakable.

The region must be built as an EMPTY region plus the four rects around each hole
(OR of complements). Starting from the full window rect and OR-ing can only add area.

  python holes_demo.py <hwnd> [--stripes]

Notes:
  * hole coords are CLIENT coords; the code adds nc_top because SetWindowRgn works in
    window coords.
  * always resets the region before exiting.
"""
import ctypes, ctypes.wintypes as wt, subprocess, sys, time

u32 = ctypes.windll.user32
gdi = ctypes.windll.gdi32
u32.SetProcessDPIAware()
S = r"C:\Users\oscar\AppData\Local\hermes\cache\scratch"
WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wt.HWND, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t)


class RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


class WNDCLASS(ctypes.Structure):
    _fields_ = [("style", ctypes.c_uint), ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int), ("hInstance", wt.HINSTANCE), ("hIcon", wt.HICON),
                ("hCursor", wt.HANDLE), ("hbrBackground", wt.HBRUSH), ("lpszMenuName", wt.LPCWSTR),
                ("lpszClassName", wt.LPCWSTR)]


u32.DefWindowProcW.argtypes = [wt.HWND, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t]
u32.DefWindowProcW.restype = ctypes.c_ssize_t


def wp(h, msg, w, l):
    if msg == 0x000F:
        ps = ctypes.create_string_buffer(96)
        hdc = u32.BeginPaint(h, ps)
        r = RECT(); u32.GetClientRect(h, ctypes.byref(r))
        for i, x in enumerate(range(0, r.right, 8)):
            br = gdi.CreateSolidBrush(0x0000FF if i % 2 == 0 else 0xFF0000)
            rc = RECT(x, 0, x + 8, r.bottom)
            u32.FillRect(hdc, ctypes.byref(rc), br); gdi.DeleteObject(br)
        u32.EndPaint(h, ps); return 0
    if msg == 0x0010:
        u32.PostQuitMessage(0); return 0
    return u32.DefWindowProcW(h, msg, w, l)


def pump(sec):
    end = time.time() + sec
    while time.time() < end:
        m = wt.MSG()
        while u32.PeekMessageW(ctypes.byref(m), None, 0, 0, 1):
            u32.TranslateMessage(ctypes.byref(m)); u32.DispatchMessageW(ctypes.byref(m))
        time.sleep(0.03)


def build_region(h, holes):
    wr = RECT(); u32.GetWindowRect(h, ctypes.byref(wr))
    W, H = wr.right - wr.left, wr.bottom - wr.top
    c0 = wt.POINT(0, 0); u32.ClientToScreen(h, ctypes.byref(c0))
    nc_top = c0.y - wr.top
    x0 = c0.x - wr.left                      # client x offset inside window
    rgn = gdi.CreateRectRgn(0, 0, 0, 0)      # EMPTY region
    comp = [(0, 0, W, H)]                    # start from the full window, minus holes
    # A region can be built by starting empty and OR-ing rects; the complement of N holes
    # is a set of rects, so compute it as: horizontal bands x vertical slabs.
    hx = [(hx + x0, hy + nc_top, hx + x0 + hw, hy + nc_top + hh) for hx, hy, hw, hh in holes]
    ys = sorted({y for r in hx for y in (r[1], r[3])})
    ys = [0] + ys + [H]
    for i in range(len(ys) - 1):
        y1, y2 = ys[i], ys[i + 1]
        if y2 <= y1:
            continue
        spans = [r for r in hx if r[1] <= y1 and r[3] >= y2]   # holes covering this band
        xs = sorted({x for r in spans for x in (r[0], r[2])})
        xs = [0] + xs + [W]
        for j in range(len(xs) - 1):
            x1, x2 = xs[j], xs[j + 1]
            if x2 <= x1:
                continue
            if any(a <= x1 and x2 <= c for a, b, c, d in spans):
                continue                     # this slab is inside a hole
            r1 = gdi.CreateRectRgn(x1, y1, x2, y2)
            gdi.CombineRgn(rgn, rgn, r1, 2)  # RGN_OR
            gdi.DeleteObject(r1)
    return rgn, (W, H, nc_top, x0)


def main():
    h = int(sys.argv[1])
    stripes = "--stripes" in sys.argv
    back = None
    if stripes:
        inst = ctypes.windll.kernel32.GetModuleHandleW(None)
        wc = WNDCLASS(); wc.lpfnWndProc = WNDPROC(wp); wc.hInstance = inst
        wc.hbrBackground = None; wc.lpszClassName = "HDStripes"
        u32.RegisterClassW(ctypes.byref(wc))
        sw, sh = u32.GetSystemMetrics(0), u32.GetSystemMetrics(1)
        back = u32.CreateWindowExW(0, "HDStripes", "s", 0x80000000 | 0x10000000,
                                   -8, -8, sw + 16, sh + 16, None, None, inst, None)
        pump(0.4)

    u32.SetWindowPos(h, 0, 100, 100, 1400, 900, 0x0040)
    u32.SetForegroundWindow(h)
    pump(1.0)

    def shot(tag):
        p = rf"{S}\hd_{tag}.png"
        subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                        r"C:\Users\oscar\Projects\edge-win7-glass\tools\shotfull.ps1", p], capture_output=True)
        print("saved", p, flush=True)
        return p

    a = shot("before")
    # tab-strip background: right of the + button, the gap right of the tab, and the
    # thin gap left of the tab chevron.  Heights/coords are for 100% DPI, 1400x900.
    holes = [(400, 4, 700, 46), (60, 4, 44, 46)]
    rgn, info = build_region(h, holes)
    print("region built, window", info, flush=True)
    print("SetWindowRgn ->", u32.SetWindowRgn(h, rgn, True), flush=True)
    pump(1.2)
    b = shot("after")

    from PIL import Image
    ia = Image.open(a).convert("RGB"); ib = Image.open(b).convert("RGB")
    c0 = wt.POINT(0, 0); u32.ClientToScreen(h, ctypes.byref(c0))
    print("samples (before -> after):", flush=True)
    for cx, cy in ((450, 20), (700, 20), (900, 20), (150, 20)):
        x, y = c0.x + cx, c0.y + cy
        print(f"  client({cx},{cy}) {ia.getpixel((x, y))} -> {ib.getpixel((x, y))}", flush=True)

    u32.SetWindowRgn(h, None, True)
    if back:
        u32.ShowWindow(back, 0); u32.DestroyWindow(back)
    pump(0.5)
    return 0


if __name__ == "__main__":
    sys.exit(main())
