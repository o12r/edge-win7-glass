import ctypes, ctypes.wintypes as wt, sys

u32 = ctypes.windll.user32
u32.SetProcessDPIAware()
dwm = ctypes.windll.dwmapi
hwnd = int(sys.argv[1])

class RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long), ("right", ctypes.c_long), ("bottom", ctypes.c_long)]
class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

w = RECT(); u32.GetWindowRect(hwnd, ctypes.byref(w))
c = RECT(); u32.GetClientRect(hwnd, ctypes.byref(c))
p = POINT(0, 0); u32.ClientToScreen(hwnd, ctypes.byref(p))
st = u32.GetWindowLongW(hwnd, -16) & 0xFFFFFFFF
print(f"hwnd={hwnd} style=0x{st:08X}")
print(f"window  {w.left},{w.top} - {w.right},{w.bottom}")
print(f"client  {c.right}x{c.bottom} at screen {p.x},{p.y}")
print(f"caption/frame height above client = {p.y - w.top}   left inset = {p.x - w.left}   right inset = {w.right - (p.x + c.right)}   bottom inset = {w.bottom - (p.y + c.bottom)}")
print(f"SM_CYCAPTION={u32.GetSystemMetrics(4)} SM_CXSIZEFRAME={u32.GetSystemMetrics(32)} SM_CYSIZEFRAME={u32.GetSystemMetrics(33)} SM_CXPADDEDBORDER={u32.GetSystemMetrics(92)} dpi={u32.GetDpiForWindow(hwnd)}")
# also children
CB = ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
def kids(h):
    out = []
    def cb(k, l):
        out.append(k); return True
    u32.EnumChildWindows(h, CB(cb), 0)
    return out
for k in kids(hwnd):
    if u32.IsWindowVisible(k):
        r = RECT(); u32.GetWindowRect(k, ctypes.byref(r))
        b = ctypes.create_unicode_buffer(256); u32.GetClassNameW(k, b, 256)
        print(f"  child {k} {b.value} {r.left},{r.top}-{r.right},{r.bottom}")
