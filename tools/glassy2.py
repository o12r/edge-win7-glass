import ctypes, ctypes.wintypes as wt, tkinter as tk, threading, time, sys, subprocess

u32 = ctypes.windll.user32
u32.SetProcessDPIAware()
GWL_STYLE, GWL_EXSTYLE = -16, -20
WS_CAPTION = 0x00C00000
WS_THICKFRAME = 0x00040000
WS_SYSMENU = 0x00080000
WS_MINIMIZEBOX = 0x00020000
WS_MAXIMIZEBOX = 0x00010000
SWP_NOSIZE, SWP_NOMOVE, SWP_NOZORDER, SWP_FRAMECHANGED = 0x1, 0x2, 0x4, 0x20

class MARGINS(ctypes.Structure):
    _fields_ = [("cl", ctypes.c_int), ("cr", ctypes.c_int), ("ct", ctypes.c_int), ("cb", ctypes.c_int)]

dwm = ctypes.windll.dwmapi
dwm.DwmExtendFrameIntoClientArea.argtypes = [wt.HWND, ctypes.POINTER(MARGINS)]
dwm.DwmExtendFrameIntoClientArea.restype = ctypes.c_long

mode = sys.argv[1] if len(sys.argv) > 1 else "frameless"
out = sys.argv[2] if len(sys.argv) > 2 else r"C:\Users\oscar\AppData\Local\hermes\cache\scratch\glassy2.png"

root = tk.Tk()
root.title("FRAMELESS GLASS TEST")
root.geometry("900x400+200+200")
root.configure(bg="#ffffff")
root.update()
hwnd = int(root.wm_frame(), 16)

def step():
    time.sleep(1.0)
    st = u32.GetWindowLongW(hwnd, GWL_STYLE) & 0xFFFFFFFF
    print("style before 0x%08X" % st, flush=True)
    if mode == "frameless":
        ns = st & ~WS_CAPTION
        ns &= ~0x80000000  # drop WS_POPUP if any
        ns |= WS_THICKFRAME | WS_SYSMENU | WS_MINIMIZEBOX | WS_MAXIMIZEBOX
        u32.SetWindowLongW(hwnd, GWL_STYLE, ctypes.c_long(ns).value)
        m = MARGINS(-1, -1, -1, -1)
        dwm.DwmExtendFrameIntoClientArea(hwnd, ctypes.byref(m))
        u32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_FRAMECHANGED)
    st2 = u32.GetWindowLongW(hwnd, GWL_STYLE) & 0xFFFFFFFF
    print("style after  0x%08X" % st2, flush=True)
    time.sleep(1.2)
    subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                    r"C:\Users\oscar\Projects\edge-win7-glass\tools\shotfull.ps1", out], capture_output=True)
    print("saved", out, flush=True)
    root.after(200, root.destroy)

threading.Thread(target=step, daemon=True).start()
root.after(9000, root.destroy)
root.mainloop()
