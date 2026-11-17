import ctypes, ctypes.wintypes as wt, tkinter as tk, threading, time, sys, os, subprocess

u32 = ctypes.windll.user32
u32.SetProcessDPIAware()

class MARGINS(ctypes.Structure):
    _fields_ = [("cl", ctypes.c_int), ("cr", ctypes.c_int), ("ct", ctypes.c_int), ("cb", ctypes.c_int)]

dwm = ctypes.windll.dwmapi
dwm.DwmExtendFrameIntoClientArea.argtypes = [wt.HWND, ctypes.POINTER(MARGINS)]
dwm.DwmExtendFrameIntoClientArea.restype = ctypes.c_long

mode = sys.argv[1] if len(sys.argv) > 1 else "all"
out = sys.argv[2] if len(sys.argv) > 2 else r"C:\Users\oscar\AppData\Local\hermes\cache\scratch\glassy.png"

root = tk.Tk()
root.title("GLASS TEST WINDOW")
root.geometry("1000x600+120+80")
root.configure(bg="#ffffff")

hwnd = u32.GetParent(root.winfo_id()) or root.winfo_id()
root.update()
hwnd = int(root.wm_frame(), 16) if hasattr(root, "wm_frame") else hwnd

def report():
    r = wt.RECT()
    u32.GetWindowRect(hwnd, ctypes.byref(r))
    print("hwnd", hwnd, "winrect", r.left, r.top, r.right, r.bottom, flush=True)

report()

def apply():
    m = MARGINS()
    if mode == "all":
        m.cl = m.cr = m.ct = m.cb = -1
    elif mode == "top40":
        m.cl = m.cr = m.cb = 0
        m.ct = 40
    elif mode == "topneg":
        m.cl = m.cr = m.cb = 0
        m.ct = -1
    r = dwm.DwmExtendFrameIntoClientArea(hwnd, ctypes.byref(m))
    print("DwmExtendFrameIntoClientArea ->", r, "mode", mode, flush=True)

def shot():
    time.sleep(1.0)
    apply()
    time.sleep(1.5)
    subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                    r"C:\Users\oscar\Projects\edge-win7-glass\tools\shotfull.ps1", out], capture_output=True)
    print("saved", out, flush=True)
    root.after(300, root.destroy)

threading.Thread(target=shot, daemon=True).start()
root.after(8000, root.destroy)
root.mainloop()
