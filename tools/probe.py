import ctypes, ctypes.wintypes as wt, sys, subprocess

u32 = ctypes.windll.user32
dwm = ctypes.windll.dwmapi
u32.SetProcessDPIAware()

class RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                ("right", ctypes.c_long), ("bottom", ctypes.c_long)]
class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

CB = ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)

def tops():
    out = []
    def cb(h, l):
        out.append(h)
        return True
    u32.EnumWindows(CB(cb), 0)
    return out

def pid_of(h):
    p = wt.DWORD()
    u32.GetWindowThreadProcessId(h, ctypes.byref(p))
    return p.value

def cls_of(h):
    b = ctypes.create_unicode_buffer(512)
    u32.GetClassNameW(h, b, 512)
    return b.value

def txt_of(h):
    b = ctypes.create_unicode_buffer(1024)
    u32.GetWindowTextW(h, b, 1024)
    return b.value

def rect(h):
    r = RECT(); u32.GetWindowRect(h, ctypes.byref(r)); return (r.left, r.top, r.right, r.bottom)

def ext(h):
    r = RECT()
    dwm.DwmGetWindowAttribute(h, 9, ctypes.byref(r), ctypes.sizeof(r))
    return (r.left, r.top, r.right, r.bottom)

def gl(h, i):
    return u32.GetWindowLongW(h, i) & 0xFFFFFFFF

target = int(sys.argv[1]) if len(sys.argv) > 1 else None
for h in tops():
    if not u32.IsWindowVisible(h):
        continue
    if target and pid_of(h) != target:
        continue
    if cls_of(h) == "Chrome_WidgetWin_1":
        print(f"hwnd={h} pid={pid_of(h)} style=0x{gl(h,-16):08X} ex=0x{gl(h,-20):08X} win={rect(h)} ext={ext(h)} title={txt_of(h)[:60]!r}")
