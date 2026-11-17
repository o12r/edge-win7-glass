"""Launch a throwaway Edge profile window, maximise it, and measure where the tab strip
really ends vs. what UIA calls the tab band. Read-only w.r.t. the user's own windows."""
import ctypes, os, subprocess, sys, time
from ctypes import wintypes as wt

u32 = ctypes.windll.user32
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    u32.SetProcessDPIAware()


class RECT(ctypes.Structure):
    _fields_ = [("left", wt.LONG), ("top", wt.LONG), ("right", wt.LONG), ("bottom", wt.LONG)]


def win_rect(h):
    r = RECT(); u32.GetWindowRect(h, ctypes.byref(r))
    return r.left, r.top, r.right, r.bottom


EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
if not os.path.exists(EDGE):
    EDGE = r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"

profile = os.path.join(os.environ["TMPDIR"], "gt_scratch_profile")
before = set()
WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)


def chromes():
    out = []
    def cb(h, l):
        b = ctypes.create_unicode_buffer(64)
        u32.GetClassNameW(h, b, 64)
        if b.value.startswith("Chrome_WidgetWin") and u32.IsWindowVisible(h):
            pid = wt.DWORD(); u32.GetWindowThreadProcessId(h, ctypes.byref(pid))
            r = win_rect(h)
            if r[2] - r[0] > 400 and r[3] - r[1] > 300:
                out.append((h, pid.value, r))
        return True
    u32.EnumWindows(WNDENUMPROC(cb), 0)
    return out


before = {h for h, _, _ in chromes()}
p = subprocess.Popen([EDGE, f"--user-data-dir={profile}", "--no-first-run",
                      "--no-default-browser-check", "--window-size=1200,800",
                      "--new-window", "about:blank"])
hwnd = None
for _ in range(100):
    time.sleep(0.2)
    for h, pid, r in chromes():
        if h not in before and pid == p.pid:
            hwnd = h
            break
    if hwnd:
        break
if not hwnd:
    sys.exit("no scratch window")
time.sleep(2.5)
u32.ShowWindow(hwnd, 3)          # SW_MAXIMIZE
time.sleep(2.0)
print(f"scratch hwnd={hwnd:x} pid={p.pid} rect={win_rect(hwnd)} maximized={bool(u32.IsZoomed(hwnd))}")

sys.path.insert(0, r"C:\Users\oscar\Projects\edge-win7-glass\tools\native")
import comtypes.client
from comtypes.gen import UIAutomationClient as UIA
uia = comtypes.client.CreateObject(UIA.CUIAutomation, interface=UIA.IUIAutomation)
root = uia.ElementFromHandle(hwnd)
cond = uia.CreatePropertyCondition(UIA.UIA_ControlTypePropertyId, 50019)
found = root.FindAll(UIA.TreeScope_Descendants, cond)
tabs = []
for i in range(found.Length):
    el = found.GetElement(i)
    b = el.CurrentBoundingRectangle
    if b.right > b.left:
        tabs.append((b.left, b.top, b.right, b.bottom))
print("tab rects:", tabs)
band = (min(t[1] for t in tabs), max(t[3] for t in tabs)) if tabs else None
win = win_rect(hwnd)
if band:
    print(f"BAND y {band[0]}..{band[1]} h={band[1]-band[0]} | rel-win top={(band[0]-win[1])/2:.1f}"
          f" bottom={(band[1]-win[1])/2:.1f} DIP")

from PIL import ImageGrab
crop = (win[0], win[1], win[2], win[1] + 160)
img = ImageGrab.grab(bbox=crop, all_screens=True)
out = os.path.join(os.environ["TMPDIR"], "gt_pristine.png")
img.save(out)
print("saved", out, img.size)

# row profile across the right-hand part of the strip (where the caption corner lives)
sep = "\n"
rowinfo = []
for y in range(0, img.size[1]):
    px = [img.getpixel((x, y))[:3] for x in range(img.size[0] - 700, img.size[0] - 20, 5)]
    g = [0.299 * a + 0.587 * b + 0.114 * c for a, b, c in px]
    m = sum(g) / len(g)
    sd = (sum((v - m) ** 2 for v in g) / len(g)) ** 0.5
    rowinfo.append((y, m, sd))
for y, m, sd in rowinfo:
    if y < 140:
        print(f"y={y:4d} dip={y/2:5.1f} mean={m:6.1f} sd={sd:5.1f}")
print("hwnd_hex", hex(hwnd))
