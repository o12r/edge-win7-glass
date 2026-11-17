"""
glasstest.py - does OpenGlass/DWM fill an *extended frame* (client-area) region with glass?

Creates a window whose whole top STRIP is left unpainted (no WM_ERASEBKGND, no WM_PAINT
touch) so the only thing that can appear there is whatever the compositor puts behind
the window surface.  Everything below the strip is painted solid white, as a control.

variants:
  strip  - normal WS_CAPTION|WS_THICKFRAME, DwmExtendFrameIntoClientArea(cyTop=STRIP)
  nocc   - no caption at all (WM_NCCALCSIZE -> 0), DwmExtendFrameIntoClientArea(-1)
  plain  - no caption, NO extend  (baseline: proves the strip goes black)
usage: python glasstest.py <variant> <out.png>
"""
import ctypes, ctypes.wintypes as wt, sys, time, subprocess

u32 = ctypes.windll.user32
gdi = ctypes.windll.gdi32
dwm = ctypes.windll.dwmapi
u32.SetProcessDPIAware()

WL, WT, WR, WB = 200, 200, 1400, 700
STRIP = 90

WS_CAPTION, WS_THICKFRAME, WS_SYSMENU = 0x00C00000, 0x00040000, 0x00080000
WS_MINIMIZEBOX, WS_MAXIMIZEBOX = 0x00020000, 0x00010000
WS_OVERLAPPED, WS_VISIBLE = 0x00000000, 0x10000000
WS_EX_TOPMOST, WS_EX_NOACTIVATE = 0x00000008, 0x08000000

WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wt.HWND, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t)


class WNDCLASS(ctypes.Structure):
    _fields_ = [("style", ctypes.c_uint), ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int), ("hInstance", wt.HINSTANCE), ("hIcon", wt.HICON),
                ("hCursor", wt.HANDLE), ("hbrBackground", wt.HBRUSH), ("lpszMenuName", wt.LPCWSTR),
                ("lpszClassName", wt.LPCWSTR)]


class MARGINS(ctypes.Structure):
    _fields_ = [("cl", ctypes.c_int), ("cr", ctypes.c_int), ("ct", ctypes.c_int), ("cb", ctypes.c_int)]


class RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long), ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


variant = sys.argv[1] if len(sys.argv) > 1 else "strip"
out = sys.argv[2] if len(sys.argv) > 2 else r"C:\Users\oscar\AppData\Local\hermes\cache\scratch\gt.png"

u32.DefWindowProcW.argtypes = [wt.HWND, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t]
u32.DefWindowProcW.restype = ctypes.c_ssize_t
dwm.DwmExtendFrameIntoClientArea.argtypes = [wt.HWND, ctypes.POINTER(MARGINS)]

state = {"hwnd": None, "painted": False}


def paint(h):
    ps = ctypes.create_string_buffer(64 + 32)
    hdc = u32.BeginPaint(h, ps)
    r = RECT()
    u32.GetClientRect(h, ctypes.byref(r))
    top = 0 if variant == "paint" else STRIP
    # paint ONLY the control area below the strip; never touch the strip
    if variant == "paint":
        wb = gdi.CreateSolidBrush(0x000000FF)   # pure red BGR
    else:
        wb = gdi.GetStockObject(0)              # WHITE_BRUSH
    rect = RECT(0, top, r.right, r.bottom)
    u32.FillRect(hdc, ctypes.byref(rect), wb)
    gdi.SetBkMode(hdc, 1)
    gdi.SetTextColor(hdc, 0x000000C8)   # bluish, GDI COLORREF is BGR
    txt = f"{variant}: above this line = never painted by the app".encode("utf-16-le")
    u32.DrawTextW(hdc, ctypes.c_wchar_p(txt.decode("utf-16-le")), -1,
                  ctypes.byref(RECT(10, top + 14, r.right - 10, top + 60)), 0x10)
    u32.EndPaint(h, ps)
    state["painted"] = True


def wndproc(h, msg, wp, lp):
    if msg == 0x0083 and variant == "nocc":        # WM_NCCALCSIZE -> no non-client at all
        return 0
    if msg == 0x0014:                              # WM_ERASEBKGND: never erase (would paint the strip)
        return 1
    if msg == 0x000F:                              # WM_PAINT
        paint(h)
        return 0
    if msg == 0x0084 and variant == "nocc":        # WM_NCHITTEST: keep it draggable from the strip
        pt = wt.POINT(wt.LOWORD(lp), wt.HIWORD(lp))
        u32.ScreenToClient(h, ctypes.byref(pt))
        return 2 if pt.y < STRIP else 1            # HTCAPTION : HTCLIENT
    if msg == 0x0010:
        u32.PostQuitMessage(0)
        return 0
    return u32.DefWindowProcW(h, msg, wp, lp)


def main():
    inst = ctypes.windll.kernel32.GetModuleHandleW(None)
    wc = WNDCLASS()
    wc.lpfnWndProc = WNDPROC(wndproc)
    wc.hInstance = inst
    wc.hbrBackground = None                        # NULL brush: nothing is ever erased
    wc.lpszClassName = "OGGlassProbe"
    wc.hCursor = u32.LoadCursorW(None, 32512)
    if not u32.RegisterClassW(ctypes.byref(wc)):
        print("RegisterClass failed", ctypes.GetLastError())

    style = WS_OVERLAPPED | WS_VISIBLE
    if variant in ("strip", "paint"):
        style |= WS_CAPTION | WS_THICKFRAME | WS_SYSMENU | WS_MINIMIZEBOX | WS_MAXIMIZEBOX
    else:
        style |= WS_THICKFRAME | WS_SYSMENU | WS_MINIMIZEBOX | WS_MAXIMIZEBOX
    h = u32.CreateWindowExW(WS_EX_TOPMOST | WS_EX_NOACTIVATE, "OGGlassProbe",
                            f"glass probe [{variant}]", style, WL, WT, WR - WL, 400, None, None, inst, None)
    if not h:
        print("CreateWindowEx failed", ctypes.GetLastError())
        return 1
    state["hwnd"] = h

    if variant == "nocc":
        m = MARGINS(-1, -1, -1, -1)
    elif variant in ("strip", "paint"):
        m = MARGINS(0, 0, STRIP, 0)
    else:
        m = MARGINS(0, 0, 0, 0)
    hr = dwm.DwmExtendFrameIntoClientArea(h, ctypes.byref(m))
    print(f"variant={variant} hwnd={h} DwmExtendFrame ret=0x{hr & 0xFFFFFFFF:08X}", flush=True)

    wr = RECT(); u32.GetWindowRect(h, ctypes.byref(wr))
    cr = RECT(); u32.GetClientRect(h, ctypes.byref(cr))
    p = wt.POINT(0, 0); u32.ClientToScreen(h, ctypes.byref(p))
    print(f"window={wr.left},{wr.top}-{wr.right},{wr.bottom} client={cr.right}x{cr.bottom}@{p.x},{p.y} "
          f"nc_top={p.y - wr.top}", flush=True)

    u32.SetWindowPos(h, -1, 0, 0, 0, 0, 0x0001 | 0x0002)   # topmost, keep pos/size
    u32.SetForegroundWindow(h)
    deadline = time.time() + 4
    while time.time() < deadline:
        msg = wt.MSG()
        while u32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
            u32.TranslateMessage(ctypes.byref(msg))
            u32.DispatchMessageW(ctypes.byref(msg))
        time.sleep(0.05)
    print("painted:", state["painted"], flush=True)
    subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                    r"C:\Users\oscar\Projects\edge-win7-glass\tools\shotfull.ps1", out], capture_output=True)
    print("saved", out, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
