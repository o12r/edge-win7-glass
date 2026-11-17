"""
region_test.py - cut a hole in another process's window with SetWindowRgn and see whether
the desktop (not the app's own pixels) shows through it.

  python region_test.py hole   <x> <y> <w> <h>    cut a rectangular hole
  python region_test.py reset                     restore the full rectangular region
"""
import ctypes, ctypes.wintypes as wt, sys, time, subprocess

u32 = ctypes.windll.user32
gdi = ctypes.windll.gdi32
u32.SetProcessDPIAware()
GWL_EXSTYLE = -20
CB = ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)


class RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long), ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


u32.GetWindowLongW.restype = ctypes.c_long


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
    if not out:
        return None
    # biggest window wins: an overlay test can steal foreground, but not area
    def area(x):
        r = RECT(); u32.GetWindowRect(x[0], ctypes.byref(r))
        return (r.right - r.left) * (r.bottom - r.top)
    return max(out, key=area)


def shot(tag, out):
    p = out.replace(".png", f"_{tag}.png")
    subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                    r"C:\Users\oscar\Projects\edge-win7-glass\tools\shotfull.ps1", p], capture_output=True)
    print("saved", p, flush=True)


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "hole"
    out = r"C:\Users\oscar\AppData\Local\hermes\cache\scratch\rt.png"
    hit = front_chromium()
    if not hit:
        print("no chromium window")
        return 1
    h, title = hit
    print(f"target {h} {title[:50]!r} fg={u32.GetForegroundWindow() == h}", flush=True)

    if mode == "reset":
        u32.SetWindowRgn(h, None, True)
        print("region reset ->", u32.SetWindowRgn(h, None, True), flush=True)
        time.sleep(0.6)
        shot("reset", out)
        return 0

    x, y, w, hh = (int(v) for v in sys.argv[2:6])
    r = RECT(); u32.GetWindowRect(h, ctypes.byref(r))
    W, H = r.right - r.left, r.bottom - r.top
    # two rects: full window minus the hole  (x,y,w,hh are window-relative)
    rects = [
        (0, 0, W, y),
        (0, y + hh, W, H),
        (0, y, x, y + hh),
        (x + w, y, W, y + hh),
    ]
    n = len(rects)
    arr = (RECT * n)(*[RECT(a, b, c, d) for a, b, c, d in rects if c > a and d > b])
    n = len(arr)
    hrgn = gdi.CreateRectRgn(0, 0, 0, 0)
    gdi.CombineRgn(hrgn, hrgn, gdi.CreateRectRgn(0, 0, 0, 0), 4)  # clear
    # build union of the 4 rects
    tmp = gdi.CreateRectRgn(0, 0, 0, 0)
    gdi.SetRectRgn(tmp, 0, 0, 0, 0)
    for i, rc in enumerate(arr):
        r1 = gdi.CreateRectRgn(rc.left, rc.top, rc.right, rc.bottom)
        gdi.CombineRgn(hrgn, hrgn, r1, 2 if i == 0 else 2)   # RGN_OR
        gdi.DeleteObject(r1)
    ok = u32.SetWindowRgn(h, hrgn, True)
    err = ctypes.GetLastError()
    print(f"window {W}x{H} hole=({x},{y},{w},{hh}) rects={n} SetWindowRgn -> {ok} err={err}", flush=True)
    time.sleep(0.8)
    shot("hole", out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
