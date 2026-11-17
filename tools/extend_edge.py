"""
extend_edge.py - call DwmExtendFrameIntoClientArea on the *live Edge window* from a
foreign process, and see (a) whether the call is accepted, (b) what DWM then draws
in the extended strip.

usage: python extend_edge.py [top_px] [out.png]
"""
import ctypes, ctypes.wintypes as wt, sys, time, subprocess

u32 = ctypes.windll.user32
dwm = ctypes.windll.dwmapi
u32.SetProcessDPIAware()

TOP = int(sys.argv[1]) if len(sys.argv) > 1 else 80
OUT = sys.argv[2] if len(sys.argv) > 2 else r"C:\Users\oscar\AppData\Local\hermes\cache\scratch\ext_edge.png"

GWL_STYLE, GWL_EXSTYLE = -16, -20
CB = ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)


class MARGINS(ctypes.Structure):
    _fields_ = [("cl", ctypes.c_int), ("cr", ctypes.c_int), ("ct", ctypes.c_int), ("cb", ctypes.c_int)]


class RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long), ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


dwm.DwmExtendFrameIntoClientArea.argtypes = [wt.HWND, ctypes.POINTER(MARGINS)]
dwm.DwmExtendFrameIntoClientArea.restype = ctypes.c_long
u32.GetWindowLongW.restype = ctypes.c_long


def find_edge():
    hits = []

    def cb(h, l):
        if not u32.IsWindowVisible(h):
            return True
        b = ctypes.create_unicode_buffer(256)
        u32.GetClassNameW(h, b, 256)
        if b.value != "Chrome_WidgetWin_1":
            return True
        t = ctypes.create_unicode_buffer(512)
        u32.GetWindowTextW(h, t, 512)
        if not t.value:
            return True
        if u32.GetWindowLongW(h, GWL_EXSTYLE) & 0x00000080:   # tool window (popup/devtools)
            return True
        hits.append((h, t.value))
        return True

    u32.EnumWindows(CB(cb), 0)
    return hits


def main():
    hs = find_edge()
    print("edge top-level windows:", [(h, t[:60]) for h, t in hs], flush=True)
    if not hs:
        return 1
    h, title = max(hs, key=lambda x: (lambda r: (r.right - r.left) * (r.bottom - r.top))(get_rect(x[0])))
    print(f"target {h} {title!r}", flush=True)

    st = u32.GetWindowLongW(h, GWL_STYLE) & 0xFFFFFFFF
    ex = u32.GetWindowLongW(h, GWL_EXSTYLE) & 0xFFFFFFFF
    print(f"style=0x{st:08X} exstyle=0x{ex:08X} has_caption={bool(st & 0x00C00000)} "
          f"thickframe={bool(st & 0x00040000)}", flush=True)

    r = get_rect(h)
    c = RECT(); u32.GetClientRect(h, ctypes.byref(c))
    p = wt.POINT(0, 0); u32.ClientToScreen(h, ctypes.byref(p))
    print(f"win={r.left},{r.top}-{r.right},{r.bottom} client={c.right}x{c.bottom}@{p.x},{p.y} "
          f"nc_top={p.y - r.top}", flush=True)

    u32.ShowWindow(h, 3)          # SW_MAXIMIZE
    u32.SetForegroundWindow(h)
    time.sleep(1.5)
    shot("before")
    m = MARGINS(0, 0, TOP, 0)
    hr = dwm.DwmExtendFrameIntoClientArea(h, ctypes.byref(m))
    print(f"DwmExtendFrameIntoClientArea(top={TOP}) -> hr=0x{hr & 0xFFFFFFFF:08X} "
          f"({'OK' if (hr & 0xFFFFFFFF) == 0 else 'FAILED'})", flush=True)
    u32.SetWindowPos(h, 0, 0, 0, 0, 0, 0x0021 | 0x0002 | 0x0004)  # FRAMECHANGED|NOMOVE|NOZORDER
    time.sleep(1.5)
    shot("after")
    return 0


def get_rect(h):
    r = RECT(); u32.GetWindowRect(h, ctypes.byref(r)); return r


def shot(tag):
    out = OUT.replace(".png", f"_{tag}.png")
    subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                    r"C:\Users\oscar\Projects\edge-win7-glass\tools\shotfull.ps1", out], capture_output=True)
    print("saved", out, flush=True)


if __name__ == "__main__":
    sys.exit(main())
