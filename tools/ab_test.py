"""
ab_test.py - strong-contrast test for "hole -> overlay glass samples the desktop".

Layout: a maximized WHITE window W (stands in for an app that paints its own chrome),
plus an OpenGlass caption strip O placed on top of it.  We screenshot O with W intact and
again after cutting a rectangular hole in W exactly under O.  If the hole works, the strip
underneath O gets darker (wallpaper instead of white).

usage: python ab_test.py
"""
import ctypes, ctypes.wintypes as wt, sys, time, subprocess

u32 = ctypes.windll.user32
gdi = ctypes.windll.gdi32
u32.SetProcessDPIAware()

WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wt.HWND, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t)
WS_POPUP, WS_CAPTION, WS_SYSMENU, WS_THICKFRAME = 0x80000000, 0x00C00000, 0x00080000, 0x00040000
WS_MINIMIZEBOX, WS_MAXIMIZEBOX, WS_VISIBLE = 0x00020000, 0x00010000, 0x10000000
WS_EX_TOOLWINDOW, WS_EX_TOPMOST, WS_EX_NOACTIVATE = 0x80, 0x08, 0x08000000

OX, OY, OW, OH = 1030, 700, 500, 90          # overlay rect (screen)
SCRATCH = r"C:\Users\oscar\AppData\Local\hermes\cache\scratch"


class RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long), ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


class WNDCLASS(ctypes.Structure):
    _fields_ = [("style", ctypes.c_uint), ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int), ("hInstance", wt.HINSTANCE), ("hIcon", wt.HICON),
                ("hCursor", wt.HANDLE), ("hbrBackground", wt.HBRUSH), ("lpszMenuName", wt.LPCWSTR),
                ("lpszClassName", wt.LPCWSTR)]


u32.DefWindowProcW.argtypes = [wt.HWND, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t]
u32.DefWindowProcW.restype = ctypes.c_ssize_t

white_wnd = None


def wp_white(h, msg, wp, lp):
    if msg == 0x0083:                       # WM_NCCALCSIZE: all client
        return 0
    if msg in (0x0014, 0x000F):             # WM_ERASEBKGND / WM_PAINT -> plain white
        hdc = u32.GetDC(h)
        r = RECT(0, 0, 6000, 6000)
        u32.FillRect(hdc, ctypes.byref(r), gdi.GetStockObject(0))
        u32.ReleaseDC(h, hdc)
        return 1 if msg == 0x0014 else 0
    if msg == 0x0010:
        u32.PostQuitMessage(0)
        return 0
    return u32.DefWindowProcW(h, msg, wp, lp)


def wp_overlay(h, msg, wp, lp):
    if msg == 0x0010:
        return 0
    return u32.DefWindowProcW(h, msg, wp, lp)


def pump(sec):
    end = time.time() + sec
    while time.time() < end:
        msg = wt.MSG()
        while u32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
            u32.TranslateMessage(ctypes.byref(msg))
            u32.DispatchMessageW(ctypes.byref(msg))
        time.sleep(0.03)


def shot(tag):
    p = rf"{SCRATCH}\ab_{tag}.png"
    subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                    r"C:\Users\oscar\Projects\edge-win7-glass\tools\shotfull.ps1", p], capture_output=True)
    print("saved", p, flush=True)


def main():
    inst = ctypes.windll.kernel32.GetModuleHandleW(None)
    c1 = WNDCLASS(); c1.lpfnWndProc = WNDPROC(wp_white); c1.hInstance = inst
    c1.hbrBackground = None; c1.lpszClassName = "ABWhite"
    u32.RegisterClassW(ctypes.byref(c1))
    c2 = WNDCLASS(); c2.lpfnWndProc = WNDPROC(wp_overlay); c2.hInstance = inst
    c2.hbrBackground = None; c2.lpszClassName = "ABOverlay"
    u32.RegisterClassW(ctypes.byref(c2))

    sw, sh = u32.GetSystemMetrics(0), u32.GetSystemMetrics(1)
    w = u32.CreateWindowExW(0, "ABWhite", "white app stand-in",
                            WS_POPUP | WS_THICKFRAME | WS_VISIBLE, -8, -8, sw + 16, sh + 16,
                            None, None, inst, None)
    print("white hwnd", w, flush=True)
    pump(0.8)

    ov = u32.CreateWindowExW(WS_EX_TOPMOST | WS_EX_NOACTIVATE, "ABOverlay", "",
                             WS_POPUP | WS_CAPTION | WS_THICKFRAME | WS_SYSMENU | WS_MINIMIZEBOX | WS_MAXIMIZEBOX,
                             OX, OY, OW, OH, None, None, inst, None)
    print("overlay hwnd", ov, flush=True)
    u32.ShowWindow(ov, 4)
    u32.SetWindowPos(ov, -1, OX, OY, OW, OH, 0x0010)
    pump(2.5)
    shot("nohole")

    # cut the hole exactly under the overlay
    r = RECT(); u32.GetWindowRect(w, ctypes.byref(r))
    hx, hy = OX - r.left, OY - r.top
    W, H = r.right - r.left, r.bottom - r.top
    rects = [(0, 0, W, hy), (0, hy + OH, W, H), (0, hy, hx, hy + OH), (hx + OW, hy, W, hy + OH)]
    hrgn = gdi.CreateRectRgn(0, 0, 0, 0)
    for i, (a, b, c_, d) in enumerate(rects):
        if c_ <= a or d <= b:
            continue
        r1 = gdi.CreateRectRgn(a, b, c_, d)
        gdi.CombineRgn(hrgn, hrgn, r1, 2)     # RGN_OR
        gdi.DeleteObject(r1)
    ok = u32.SetWindowRgn(w, hrgn, True)
    print(f"hole at {hx},{hy} {OW}x{OH} in {W}x{H} -> SetWindowRgn {ok}", flush=True)
    u32.SetWindowPos(ov, -1, OX, OY, OW, OH, 0x0010)
    pump(1.5)
    shot("hole")

    u32.SetWindowRgn(w, None, True)
    u32.DestroyWindow(ov)
    u32.DestroyWindow(w)
    return 0


if __name__ == "__main__":
    sys.exit(main())
