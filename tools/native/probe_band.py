"""Read-only probe: compare the UIA tab band with the real pixel row where the
toolbar starts, for an msedge top-level window. Nothing is modified."""
import ctypes, sys, time
from ctypes import wintypes as wt

u32 = ctypes.windll.user32
gdi = ctypes.windll.gdi32

# per-monitor DPI aware, otherwise every rect below is virtualised (>100% displays)
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    u32.SetProcessDPIAware()

class RECT(ctypes.Structure):
    _fields_ = [("left", wt.LONG), ("top", wt.LONG), ("right", wt.LONG), ("bottom", wt.LONG)]

def win_rect(h):
    r = RECT(); u32.GetWindowRect(h, ctypes.byref(r))
    return r.left, r.top, r.right, r.bottom

def dpi(h):
    try:
        return u32.GetDpiForWindow(h)
    except Exception:
        return 192

WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)

def windows():
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

ws = windows()
print("candidate windows:")
for h, pid, r in ws:
    print(f"  hwnd={h:x} pid={pid} rect={r} size={r[2]-r[0]}x{r[3]-r[1]} dpi={dpi(h)}")

if not ws:
    sys.exit("no window")

# pick one: prefer the hwnd passed on the command line
want = int(sys.argv[1], 16) if len(sys.argv) > 1 else ws[0][0]
h = next((h for h, _, _ in ws if h == want), ws[0][0])
r = win_rect(h)
scale = dpi(h) / 96.0
print(f"\nprobe hwnd={h:x} rect={r} scale={scale}")

# ---- UIA: tab band + address bar
sys.path.insert(0, r"C:\Users\oscar\Projects\edge-win7-glass\tools\native")
import comtypes.client
from comtypes.gen import UIAutomationClient as UIA

uia = comtypes.client.CreateObject(UIA.CUIAutomation, interface=UIA.IUIAutomation)
root = uia.ElementFromHandle(h)

def rect(el):
    b = el.CurrentBoundingRectangle
    if b.right <= b.left:
        return None
    return (b.left, b.top, b.right, b.bottom)

cond = uia.CreatePropertyCondition(UIA.UIA_ControlTypePropertyId, 50019)  # TabItem
found = root.FindAll(UIA.TreeScope_Descendants, cond)
tabs = []
for i in range(found.Length):
    el = found.GetElement(i)
    rr = rect(el)
    if rr and rr[3] > r[1] - 4 and rr[1] < r[1] + 260:
        tabs.append((el.CurrentName, rr))
print("tabs:", tabs[:6])

# address bar (Edit control type 50004) + top-level toolbar-ish elements
for ct, label in ((50004, "Edit"), (50017, "ToolBar"), (50000, "Button")):
    c = uia.CreatePropertyCondition(UIA.UIA_ControlTypePropertyId, ct)
    f = root.FindAll(UIA.TreeScope_Descendants, c)
    seen = []
    for i in range(min(f.Length, 40)):
        el = f.GetElement(i)
        rr = rect(el)
        if rr and rr[1] < r[1] + 200:
            seen.append((el.CurrentName[:24], rr))
    print(f"{label} near top: {seen[:8]}")

if tabs:
    y0 = min(t[1][1] for t in tabs)
    y1 = max(t[1][3] for t in tabs)
    print(f"\nBAND from UIA: y0={y0} y1={y1} height={y1-y0}  (top rel win = {y0-r[1]}, {(y0-r[1])/scale:.1f} DIP)"
          f"  bottom rel win = {y1-r[1]}, {(y1-r[1])/scale:.1f} DIP")

# ---- pixels: save a crop of the whole top strip
from PIL import ImageGrab
crop_top = r[1]
crop_bot = r[1] + int(150 * scale)
img = ImageGrab.grab(bbox=(r[0], crop_top, r[2], crop_bot), all_screens=True)
img.save(r"C:\Users\oscar\AppData\Local\hermes\cache\scratch\gt_top.png")
print(f"\nsaved crop {img.size} -> gt_top.png")

W, H = img.size
# two columns: one inside the tab strip (left), one inside the hole area (right)
cols = {"left(tab strip)": int(120 * scale), "right(hole)": W - int(40 * scale)}
for label, x in cols.items():
    print(f"\n{label} x={x} (abs {r[0]+x}): row colors rel-win")
    prev = None
    runs = []
    for y in range(0, H):
        px = img.getpixel((x, y))[:3]
        if prev is None or max(abs(a - b) for a, b in zip(px, prev)) > 6:
            runs.append((y, px))
            prev = px
    for y, px in runs[:40]:
        print(f"   y_rel={y:4d} dip={y/scale:6.1f}  rgb={px}")
