"""
dwm_caption_test.py - the top black bar is DWM's own caption, not Chromium pixels.
Toggle the DWM caption attributes from outside and see which one turns it into glass:

  20  DWMWA_USE_IMMERSIVE_DARK_MODE   0 -> light (glass-able) caption, 1 -> dark
  35  DWMWA_CAPTION_COLOR             solid colour, no glass        (control)
  38  DWMWA_SYSTEMBACKDROP_TYPE       2=DWMSBT_MAINWINDOW(mica) 3=acrylic 4=tabbed
  33  DWMWA_BORDER_COLOR
"""
import ctypes, ctypes.wintypes as wt, sys, time, subprocess

u32 = ctypes.windll.user32
dwm = ctypes.windll.dwmapi
u32.SetProcessDPIAware()
GWL_EXSTYLE = -20
CB = ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
SCRATCH = r"C:\Users\oscar\AppData\Local\hermes\cache\scratch"


class RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


u32.GetWindowLongW.restype = ctypes.c_long


def find_target():
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
        hits.append((h, t.value, (r.right - r.left) * (r.bottom - r.top)))
        return True

    u32.EnumWindows(CB(cb), 0)
    hits.sort(key=lambda x: -x[2])
    return hits[0] if hits else (None, None, 0)


def set_attr(h, attr, val, label):
    v = ctypes.c_int(val)
    hr = dwm.DwmSetWindowAttribute(h, attr, ctypes.byref(v), ctypes.sizeof(v))
    print(f"  {attr:3d} {label:34s} = {val:#010x} -> hr=0x{hr & 0xFFFFFFFF:08X}", flush=True)


def shot(tag):
    p = rf"{SCRATCH}\cap_{tag}.png"
    subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                    r"C:\Users\oscar\Projects\edge-win7-glass\tools\shotfull.ps1", p],
                   capture_output=True)
    print("  saved", p, flush=True)
    return p


def row_colors(path, y, xs):
    from PIL import Image
    im = Image.open(path).convert("RGB")
    return [im.getpixel((x, y)) for x in xs]


def main():
    h, title, _a = find_target()
    if not h:
        print("no chromium window")
        return 1
    print(f"target {h} {title[:50]!r}", flush=True)
    u32.ShowWindow(h, 3)
    u32.SetForegroundWindow(h)
    time.sleep(1.5)

    set_attr(h, 20, 1, "USE_IMMERSIVE_DARK_MODE")
    time.sleep(0.6); shot("dark_on")
    set_attr(h, 20, 0, "USE_IMMERSIVE_DARK_MODE")
    time.sleep(1.0); shot("dark_off")
    set_attr(h, 38, 2, "SYSTEMBACKDROP_TYPE mica")
    time.sleep(1.0); shot("backdrop_mica")
    set_attr(h, 38, 3, "SYSTEMBACKDROP_TYPE acrylic")
    time.sleep(1.0); shot("backdrop_acrylic")
    set_attr(h, 38, 0, "SYSTEMBACKDROP_TYPE none")
    # restore
    set_attr(h, 20, 1, "USE_IMMERSIVE_DARK_MODE (restore)")
    time.sleep(0.8); shot("restore")

    print("\nband colours (caption y=30, tabstrip y=95, toolbar y=160):", flush=True)
    for tag in ("dark_on", "dark_off", "backdrop_mica", "backdrop_acrylic"):
        p = rf"{SCRATCH}\cap_{tag}.png"
        print(tag, [row_colors(p, y, (400, 1200, 2000)) for y in (30, 95, 160)], flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
