import ctypes, ctypes.wintypes as wt, sys, subprocess, time, os

u32 = ctypes.windll.user32
u32.SetProcessDPIAware()
tag = sys.argv[1]

class RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long), ("right", ctypes.c_long), ("bottom", ctypes.c_long)]
class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]
CB = ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)

def edge_hwnds():
    out = []
    def cb(h, l):
        b = ctypes.create_unicode_buffer(256)
        u32.GetClassNameW(h, b, 256)
        if b.value == "Chrome_WidgetWin_1" and u32.IsWindowVisible(h):
            t = ctypes.create_unicode_buffer(512); u32.GetWindowTextW(h, t, 512)
            if "Edge" in t:
                out.append(h)
        return True
    u32.EnumWindows(CB(cb), 0)
    return out

def measure(h, maximize=True):
    if maximize:
        u32.ShowWindow(h, 3); u32.SetForegroundWindow(h); time.sleep(1.5)
    w = RECT(); u32.GetWindowRect(h, ctypes.byref(w))
    c = RECT(); u32.GetClientRect(h, ctypes.byref(c))
    p = POINT(0, 0); u32.ClientToScreen(h, ctypes.byref(p))
    print(f"[{tag}] hwnd={h} win={w.left},{w.top}-{w.right},{w.bottom} client={c.right}x{c.bottom}@({p.x},{p.y}) inset_top={p.y-w.top} left={p.x-w.left}", flush=True)
    out = rf"C:\Users\oscar\AppData\Local\hermes\cache\scratch\og_{tag}.png"
    subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                    r"C:\Users\oscar\Projects\edge-win7-glass\tools\shotfull.ps1", out], capture_output=True)
    print("saved", out, flush=True)

hs = edge_hwnds()
print("edge windows:", hs, flush=True)
if hs:
    measure(hs[0])
