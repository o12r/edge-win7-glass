"""
glass_in_hole.py - does the tabstrip area become real glass when the frame is extended?

Setup: a full-screen 8px red/blue striped backdrop window, then the scratch Edge window
on top of it. A hole is cut in Edge's tab strip (SetWindowRgn), so the stripes are the only
thing the hole can show.

  A  hole only                 -> sharp stripes (raw desktop through the hole)
  B  + extended frame (in-proc) -> blurred stripes = glass works, mod can target paint
                                   flat dark      = DWM paints an opaque caption there

usage: python glass_in_hole.py <hwnd>
"""
import ctypes, ctypes.wintypes as wt, subprocess, sys, time

u32 = ctypes.windll.user32
gdi = ctypes.windll.gdi32
dwm = ctypes.windll.dwmapi
u32.SetProcessDPIAware()
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


class MARGINS(ctypes.Structure):
    _fields_ = [("cl", ctypes.c_int), ("cr", ctypes.c_int), ("ct", ctypes.c_int), ("cb", ctypes.c_int)]


class DWM_BLURBEHIND(ctypes.Structure):
    _fields_ = [("dwFlags", wt.DWORD), ("fEnable", wt.BOOL), ("hRgnBlur", wt.HANDLE),
                ("fTransitionOnMaximized", wt.BOOL)]


u32.DefWindowProcW.argtypes = [wt.HWND, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t]
u32.DefWindowProcW.restype = ctypes.c_ssize_t
dwm.DwmExtendFrameIntoClientArea.argtypes = [wt.HWND, ctypes.POINTER(MARGINS)]
dwm.DwmEnableBlurBehindWindow.argtypes = [wt.HWND, ctypes.POINTER(DWM_BLURBEHIND)]


def wp(h, msg, w, l):
    if msg == 0x000F:
        ps = ctypes.create_string_buffer(96)
        hdc = u32.BeginPaint(h, ps)
        r = RECT(); u32.GetClientRect(h, ctypes.byref(r))
        for i, x in enumerate(range(0, r.right, 8)):
            br = gdi.CreateSolidBrush(0x0000FF if i % 2 == 0 else 0xFF0000)
            rc = RECT(x, 0, x + 8, r.bottom)
            u32.FillRect(hdc, ctypes.byref(rc), br)
            gdi.DeleteObject(br)
        u32.EndPaint(h, ps)
        return 0
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


def shot(tag):
    p = rf"{SCRATCH}\gi_{tag}.png"
    subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                    r"C:\Users\oscar\Projects\edge-win7-glass\tools\shotfull.ps1", p], capture_output=True)
    print("saved", p, flush=True)
    return p


def main():
    h = int(sys.argv[1])
    inst = ctypes.windll.kernel32.GetModuleHandleW(None)
    wc = WNDCLASS(); wc.lpfnWndProc = WNDPROC(wp); wc.hInstance = inst
    wc.hbrBackground = None; wc.lpszClassName = "GIStripes"
    u32.RegisterClassW(ctypes.byref(wc))
    sw, sh = u32.GetSystemMetrics(0), u32.GetSystemMetrics(1)
    back = u32.CreateWindowExW(0, "GIStripes", "s", 0x80000000 | 0x10000000,
                               -8, -8, sw + 16, sh + 16, None, None, inst, None)
    pump(0.5)

    u32.SetWindowPos(h, 0, 100, 100, 1400, 900, 0x0040)
    u32.SetForegroundWindow(h)
    pump(1.0)

    wr = RECT(); u32.GetWindowRect(h, ctypes.byref(wr))
    c0 = wt.POINT(0, 0); u32.ClientToScreen(h, ctypes.byref(c0))
    nc_top = c0.y - wr.top
    print(f"window={wr.left},{wr.top},{wr.right},{wr.bottom} clientOrigin={c0.x},{c0.y} nc_top={nc_top}", flush=True)

    HX, HY, HW, HH = 600, 8, 500, 42          # client coords, inside the tab strip
    W, H = wr.right - wr.left, wr.bottom - wr.top
    hrgn = gdi.CreateRectRgn(0, 0, 1, 1)
    for a, b, c_, d in ((0, 0, W, HY + nc_top), (0, HY + nc_top + HH, W, H),
                        (0, HY + nc_top, HX, HY + nc_top + HH),
                        (HX + HW, HY + nc_top, W, HY + nc_top + HH)):
        if c_ <= a or d <= b:
            continue
        r1 = gdi.CreateRectRgn(a, b, c_, d)
        gdi.CombineRgn(hrgn, hrgn, r1, 2)
        gdi.DeleteObject(r1)
    u32.SetWindowRgn(h, hrgn, True)
    pump(1.0)
    a = shot("A_hole")

    top = nc_top + HY + HH + 8
    hr = dwm.DwmExtendFrameIntoClientArea(h, ctypes.byref(MARGINS(0, 0, top, 0)))
    print(f"extend top={top} -> 0x{hr & 0xFFFFFFFF:08X}", flush=True)
    pump(1.0)
    b = shot("B_extend")

    bb = DWM_BLURBEHIND(0x1 | 0x2, True, gdi.CreateRectRgn(0, 0, 4000, 4000), False)
    print("blurbehind -> 0x%08X" % (dwm.DwmEnableBlurBehindWindow(h, ctypes.byref(bb)) & 0xFFFFFFFF), flush=True)
    pump(1.0)
    c = shot("C_blur")

    u32.SetWindowRgn(h, None, True)
    dwm.DwmExtendFrameIntoClientArea(h, ctypes.byref(MARGINS(0, 0, 0, 0)))
    dwm.DwmEnableBlurBehindWindow(h, ctypes.byref(DWM_BLURBEHIND(0x1, False, None, False)))
    u32.ShowWindow(back, 0); u32.DestroyWindow(back)
    pump(0.4)

    from PIL import Image
    sx, sy = c0.x + HX, c0.y + HY
    for tag, path in (("A hole", a), ("B extend", b), ("C blur", c)):
        im = Image.open(path).convert("RGB")
        px = [im.getpixel((sx + x, sy + 20)) for x in range(0, HW, 40)]
        g = Image.open(path).convert("L").crop((sx + 2, sy + 2, sx + HW - 2, sy + HH - 2))
        p = g.load()
        tot = n = 0
        for yy in range(0, HH - 4, 2):
            for xx in range(1, HW - 4, 2):
                tot += abs(p[xx, yy] - p[xx - 1, yy]); n += 1
        print(f"{tag:10s} sharpness={tot / max(n,1):6.2f}  pixels={px}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
