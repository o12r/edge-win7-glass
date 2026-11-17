"""
striped_backdrop_test.py - controlled A/B for "does DWM/OpenGlass blur appear in a
transparent client region of a Chromium window?"

Backdrop: our own full-screen window painted with 4px vertical stripes (high detail).
Subject:  the Chromium window, maximized over it, with a rectangular hole cut in its
          tab strip (so the hole is the only place the stripes can show).
A: hole only                          -> stripes should be SHARP.
B: + DwmEnableBlurBehindWindow        -> stripes blurred = glass is possible.
C: + DwmExtendFrameIntoClientArea     -> second chance for OpenGlass to pick it up.

Sharpness = mean |horizontal gradient| inside the hole; blur flattens it.

usage: python striped_backdrop_test.py
"""
import ctypes, ctypes.wintypes as wt, sys, time, subprocess

u32 = ctypes.windll.user32
gdi = ctypes.windll.gdi32
dwm = ctypes.windll.dwmapi
u32.SetProcessDPIAware()
GWL_EXSTYLE = -20
CB = ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
SCRATCH = r"C:\Users\oscar\AppData\Local\hermes\cache\scratch"
WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wt.HWND, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t)


class RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


class WNDCLASS(ctypes.Structure):
    _fields_ = [("style", ctypes.c_uint), ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int), ("hInstance", wt.HINSTANCE), ("hIcon", wt.HICON),
                ("hCursor", wt.HANDLE), ("hbrBackground", wt.HBRUSH), ("lpszMenuName", wt.LPCWSTR),
                ("lpszClassName", wt.LPCWSTR)]


class DWM_BLURBEHIND(ctypes.Structure):
    _fields_ = [("dwFlags", wt.DWORD), ("fEnable", wt.BOOL), ("hRgnBlur", wt.HANDLE),
                ("fTransitionOnMaximized", wt.BOOL)]


class MARGINS(ctypes.Structure):
    _fields_ = [("cl", ctypes.c_int), ("cr", ctypes.c_int), ("ct", ctypes.c_int), ("cb", ctypes.c_int)]


u32.DefWindowProcW.argtypes = [wt.HWND, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t]
u32.DefWindowProcW.restype = ctypes.c_ssize_t
u32.GetWindowLongW.restype = ctypes.c_long
dwm.DwmEnableBlurBehindWindow.argtypes = [wt.HWND, ctypes.POINTER(DWM_BLURBEHIND)]
dwm.DwmExtendFrameIntoClientArea.argtypes = [wt.HWND, ctypes.POINTER(MARGINS)]


def wp(h, msg, wp_, lp):
    if msg == 0x000F:                      # WM_PAINT -> stripes
        ps = ctypes.create_string_buffer(96)
        hdc = u32.BeginPaint(h, ps)
        r = RECT(); u32.GetClientRect(h, ctypes.byref(r))
        for x in range(0, r.right, 8):
            col = 0x0000FF if (x // 8) % 2 == 0 else 0xFF0000   # BGR: red / blue
            br = gdi.CreateSolidBrush(col)
            rc = RECT(x, 0, x + 8, r.bottom)
            u32.FillRect(hdc, ctypes.byref(rc), br)
            gdi.DeleteObject(br)
        u32.EndPaint(h, ps)
        return 0
    if msg == 0x0010:
        u32.PostQuitMessage(0)
        return 0
    return u32.DefWindowProcW(h, msg, wp_, lp)


def find_chromium():
    hits = []

    def cb(h, l):
        if not u32.IsWindowVisible(h):
            return True
        b = ctypes.create_unicode_buffer(256)
        u32.GetClassNameW(h, b, 256)
        if b.value != "Chrome_WidgetWin_1":
            return True
        if u32.GetWindowLongW(h, GWL_EXSTYLE) & 0x80:
            return True
        t = ctypes.create_unicode_buffer(512)
        u32.GetWindowTextW(h, t, 512)
        if not t.value:
            return True
        r = RECT(); u32.GetWindowRect(h, ctypes.byref(r))
        hits.append((h, t.value, (r.right - r.left) * (r.bottom - r.top), r.left, r.top))
        return True

    u32.EnumWindows(CB(cb), 0)
    hits.sort(key=lambda x: -x[2])
    return hits[0]


def pump(sec):
    end = time.time() + sec
    while time.time() < end:
        msg = wt.MSG()
        while u32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
            u32.TranslateMessage(ctypes.byref(msg))
            u32.DispatchMessageW(ctypes.byref(msg))
        time.sleep(0.03)


def shot(tag):
    p = rf"{SCRATCH}\sb_{tag}.png"
    subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                    r"C:\Users\oscar\Projects\edge-win7-glass\tools\shotfull.ps1", p],
                   capture_output=True)
    print("saved", p, flush=True)
    return p


def sharpness(path, x, y, w, h):
    from PIL import Image
    im = Image.open(path).convert("L").crop((x, y, x + w, y + h))
    px = im.load()
    tot = n = 0
    for yy in range(0, h, 2):
        for xx in range(1, w, 2):
            tot += abs(px[xx, yy] - px[xx - 1, yy])
            n += 1
    return tot / max(n, 1)


def main():
    inst = ctypes.windll.kernel32.GetModuleHandleW(None)
    wc = WNDCLASS()
    wc.lpfnWndProc = WNDPROC(wp)
    wc.hInstance = inst
    wc.hbrBackground = None
    wc.lpszClassName = "SBStripes"
    u32.RegisterClassW(ctypes.byref(wc))
    sw, sh = u32.GetSystemMetrics(0), u32.GetSystemMetrics(1)
    back = u32.CreateWindowExW(0, "SBStripes", "stripes", 0x80000000 | 0x10000000,
                               -8, -8, sw + 16, sh + 16, None, None, inst, None)
    print("backdrop", back, flush=True)
    pump(0.6)

    h, title, _a, left, top = find_chromium()
    print(f"target hwnd={h} {title[:40]!r} at {left},{top}", flush=True)
    u32.ShowWindow(h, 3)
    u32.SetForegroundWindow(h)
    pump(1.2)

    # hole: inside the tab strip, away from tabs/buttons
    hx, hy, hw, hh = 1150, 62, 700, 56
    r = RECT(); u32.GetWindowRect(h, ctypes.byref(r))
    W, H = r.right - r.left, r.bottom - r.top
    hrgn = gdi.CreateRectRgn(0, 0, 1, 1)
    for a, b, c_, d in ((0, 0, W, hy), (0, hy + hh, W, H), (0, hy, hx, hy + hh), (hx + hw, hy, W, hy + hh)):
        if c_ <= a or d <= b:
            continue
        r1 = gdi.CreateRectRgn(a, b, c_, d)
        gdi.CombineRgn(hrgn, hrgn, r1, 2)
        gdi.DeleteObject(r1)
    u32.SetWindowRgn(h, hrgn, True)
    print("hole cut", flush=True)
    pump(1.0)
    p_a = shot("hole")

    hRgn = gdi.CreateRectRgn(0, 0, 4000, 4000)
    bb = DWM_BLURBEHIND(0x1 | 0x2, True, hRgn, False)
    print("DwmEnableBlurBehindWindow hr=0x%08X" % (dwm.DwmEnableBlurBehindWindow(h, ctypes.byref(bb)) & 0xFFFFFFFF), flush=True)
    pump(1.2)
    p_b = shot("blur")

    m = MARGINS(0, 0, hy + hh, 0)
    print("DwmExtendFrame hr=0x%08X" % (dwm.DwmExtendFrameIntoClientArea(h, ctypes.byref(m)) & 0xFFFFFFFF), flush=True)
    pump(1.2)
    p_c = shot("extend")

    # revert
    bb0 = DWM_BLURBEHIND(0x1, False, None, False)
    dwm.DwmEnableBlurBehindWindow(h, ctypes.byref(bb0))
    dwm.DwmExtendFrameIntoClientArea(h, ctypes.byref(MARGINS(0, 0, 0, 0)))
    u32.SetWindowRgn(h, None, True)
    u32.ShowWindow(back, 0)
    u32.DestroyWindow(back)
    pump(0.6)

    sx, sy = left + hx, top + hy
    for tag, path in (("A hole", p_a), ("B blur", p_b), ("C extend", p_c)):
        print(f"{tag:10s} sharpness={sharpness(path, sx + 3, sy + 3, hw - 6, hh - 6):.3f}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
