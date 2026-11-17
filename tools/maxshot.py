import ctypes, ctypes.wintypes as wt, sys, subprocess

u32 = ctypes.windll.user32
u32.SetProcessDPIAware()
hwnd = int(sys.argv[1])
tag = sys.argv[2] if len(sys.argv) > 2 else "x"

class RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long), ("right", ctypes.c_long), ("bottom", ctypes.c_long)]
class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

SW_MAXIMIZE = 3
u32.ShowWindow(hwnd, SW_MAXIMIZE)
u32.SetForegroundWindow(hwnd)
import time; time.sleep(1.5)

w = RECT(); u32.GetWindowRect(hwnd, ctypes.byref(w))
c = RECT(); u32.GetClientRect(hwnd, ctypes.byref(c))
p = POINT(0, 0); u32.ClientToScreen(hwnd, ctypes.byref(p))
print(f"MAX window {w.left},{w.top}-{w.right},{w.bottom} client {c.right}x{c.bottom} at {p.x},{p.y} inset_top={p.y-w.top}")
out = rf"C:\Users\oscar\AppData\Local\hermes\cache\scratch\max_{tag}.png"
subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                r"C:\Users\oscar\Projects\edge-win7-glass\tools\shotfull.ps1", out], capture_output=True)
print("saved", out)
