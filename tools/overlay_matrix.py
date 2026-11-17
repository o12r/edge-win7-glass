"""
overlay_matrix.py - which window recipe actually gets OpenGlass glass + Win7 caption buttons?

Creates the same 500x90 caption strip over and over with different style/exstyle combinations,
screenshots each one, and tears it down.  Run with the hole already cut into the target window
so the glass backdrop is the desktop.

usage: python overlay_matrix.py <sx> <sy>      (screen coords for the strip's top-left)
"""
import ctypes, ctypes.wintypes as wt, sys, time, subprocess

u32 = ctypes.windll.user32
u32.SetProcessDPIAware()
WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wt.HWND, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t)

WS_POPUP, WS_CAPTION, WS_SYSMENU, WS_THICKFRAME = 0x80000000, 0x00C00000, 0x00080000, 0x00040000
WS_MINIMIZEBOX, WS_MAXIMIZEBOX = 0x00020000, 0x00010000
WS_EX_TOOLWINDOW, WS_EX_TOPMOST, WS_EX_NOACTIVATE, WS_EX_LAYERED = 0x80, 0x08, 0x08000000, 0x00080000


class WNDCLASS(ctypes.Structure):
    _fields_ = [("style", ctypes.c_uint), ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int), ("hInstance", wt.HINSTANCE), ("hIcon", wt.HICON),
                ("hCursor", wt.HANDLE), ("hbrBackground", wt.HBRUSH), ("lpszMenuName", wt.LPCWSTR),
                ("lpszClassName", wt.LPCWSTR)]


u32.DefWindowProcW.argtypes = [wt.HWND, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t]
u32.DefWindowProcW.restype = ctypes.c_ssize_t


def wndproc(h, msg, wp, lp):
    if msg == 0x0010:
        u32.PostQuitMessage(0)
        return 0
    return u32.DefWindowProcW(h, msg, wp, lp)


CONFIGS = [
    ("popup_tool",    WS_POPUP | WS_CAPTION | WS_SYSMENU, WS_EX_TOOLWINDOW | WS_EX_TOPMOST | WS_EX_NOACTIVATE),
    ("popup_plain",   WS_POPUP | WS_CAPTION | WS_SYSMENU, WS_EX_TOPMOST | WS_EX_NOACTIVATE),
    ("popup_frames",  WS_POPUP | WS_CAPTION | WS_THICKFRAME | WS_SYSMENU | WS_MINIMIZEBOX | WS_MAXIMIZEBOX,
                      WS_EX_TOPMOST | WS_EX_NOACTIVATE),
    ("popup_tall",    WS_POPUP | WS_CAPTION | WS_SYSMENU, WS_EX_TOOLWINDOW | WS_EX_TOPMOST | WS_EX_NOACTIVATE),
]


def main():
    sx, sy = int(sys.argv[1]), int(sys.argv[2])
    only = sys.argv[3] if len(sys.argv) > 3 else None
    inst = ctypes.windll.kernel32.GetModuleHandleW(None)
    wc = WNDCLASS()
    wc.lpfnWndProc = WNDPROC(wndproc)
    wc.hInstance = inst
    wc.hbrBackground = None
    wc.lpszClassName = "OGMatrix"
    u32.RegisterClassW(ctypes.byref(wc))

    for tag, style, ex in CONFIGS:
        if only and tag != only:
            continue
        big = (tag == "popup_tall")
        w, h = 500, (400 if big else 90)
        ov = u32.CreateWindowExW(ex, "OGMatrix", "", style, sx, sy, w, h, None, None, inst, None)
        print(f"[{tag}] hwnd={ov} style=0x{style:08X} ex=0x{ex:08X} {w}x{h}", flush=True)
        u32.ShowWindow(ov, 4)
        u32.SetWindowPos(ov, -1, sx, sy, w, h, 0x0010)
        deadline = time.time() + 2.5
        while time.time() < deadline:
            msg = wt.MSG()
            while u32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
                u32.TranslateMessage(ctypes.byref(msg))
                u32.DispatchMessageW(ctypes.byref(msg))
            time.sleep(0.05)
        suffix = sys.argv[4] if len(sys.argv) > 4 else ""
        out = rf"C:\Users\oscar\AppData\Local\hermes\cache\scratch\mx_{tag}{suffix}.png"
        subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                        r"C:\Users\oscar\Projects\edge-win7-glass\tools\shotfull.ps1", out], capture_output=True)
        print("saved", out, flush=True)
        u32.DestroyWindow(ov)
        time.sleep(0.4)
    return 0


if __name__ == "__main__":
    sys.exit(main())
