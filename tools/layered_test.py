"""
layered_test.py - can a *foreign* process make a Chromium window's own pixels transparent?

Tests the two mechanisms the "make the black strip transparent" idea depends on:
  1. WS_EX_LAYERED + SetLayeredWindowAttributes(LWA_COLORKEY) applied from outside
  2. WS_EX_LAYERED + LWA_ALPHA (sanity: if even this fails, layered is locked out)

Screenshots before / after / after-reset so the effect (if any) is visible.

usage: python layered_test.py [colorkey_hex]
"""
import ctypes, ctypes.wintypes as wt, sys, time, subprocess

u32 = ctypes.windll.user32
u32.SetProcessDPIAware()
GWL_STYLE, GWL_EXSTYLE = -16, -20
WS_EX_LAYERED = 0x00080000
LWA_COLORKEY, LWA_ALPHA = 0x1, 0x2
SWP = 0x0001 | 0x0002 | 0x0004 | 0x0020   # NOSIZE|NOMOVE|NOZORDER|FRAMECHANGED
CB = ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
SCRATCH = r"C:\Users\oscar\AppData\Local\hermes\cache\scratch"


class RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


u32.GetWindowLongW.restype = ctypes.c_long
u32.SetWindowLongW.restype = ctypes.c_long


def targets():
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
        ex = u32.GetWindowLongW(h, GWL_EXSTYLE) & 0xFFFFFFFF
        if not t.value or ex & 0x80:      # tool windows (devtools/popups)
            return True
        r = RECT(); u32.GetWindowRect(h, ctypes.byref(r))
        if u32.IsIconic(h):
            return True
        out.append((h, t.value, (r.right - r.left) * (r.bottom - r.top),
                    (r.left, r.top, r.right - r.left, r.bottom - r.top)))
        return True

    u32.EnumWindows(CB(cb), 0)
    out.sort(key=lambda x: -x[2])
    return out


def shot(tag):
    p = rf"{SCRATCH}\lay_{tag}.png"
    subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                    r"C:\Users\oscar\Projects\edge-win7-glass\tools\shotfull.ps1", p],
                   capture_output=True)
    print("saved", p, flush=True)


def main():
    key = int(sys.argv[1], 0) if len(sys.argv) > 1 else 0x000000
    hits = targets()
    if not hits:
        print("no chromium top-level window")
        return 1
    h, title, area, rect = hits[0]
    print(f"target hwnd={h} title={title[:60]!r} rect={rect}", flush=True)
    u32.ShowWindow(h, 3)          # maximize: strip is at a known place
    u32.SetForegroundWindow(h)
    time.sleep(1.2)
    shot("before")

    st = u32.GetWindowLongW(h, GWL_STYLE) & 0xFFFFFFFF
    ex = u32.GetWindowLongW(h, GWL_EXSTYLE) & 0xFFFFFFFF
    print(f"style=0x{st:08X} exstyle=0x{ex:08X}", flush=True)

    # --- 1. add WS_EX_LAYERED from outside, then colour-key pure black away
    r = u32.SetWindowLongW(h, GWL_EXSTYLE, ex | WS_EX_LAYERED)
    print(f"SetWindowLongW(+LAYERED) -> {r:#x} err={ctypes.GetLastError()}", flush=True)
    u32.SetWindowPos(h, 0, 0, 0, 0, 0, SWP)

    ok = u32.SetLayeredWindowAttributes(h, key & 0xFFFFFFFF, 0, LWA_COLORKEY)
    err = ctypes.GetLastError()
    print(f"SetLayeredWindowAttributes(colorkey={key:#08x}) -> {ok} err={err} "
          f"({'OK' if ok else 'DENIED/FAILED'})", flush=True)
    time.sleep(1.0)
    shot("colorkey")

    # --- 2. sanity: alpha
    ok2 = u32.SetLayeredWindowAttributes(h, 0, 128, LWA_ALPHA)
    err2 = ctypes.GetLastError()
    print(f"SetLayeredWindowAttributes(alpha=128) -> {ok2} err={err2}", flush=True)
    time.sleep(0.8)
    shot("alpha")

    # --- revert
    u32.SetLayeredWindowAttributes(h, 0, 255, LWA_ALPHA)
    u32.SetWindowLongW(h, GWL_EXSTYLE, ex & ~WS_EX_LAYERED)
    u32.SetWindowPos(h, 0, 0, 0, 0, 0, SWP)
    time.sleep(0.8)
    shot("reset")
    ex2 = u32.GetWindowLongW(h, GWL_EXSTYLE) & 0xFFFFFFFF
    print(f"exstyle after reset=0x{ex2:08X} layered={bool(ex2 & WS_EX_LAYERED)}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
