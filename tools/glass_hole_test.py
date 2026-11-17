"""
glass_hole_test.py - the make-or-break question for the injection route:

  If Chromium's surface is *transparent* in the tab strip (simulated with a SetWindowRgn
  hole), does OpenGlass/DWM render blurred Aero glass there, or does the hole just show the
  raw desktop?

  A: hole only              -> baseline. Should show SHARP desktop pixels.
  B: hole + DwmEnableBlurBehindWindow(region = whole client)  -> glass?
  C: hole + SetWindowCompositionAttribute(ACCENT_ENABLE_BLURBEHIND) -> glass?

Blur vs sharp is measured by local pixel variance: blur flattens detail.

usage: python glass_hole_test.py [hole_left hole_top hole_w hole_h]
"""
import ctypes, ctypes.wintypes as wt, sys, time, subprocess

u32 = ctypes.windll.user32
gdi = ctypes.windll.gdi32
dwm = ctypes.windll.dwmapi
u32.SetProcessDPIAware()
GWL_EXSTYLE = -20
CB = ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
SCRATCH = r"C:\Users\oscar\AppData\Local\hermes\cache\scratch"


class RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


class DWM_BLURBEHIND(ctypes.Structure):
    _fields_ = [("dwFlags", wt.DWORD), ("fEnable", wt.BOOL), ("hRgnBlur", wt.HANDLE),
                ("fTransitionOnMaximized", wt.BOOL)]


class ACCENTPOLICY(ctypes.Structure):
    _fields_ = [("AccentState", ctypes.c_int), ("AccentFlags", ctypes.c_int),
                ("GradientColor", ctypes.c_uint), ("AnimationId", ctypes.c_int)]


class WINDOWCOMPOSITIONATTRIBDATA(ctypes.Structure):
    _fields_ = [("Attribute", ctypes.c_int), ("Data", ctypes.c_void_p), ("SizeOfData", ctypes.c_size_t)]


class MARGINS(ctypes.Structure):
    _fields_ = [("cl", ctypes.c_int), ("cr", ctypes.c_int), ("ct", ctypes.c_int), ("cb", ctypes.c_int)]


DWM_BB_ENABLE, DWM_BB_BLURREGION = 0x1, 0x2
WCA_ACCENT_POLICY = 19
ACCENT_ENABLE_BLURBEHIND = 3
ACCENT_ENABLE_ACRYLICBLURBEHIND = 4

u32.GetWindowLongW.restype = ctypes.c_long
u32.SetWindowLongW.restype = ctypes.c_long
dwm.DwmEnableBlurBehindWindow.argtypes = [wt.HWND, ctypes.POINTER(DWM_BLURBEHIND)]
dwm.DwmExtendFrameIntoClientArea.argtypes = [wt.HWND, ctypes.POINTER(MARGINS)]


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
    return hits[0] if hits else (None, None, 0, 0, 0)


def shot(tag):
    p = rf"{SCRATCH}\gh_{tag}.png"
    subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                    r"C:\Users\oscar\Projects\edge-win7-glass\tools\shotfull.ps1", p],
                   capture_output=True)
    print("saved", p, flush=True)
    return p


def cut_hole(h, x, y, w, hh):
    r = RECT(); u32.GetWindowRect(h, ctypes.byref(r))
    W, H = r.right - r.left, r.bottom - r.top
    rects = [(0, 0, W, y), (0, y + hh, W, H), (0, y, x, y + hh), (x + w, y, W, y + hh)]
    hrgn = gdi.CreateRectRgn(0, 0, 1, 1)
    for a, b, c_, d in rects:
        if c_ <= a or d <= b:
            continue
        r1 = gdi.CreateRectRgn(a, b, c_, d)
        gdi.CombineRgn(hrgn, hrgn, r1, 2)
        gdi.DeleteObject(r1)
    u32.SetWindowRgn(h, hrgn, True)
    print(f"hole (client {x},{y} {w}x{hh}) in {W}x{H}", flush=True)


def set_accent(h, state):
    pol = ACCENTPOLICY(state, 0, 0, 0)
    data = WINDOWCOMPOSITIONATTRIBDATA(WCA_ACCENT_POLICY,
                                       ctypes.cast(ctypes.byref(pol), ctypes.c_void_p),
                                       ctypes.sizeof(pol))
    fn = u32.SetWindowCompositionAttribute
    fn.argtypes = [wt.HWND, ctypes.POINTER(WINDOWCOMPOSITIONATTRIBDATA)]
    ok = fn(h, ctypes.byref(data))
    print(f"SetWindowCompositionAttribute(state={state}) -> {ok} err={ctypes.GetLastError()}", flush=True)
    return ok


def sharpness(path, x, y, w, h):
    from PIL import Image
    im = Image.open(path).convert("L").crop((x, y, x + w, y + h))
    px = im.load()
    # mean absolute horizontal gradient: blur -> small, sharp detail -> large
    tot = n = 0
    for yy in range(0, h, 2):
        for xx in range(1, w, 2):
            tot += abs(px[xx, yy] - px[xx - 1, yy])
            n += 1
    return tot / max(n, 1)


def main():
    hx, hy, hw, hh = (int(v) for v in sys.argv[1:5]) if len(sys.argv) > 4 else (1200, 62, 700, 60)
    h, title, _area, left, top = find_chromium()
    if not h:
        print("no chromium window")
        return 1
    print(f"target hwnd={h} {title[:50]!r} at {left},{top}", flush=True)
    u32.ShowWindow(h, 3)
    u32.SetForegroundWindow(h)
    time.sleep(1.5)

    cut_hole(h, hx, hy, hw, hh)
    time.sleep(1.0)
    p_a = shot("hole_only")

    # B: classic per-region client blur (the Win7 mechanism Chrome used)
    hrgn = gdi.CreateRectRgn(0, 0, 4000, 4000)      # client coords, whole client
    bb = DWM_BLURBEHIND(DWM_BB_ENABLE | DWM_BB_BLURREGION, True, hrgn, False)
    hr = dwm.DwmEnableBlurBehindWindow(h, ctypes.byref(bb))
    print(f"DwmEnableBlurBehindWindow -> hr=0x{hr & 0xFFFFFFFF:08X}", flush=True)
    time.sleep(1.2)
    p_b = shot("blurbehind")

    # C: accent blur
    set_accent(h, ACCENT_ENABLE_ACRYLICBLURBEHIND)
    time.sleep(1.2)
    p_c = shot("acrylic")

    # D: extend frame as well (top margin) - in case OpenGlass needs the margin
    m = MARGINS(0, 0, hy + hh, 0)
    hr2 = dwm.DwmExtendFrameIntoClientArea(h, ctypes.byref(m))
    print(f"DwmExtendFrameIntoClientArea(top={hy + hh}) -> hr=0x{hr2 & 0xFFFFFFFF:08X}", flush=True)
    time.sleep(1.2)
    p_d = shot("blur_extend")

    # --- revert everything ---
    set_accent(h, 0)                     # ACCENT_DISABLED
    bb0 = DWM_BLURBEHIND(DWM_BB_ENABLE, False, None, False)
    dwm.DwmEnableBlurBehindWindow(h, ctypes.byref(bb0))
    m0 = MARGINS(0, 0, 0, 0)
    dwm.DwmExtendFrameIntoClientArea(h, ctypes.byref(m0))
    u32.SetWindowRgn(h, None, True)
    time.sleep(0.8)
    shot("reset")

    sx, sy = left + hx, top + hy
    for tag, path in (("A hole_only", p_a), ("B blurbehind", p_b),
                      ("C acrylic", p_c), ("D blur+extend", p_d)):
        print(f"{tag:16s} sharpness={sharpness(path, sx + 4, sy + 4, hw - 8, hh - 8):.3f}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
