"""
glass_titlebar.py - replace a Chromium browser's self-drawn title bar with a real glass bar.

The whole title bar strip (tabs + window buttons) is cut out of the window with SetWindowRgn,
which exposes the Aero/OpenGlass glass that DWM already renders behind it. A layered overlay
window then redraws the tabs, the new-tab button and the window buttons on top of that glass.

Tab text/state/rects and the button rects come from UI Automation, so the redrawn bar follows
tab open/close/selection and window resizes.

Interactions handled by the overlay:
  click tab        -> SelectionItemPattern.Select on that tab
  click tab close  -> Invoke on that tab's "Close tab" button
  click +          -> Ctrl+T to the browser
  click min/max/x  -> WM_SYSCOMMAND on the browser window
  drag empty area  -> move window
  double-click     -> toggle maximize

usage
  python glass_titlebar.py --hwnd 0x20FC4
  python glass_titlebar.py --pid 1072 --theme dark|light
Ctrl+C resets the window region and removes the overlay.
"""
from __future__ import annotations

import argparse
import ctypes
import ctypes.wintypes as wt
import json
import os
import queue
import re
import sys
import threading
import time

import comtypes.client
from PIL import Image, ImageChops, ImageDraw, ImageFont
from comtypes.gen import UIAutomationClient as UIA

u32 = ctypes.windll.user32
gdi = ctypes.windll.gdi32
k32 = ctypes.windll.kernel32
u32.SetProcessDPIAware()
sys.setswitchinterval(0.001)     # fast GIL hand-off: the mouse hook thread must never wait

DEBUG = os.environ.get("GLASS_TITLEBAR_DEBUG") == "1"
DEBUG_LOG = os.path.join(os.environ.get("LOCALAPPDATA") or os.environ.get("TEMP", "."),
                         "edge-win7-glass", "tool-debug.log")
try:
    os.makedirs(os.path.dirname(DEBUG_LOG), exist_ok=True)
except OSError:
    pass

_log_q = queue.Queue()


def dbg(msg):
    """Never touch the disk on the caller's thread: the mouse hook must return in <300 ms."""
    if DEBUG:
        _log_q.put(msg)


def trace(msg):
    """Always-on breadcrumb for the interactive paths (downs, drags, region clears).

    Cheap (queued, off-thread) and it is the only way to see what a real hand did when a
    behaviour cannot be reproduced with synthetic input.
    """
    _log_q.put(msg)


def _log_writer():
    while True:
        msg = _log_q.get()
        if msg is None:
            return
        try:
            with open(DEBUG_LOG, "a", encoding="utf-8") as f:
                f.write(f"{time.time():.2f} {msg}\n")
        except Exception:
            pass


threading.Thread(target=_log_writer, daemon=True).start()


_VOLATILE = re.compile(r"\d+(?:[.,]\d+)?\s*(?:MB|GB|KB|B)\b")


def _stable(name):
    """Drop volatile numbers (memory usage in the tab title) so signatures stay stable."""
    return _VOLATILE.sub("#", name)


GWL_STYLE = -16
WS_MAXIMIZE = 0x01000000
WS_EX_TOOLWINDOW, WS_EX_LAYERED, WS_EX_NOACTIVATE = 0x80, 0x00080000, 0x08000000
WS_POPUP = 0x80000000
SWP_NOZORDER, SWP_NOACTIVATE = 0x0004, 0x0010
SWP_NOMOVE, SWP_NOSIZE = 0x0002, 0x0001
SW_MAXIMIZE, SW_RESTORE, SW_MINIMIZE = 3, 9, 6
WM_SYSCOMMAND, SC_MINIMIZE, SC_MAXIMIZE, SC_RESTORE, SC_CLOSE = 0x0112, 0xF020, 0xF030, 0xF120, 0xF060
MA_NOACTIVATE = 3
AC_SRC_OVER, AC_SRC_ALPHA = 0x00, 0x01
SRCCOPY = 0x00CC0020
ULW_ALPHA = 0x02

CW = ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)


class RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class SIZE(ctypes.Structure):
    _fields_ = [("cx", ctypes.c_long), ("cy", ctypes.c_long)]


class BLENDFUNCTION(ctypes.Structure):
    _fields_ = [("BlendOp", ctypes.c_ubyte), ("BlendFlags", ctypes.c_ubyte),
                ("SourceConstantAlpha", ctypes.c_ubyte), ("AlphaFormat", ctypes.c_ubyte)]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wt.DWORD), ("biWidth", ctypes.c_long), ("biHeight", ctypes.c_long),
                ("biPlanes", wt.WORD), ("biBitCount", wt.WORD), ("biCompression", wt.DWORD),
                ("biSizeImage", wt.DWORD), ("biXPelsPerMeter", ctypes.c_long),
                ("biYPelsPerMeter", ctypes.c_long), ("biClrUsed", wt.DWORD), ("biClrImportant", wt.DWORD)]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wt.DWORD * 3)]


u32.GetWindowLongW.restype = ctypes.c_long
u32.SetWindowRgn.argtypes = [wt.HWND, wt.HANDLE, wt.BOOL]
u32.DefWindowProcW.argtypes = [wt.HWND, ctypes.c_uint, wt.WPARAM, wt.LPARAM]
u32.DefWindowProcW.restype = ctypes.c_ssize_t
gdi.CreateRectRgn.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int]
gdi.CreateRectRgn.restype = wt.HANDLE
gdi.CombineRgn.argtypes = [wt.HANDLE, wt.HANDLE, wt.HANDLE, ctypes.c_int]
gdi.DeleteObject.argtypes = [wt.HANDLE]
gdi.DeleteDC.argtypes = [wt.HDC]
gdi.CreateCompatibleDC.argtypes = [wt.HDC]
gdi.CreateCompatibleDC.restype = wt.HDC
gdi.SelectObject.argtypes = [wt.HDC, wt.HANDLE]
u32.GetDC.argtypes = [wt.HWND]
u32.GetDC.restype = wt.HDC
u32.ReleaseDC.argtypes = [wt.HWND, wt.HDC]
u32.UpdateLayeredWindow.argtypes = [wt.HWND, wt.HDC, ctypes.POINTER(POINT), ctypes.POINTER(SIZE),
                                    wt.HDC, ctypes.POINTER(POINT), wt.DWORD,
                                    ctypes.POINTER(BLENDFUNCTION), wt.DWORD]
gdi.CreateDIBSection.argtypes = [wt.HDC, ctypes.POINTER(BITMAPINFO), wt.UINT,
                                 ctypes.POINTER(ctypes.c_void_p), wt.HANDLE, wt.DWORD]

WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wt.HWND, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t)

WH_MOUSE_LL = 14
WM_APP = 0x8000
LLMHF_INJECTED = 0x01
WM_MOUSEMOVE, WM_LBUTTONDOWN, WM_LBUTTONUP = 0x0200, 0x0201, 0x0202
WM_RBUTTONDOWN, WM_RBUTTONUP, WM_MBUTTONDOWN, WM_MBUTTONUP = 0x0204, 0x0205, 0x0207, 0x0208
WM_MOUSEWHEEL = 0x020A
WM_NCLBUTTONDOWN = 0x00A1
HTCAPTION = 2
HT_EDGE = {"l": 10, "r": 11, "t": 12, "tl": 13, "tr": 14, "b": 15, "bl": 16, "br": 17}


class MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [("pt", POINT), ("mouseData", wt.DWORD), ("flags", wt.DWORD),
                ("time", wt.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class WNDCLASS(ctypes.Structure):
    _fields_ = [("style", ctypes.c_uint), ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int), ("hInstance", wt.HINSTANCE), ("hIcon", wt.HICON),
                ("hCursor", wt.HANDLE), ("hbrBackground", wt.HBRUSH), ("lpszMenuName", wt.LPCWSTR),
                ("lpszClassName", wt.LPCWSTR)]


# ------------------------------------------------------------------ UIA
TAB = UIA.UIA_TabItemControlTypeId
BTN = UIA.UIA_ButtonControlTypeId
SEL = UIA.UIA_SelectionItemPatternId
INV = UIA.UIA_InvokePatternId


def element_rect(el):
    b = el.CurrentBoundingRectangle
    if b.right <= b.left or b.bottom <= b.top:
        return None
    return (b.left, b.top, b.right, b.bottom)


class Snapshot:
    """Tabs + relevant buttons, as UIA sees them."""
    __slots__ = ("win", "band", "tabs", "min_r", "max_r", "close_r", "newtab_r", "search_r")

    def __init__(self, win, band, tabs, min_r, max_r, close_r, newtab_r, search_r):
        self.win, self.band, self.tabs = win, band, tabs
        self.min_r, self.max_r, self.close_r = min_r, max_r, close_r
        self.newtab_r, self.search_r = newtab_r, search_r

    def signature(self):
        # Tab titles carry volatile bits ("Memory usage - 106 MB"); collapse them so the bar
        # is not repainted several times a second (that starves the mouse hook).
        return (self.win, self.band,
                self.min_r, self.max_r, self.close_r, self.newtab_r,
                tuple((_stable(t["name"]), t["rect"], t["selected"]) for t in self.tabs))


def clone_snapshot(snap, win):
    """Copy a snapshot, shifting every rect so it describes the window at `win`.

    Lets the attach loop survive a move (hand-drag) without throwing the hole away while
    UIA is still reporting the old window rectangle.
    """
    dx, dy = win[0] - snap.win[0], win[1] - snap.win[1]

    def sh(r):
        return None if not r else (r[0] + dx, r[1] + dy, r[2] + dx, r[3] + dy)

    out = Snapshot(win, sh(snap.band),
                   [{**t, "rect": sh(t["rect"])} for t in snap.tabs],
                   sh(snap.min_r), sh(snap.max_r), sh(snap.close_r),
                   sh(snap.newtab_r), sh(snap.search_r))
    return out


class UiaWorker:
    def __init__(self, hwnd):
        self.hwnd = hwnd
        self.lock = threading.Lock()
        self.snap = None
        self.gen = 0

    def start(self):
        self.gen += 1
        threading.Thread(target=self._run, args=(self.gen,), daemon=True).start()

    def _run(self, gen):
        ole32 = ctypes.windll.ole32
        ole32.CoInitializeEx(None, 0x2)
        try:
            while self.gen == gen:
                t0 = time.time()
                try:
                    snap = self._sample()
                    if self.gen == gen:
                        with self.lock:
                            self.snap = (snap, time.time())
                except Exception as e:
                    dbg(f"uia error {e!r}")
                time.sleep(0.2 if time.time() - t0 < 0.2 else 0.02)
        finally:
            ole32.CoUninitialize()

    def _sample(self):
        uia = comtypes.client.CreateObject(UIA.CUIAutomation, interface=UIA.IUIAutomation)
        root = uia.ElementFromHandle(self.hwnd)
        win = window_rect(self.hwnd)

        tabs = []
        cond = uia.CreatePropertyCondition(UIA.UIA_ControlTypePropertyId, TAB)
        found = root.FindAll(UIA.TreeScope_Descendants, cond)
        for i in range(found.Length):
            el = found.GetElement(i)
            r = element_rect(el)
            if not r or r[3] < win[1] - 4 or r[1] > win[1] + 260:
                continue
            sel = False
            try:
                p = el.GetCurrentPattern(SEL)
                sel = bool(p.QueryInterface(UIA.IUIAutomationSelectionItemPattern).CurrentIsSelected)
            except Exception:
                pass
            tabs.append({"el": el, "name": el.CurrentName, "rect": r, "selected": sel})

        band = None
        if tabs:
            y0 = min(t["rect"][1] for t in tabs)
            y1 = max(t["rect"][3] for t in tabs)
            if 16 <= y1 - y0 <= 120:
                band = (win[0], y0, win[2], y1)

        rects = {}
        cond = uia.CreatePropertyCondition(UIA.UIA_ControlTypePropertyId, BTN)
        found = root.FindAll(UIA.TreeScope_Descendants, cond)
        for i in range(found.Length):
            el = found.GetElement(i)
            r = element_rect(el)
            if not r:
                continue
            name = el.CurrentName
            if band and not (r[3] > band[1] and r[1] < band[3]):
                continue
            if name == "Minimize":
                rects["min"] = r
            elif name == "Maximize" or name == "Restore":
                rects["max"] = r
            elif name == "Close" and not rects.get("close"):
                rects["close"] = r
            elif name == "New Tab":
                rects["newtab"] = r
            elif name == "Search tabs":
                rects["search"] = r
            elif name == "Close tab":
                # attach to the tab whose rect contains it
                for t in tabs:
                    tr = t["rect"]
                    if tr[0] <= r[0] <= tr[2] and tr[1] <= r[1] <= tr[3]:
                        t["close_el"] = el
                        t["close_rect"] = r
                        break
        return Snapshot(win, band, tabs, rects.get("min"), rects.get("max"),
                        rects.get("close"), rects.get("newtab"), rects.get("search"))

    def latest(self, max_age=1.5):
        with self.lock:
            s = self.snap
        if not s or time.time() - s[1] > max_age:
            return None
        return s[0]

    def stop(self):
        self.gen += 1


# ------------------------------------------------------------------ geometry
def window_rect(h):
    r = RECT(); u32.GetWindowRect(h, ctypes.byref(r))
    return r.left, r.top, r.right, r.bottom


def clip_region(win, hole):
    wx0, wy0, wx1, wy1 = win
    W, H = wx1 - wx0, wy1 - wy0
    a, b, c, d = hole
    a, b, c, d = max(0, a - wx0), max(0, b - wy0), min(W, c - wx0), min(H, d - wy0)
    if c <= a or d <= b:
        return None
    ys = sorted({0, b, d, H})
    rgn = gdi.CreateRectRgn(0, 0, 0, 0)
    for i in range(len(ys) - 1):
        y1, y2 = ys[i], ys[i + 1]
        if y2 <= y1:
            continue
        hole_band = (b <= y1 and d >= y2)
        xs = [0, a, c, W] if hole_band else [0, W]
        for j in range(len(xs) - 1):
            x1, x2 = xs[j], xs[j + 1]
            if x2 <= x1 or (hole_band and a <= x1 and x2 <= c):
                continue
            rr = gdi.CreateRectRgn(x1, y1, x2, y2)
            gdi.CombineRgn(rgn, rgn, rr, 2)
            gdi.DeleteObject(rr)
    return rgn


def round_corner_cut(x0, y0, x1, y1, r):
    """A cut rect whose bottom-left corner is rounded off (the window keeps a small arc).

    Row insets describe the arc: 0 at the top of the arc, r at the bottom edge, so the hole
    narrows as it approaches the toolbar and the visible corner is a quarter circle.
    """
    r = max(1, min(r, (y1 - y0) // 2, (x1 - x0) // 2))
    out = [(x0, y0, x1, y1 - r)]
    for i in range(r):                      # i = 0 is the top row of the arc
        inset = r - int(round(max(0.0, r * r - (i + 0.5) ** 2) ** 0.5))
        yy = y1 - r + i
        out.append((x0 + inset, yy, x1, yy + 1))
    return out


def is_fullscreen(hwnd, win):
    """True for real fullscreen (F11): the frame covers the whole monitor and is not maximized.

    Fullscreen must be left completely alone -- Chromium shows/hides its tab strip there as the
    cursor nears the top, and cutting a hole for that (or clearing it again) makes the region
    flicker. Maximized windows stay *outside* monitor bounds, so this does not catch them.
    """
    if u32.IsZoomed(hwnd):
        return False
    MONITORINFO = type("MONITORINFO", (ctypes.Structure,), {
        "_fields_": [("cbSize", wt.DWORD), ("rcMonitor", wt.RECT),
                     ("rcWork", wt.RECT), ("dwFlags", wt.DWORD)]})
    mi = MONITORINFO()
    mi.cbSize = ctypes.sizeof(mi)
    mon = u32.MonitorFromWindow(hwnd, 2)          # MONITOR_DEFAULTTONEAREST
    if not u32.GetMonitorInfoW(mon, ctypes.byref(mi)):
        return False
    m = mi.rcMonitor
    return (win[0] <= m.left and win[1] <= m.top and
            win[2] >= m.right and win[3] >= m.bottom)


def frame_region(win, cuts, inset=0, radius=0):
    """Window region = inset rounded rectangle (glass frame) minus `cuts` (screen coords).

    The inset gives the four-sided glass frame; `radius` rounds the two TOP corners so the
    frame does not look like a hard rectangle (bottom corners stay square, like Win7).
    """
    wx0, wy0, wx1, wy1 = win
    W, H = wx1 - wx0, wy1 - wy0
    if inset > 0:
        x0, y0, x1, y1 = inset, inset, W - inset + 1, H - inset + 1
    else:
        x0, y0, x1, y1 = 0, 0, W, H
    if radius > 0 and (x1 - x0) > 2 * radius and (y1 - y0) > 2 * radius:
        rgn = gdi.CreateRoundRectRgn(x0, y0, x1, y1, 2 * radius, 2 * radius)
        sq = gdi.CreateRectRgn(x0, y0 + radius, x1, y1)      # square off the bottom corners
        gdi.CombineRgn(rgn, rgn, sq, 2)                      # RGN_OR
        gdi.DeleteObject(sq)
    else:
        rgn = gdi.CreateRectRgn(x0, y0, x1, y1)
    for (l, t, r, b) in cuts:
        cx0, cy0 = max(0, l - wx0), max(0, t - wy0)
        cx1, cy1 = min(W, r - wx0), min(H, b - wy0)
        if cx1 <= cx0 or cy1 <= cy0:
            continue
        rr = gdi.CreateRectRgn(cx0, cy0, cx1, cy1)
        gdi.CombineRgn(rgn, rgn, rr, 4)                 # RGN_DIFF
        gdi.DeleteObject(rr)
    return rgn


def comb_region(win, band, keep):
    """Window region with the strip *background* cut out and `keep` rects left untouched.

    Native-tab mode (see FINDINGS §11): the native tab bodies stay pixel-identical (real
    favicons, real close buttons, real drag-reorder) and only the strip background behind
    them becomes glass.
    """
    wx0, wy0, wx1, wy1 = win
    W, H = wx1 - wx0, wy1 - wy0
    cut = gdi.CreateRectRgn(0, band[1] - wy0, W, band[3] - wy0)
    for r in keep:
        if not r:
            continue
        rr = gdi.CreateRectRgn(max(0, r[0] - wx0 - 1), max(0, r[1] - wy0),
                               min(W, r[2] - wx0 + 1), min(H, r[3] - wy0))
        gdi.CombineRgn(cut, cut, rr, 4)                 # RGN_DIFF
        gdi.DeleteObject(rr)
    whole = gdi.CreateRectRgn(0, 0, W, H)
    gdi.CombineRgn(whole, whole, cut, 4)
    gdi.DeleteObject(cut)
    return whole


def d3d_child(hwnd):
    """Chromium paints the whole browser UI (tab strip included) into its D3D child window
    with DirectComposition. A region on the top-level window does NOT clip that child, so the
    native tab strip survives a parent-only hole and shows through as a second layer."""
    out = []
    CB = ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)

    def cb(h, l):
        b = ctypes.create_unicode_buffer(128)
        u32.GetClassNameW(h, b, 128)
        if b.value == "Intermediate D3D Window":
            r = window_rect(h)
            out.append(((r[2] - r[0]) * (r[3] - r[1]), h))
        return True

    u32.EnumChildWindows.argtypes = [wt.HWND, ctypes.c_void_p, wt.LPARAM]
    u32.EnumChildWindows(hwnd, ctypes.cast(CB(cb), ctypes.c_void_p), 0)
    return max(out)[1] if out else None


def child_cut_region(child, hole):
    """Same band removed, but in the D3D child's local coordinates."""
    if not child or not u32.IsWindow(child):
        return None
    cr = window_rect(child)
    W, H = cr[2] - cr[0], cr[3] - cr[1]
    cut = hole[3] - cr[1]
    if cut <= 0 or cut >= H:
        return None
    return gdi.CreateRectRgn(-1, cut, W + 1, H + 1)


# ------------------------------------------------------------------ settings / layout
SETTINGS_PATH = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")),
                             "edge-win7-glass", "settings.json")


class Settings:
    """Tunables, read from %APPDATA%\\edge-win7-glass\\settings.json (CLI wins over file)."""

    DEFAULTS = {
        "theme": "light",          # light | dark
        "frame_px": 4,             # CSS px; thin glass frame on all four sides
        "corner_px": 6,            # CSS px; radius of the two top corners of the frame
        "gl_buttons": True,        # hand the top-right corner to OpenGlass caption buttons
        "tab_max_width": 220,      # CSS px; Win7/Chrome caps tabs at 220
        "tab_min_width": 70,
        "tab_radius": 6,
        "hover": True,
        "favicons": True,
        "wheel_tabs": True,        # wheel over the tab strip switches tabs
        "port": 8721,              # local settings page
        "autostart": False,
    }

    _PATH = SETTINGS_PATH

    def __init__(self, path=None, **over):
        object.__setattr__(self, "path", path or self._PATH)
        data = dict(self.DEFAULTS)
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                data.update({k: v for k, v in loaded.items() if k in self.DEFAULTS})
        except (OSError, ValueError):
            pass
        data.update({k: v for k, v in over.items() if v is not None})
        object.__setattr__(self, "data", data)

    def __getattr__(self, k):
        try:
            return object.__getattribute__(self, "data")[k]
        except KeyError:
            raise AttributeError(k)


def layout_tabs(snap, scale, cfg):
    """Win7-style strip: equal widths, capped at tab_max_width, left aligned, 1px-ish gaps.

    Tab rects from UIA are only used for identity/icon positions -- Chromium makes the last
    tab eat all the space, which is not what Win7 looked like.
    """
    band = snap.band
    n = len(snap.tabs)
    if not band or not n:
        return []
    start = band[0] + int(1 * scale)
    if snap.search_r:
        start = max(start, snap.search_r[2] + int(2 * scale))
    limit = (snap.newtab_r[0] - int(2 * scale)) if snap.newtab_r else band[2] - int(8 * scale)
    gap = max(1, int(2 * scale))
    avail = max(40 * scale, limit - start)
    max_w = max(60, int(cfg.tab_max_width * scale))
    min_w = max(30, int(cfg.tab_min_width * scale))
    w = min(max_w, max(min_w, int((avail - gap * (n - 1)) / n)))
    out = []
    x = start
    for _ in range(n):
        out.append((x, band[1], x + w, band[3]))
        x += w + gap
    return out


def _screen_grab(box):
    """BitBlt a screen rect into an RGB PIL image (fast; ImageGrab is 3x slower)."""
    x, y, x1, y1 = box
    w, h = max(1, x1 - x), max(1, y1 - y)
    screen = u32.GetDC(None)
    mem = gdi.CreateCompatibleDC(screen)
    hbmp = gdi.CreateCompatibleBitmap(screen, w, h)
    old = gdi.SelectObject(mem, hbmp)
    gdi.BitBlt(mem, 0, 0, w, h, screen, x, y, SRCCOPY)
    gdi.SelectObject(mem, old)
    bmi = BITMAPINFO()
    bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bmi.bmiHeader.biWidth = w
    bmi.bmiHeader.biHeight = -h
    bmi.bmiHeader.biPlanes = 1
    bmi.bmiHeader.biBitCount = 32
    buf = ctypes.create_string_buffer(w * h * 4)
    gdi.GetDIBits(mem, hbmp, 0, h, buf, ctypes.byref(bmi), 0)
    gdi.DeleteObject(hbmp)
    gdi.DeleteDC(mem)
    u32.ReleaseDC(None, screen)
    return Image.frombuffer("RGBA", (w, h), buf.raw, "raw", "BGRA", 0, 1).convert("RGB")


def key_icon(crop, light_theme=True):
    """Turn a captured 16px tab icon into RGBA: knock the tab background out by colour
    distance from the corners, so glyph icons sit on our light tab without a dark box.

    A white glyph captured off Chromium's dark tab would be invisible on a light tab, so
    low-saturation pixels get recoloured to the theme's text colour (alpha is kept)."""
    rgb = crop.convert("RGB")
    w, h = rgb.size
    corners = [rgb.getpixel(p) for p in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1),
                                         (w // 2, 0), (w // 2, h - 1))]
    bg = tuple(sorted(c[i] for c in corners)[len(corners) // 2] for i in range(3))
    diff = ImageChops.difference(rgb, Image.new("RGB", (w, h), bg)).convert("L")
    alpha = diff.point(lambda v: 0 if v <= 12 else min(255, (v - 12) * 9))
    if alpha.getextrema()[1] < 40:          # nothing but background -> caller falls back
        return None
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, w - 1, h - 1], radius=max(2, w // 6), fill=255)
    alpha = ImageChops.multiply(alpha, mask)
    out = rgb.convert("RGBA")
    out.putalpha(alpha)
    # recolour monochrome glyphs so they read on our tab colour
    src = out.load()
    dark_ink, light_ink = (64, 68, 76), (226, 231, 238)
    for y in range(h):
        for x in range(w):
            r, g, b, al = src[x, y]
            if al < 30:
                continue
            if max(r, g, b) - min(r, g, b) > 48:      # coloured site icon: leave it alone
                continue
            lum = 0.299 * r + 0.587 * g + 0.114 * b
            if light_theme and lum > 105:
                src[x, y] = (*dark_ink, al)
            elif not light_theme and lum < 120:
                src[x, y] = (*light_ink, al)
    return out


class Favicons:
    """Real tab icons, grabbed from the browser itself.

    The strip is cut out of the window and PrintWindow honours SetWindowRgn (the hole comes
    back black), so a capture means: clear the region, print the D3D child, restore. To keep
    that invisible the overlay first freezes the current screen (glass included) as an opaque
    frame, so the native bar never shows through for the ~80 ms the region is cleared.
    """

    def __init__(self, target, scale, cfg):
        self.target = target
        self.scale = scale
        self.cfg = cfg
        self.cache = {}
        self.miss = {}          # title -> time of last failed capture
        self.child = None
        u32.EnumChildWindows.argtypes = [wt.HWND, ctypes.c_void_p, wt.LPARAM]
        u32.PrintWindow.argtypes = [wt.HWND, wt.HDC, wt.UINT]
        u32.PrintWindow.restype = wt.BOOL

    def _dx3_child(self):
        if self.child and u32.IsWindow(self.child):
            return self.child
        self.child = d3d_child(self.target)
        return self.child

    def _print(self, h):
        r = window_rect(h)
        w, hh = r[2] - r[0], r[3] - r[1]
        screen = u32.GetDC(None)
        mem = gdi.CreateCompatibleDC(screen)
        bmi = BITMAPINFO()
        bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bmi.bmiHeader.biWidth = w
        bmi.bmiHeader.biHeight = -hh
        bmi.bmiHeader.biPlanes = 1
        bmi.bmiHeader.biBitCount = 32
        bits = ctypes.c_void_p()
        hbmp = gdi.CreateDIBSection(mem, ctypes.byref(bmi), 0, ctypes.byref(bits), None, 0)
        old = gdi.SelectObject(mem, hbmp)
        ok = u32.PrintWindow(h, mem, 2)          # PW_RENDERFULLCONTENT
        data = ctypes.string_at(bits, w * hh * 4)
        gdi.SelectObject(mem, old)
        gdi.DeleteObject(hbmp)
        gdi.DeleteDC(mem)
        u32.ReleaseDC(None, screen)
        if not ok:
            return None
        return Image.frombuffer("RGBA", (w, hh), data, "raw", "BGRA", 0, 1), r

    def missing(self, snap):
        now = time.time()
        want = []
        for t in snap.tabs:
            k = _stable(t["name"])
            if k in self.cache or (k in self.miss and now - self.miss[k] < 20):
                continue
            want.append(t)
        return want

    def capture(self, snap, overlay, hole, win):
        """One capture round for the tabs whose icon we do not know yet."""
        want = self.missing(snap)
        child = self._dx3_child()
        if not want or not child or not hole:
            return False
        box = (hole[0], hole[1], hole[2], hole[3])
        overlay.freeze(box)                     # hide the native bar we are about to expose
        u32.SetWindowRgn(self.target, None, True)
        if child:
            u32.SetWindowRgn(child, None, True)
        u32.RedrawWindow(self.target, None, None, 0x0001 | 0x0080 | 0x0100)
        got = None
        try:
            got = self._print(child)
        finally:
            rgn = clip_region(win, hole)
            if rgn:
                u32.SetWindowRgn(self.target, rgn, True)
            if child:
                crgn = child_cut_region(child, hole)
                if crgn:
                    u32.SetWindowRgn(child, crgn, True)
        if not got:
            return False
        cap, cr = got
        s = int(16 * self.scale)
        H = hole[3] - hole[1]
        cy = hole[1] + (H - s) // 2
        for t in want:
            k = _stable(t["name"])
            x0 = t["rect"][0] + int(8 * self.scale)
            lx, ly = x0 - cr[0], cy - cr[1]
            if lx < 0 or ly < 0 or lx + s > cap.size[0] or ly + s > cap.size[1]:
                self.miss[k] = time.time()
                continue
            icon = key_icon(cap.crop((lx, ly, lx + s, ly + s)), light_theme=(self.cfg.theme == "light"))
            if icon is None:
                self.miss[k] = time.time()
            else:
                self.cache[k] = icon
                dbg(f"favicon {k[:24]}")
        return True


# ------------------------------------------------------------------ painting
class Theme:
    """Colours for the redrawn bar. 'light' = light active tabs on dark glass (Win7 look)."""

    def __init__(self, light=True):
        self.light = light
        if light:
            self.tab_active_top = (252, 252, 253, 236)
            self.tab_active_bot = (232, 236, 240, 226)
            self.tab_fill_top = (255, 255, 255, 46)
            self.tab_fill_bot = (255, 255, 255, 26)
            self.tab_hover_top = (255, 255, 255, 96)
            self.tab_hover_bot = (255, 255, 255, 60)
            self.tab_edge = (255, 255, 255, 60)
            self.text_active = (34, 38, 44, 255)
            self.text_dim = (226, 232, 238, 240)
            self.close_active = (96, 104, 114, 255)
            self.close_dim = (226, 232, 238, 210)
            self.btn_glyph = (246, 249, 252, 255)
            self.btn_fill_top = (250, 252, 255, 238)
            self.btn_fill_bot = (222, 228, 236, 230)
            self.btn_edge = (255, 255, 255, 160)
            self.plus = (240, 245, 250, 225)
        else:
            self.tab_active_top = (74, 82, 94, 232)
            self.tab_active_bot = (52, 58, 68, 224)
            self.tab_fill_top = (24, 28, 36, 90)
            self.tab_fill_bot = (18, 22, 28, 70)
            self.tab_hover_top = (60, 68, 80, 150)
            self.tab_hover_bot = (44, 50, 60, 130)
            self.tab_edge = (255, 255, 255, 40)
            self.text_active = (250, 252, 255, 255)
            self.text_dim = (200, 208, 218, 235)
            self.close_active = (232, 238, 244, 240)
            self.close_dim = (196, 204, 214, 200)
            self.btn_glyph = (240, 244, 248, 255)
            self.btn_fill_top = (255, 255, 255, 40)
            self.btn_fill_bot = (255, 255, 255, 12)
            self.btn_edge = (255, 255, 255, 70)
            self.plus = (226, 232, 240, 190)


GLYPH_MIN = [[(0.34, 0.56), (0.66, 0.56)]]
GLYPH_CHEVRON = [[(0.24, 0.36), (0.5, 0.66), (0.76, 0.36)]]
GLYPH_MAX = [[(0.34, 0.36), (0.64, 0.36), (0.64, 0.64), (0.34, 0.64), (0.34, 0.36)]]
GLYPH_CLOSE = [[(0.33, 0.33), (0.67, 0.67)], [(0.67, 0.33), (0.33, 0.67)]]
GLYPH_PLUS = [[(0.5, 0.32), (0.5, 0.68)], [(0.32, 0.5), (0.68, 0.5)]]


def load_font(size):
    for name in ("segoeui.ttf", "segoeuib.ttf", "arial.ttf"):
        try:
            return ImageFont.truetype(os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", name), size)
        except Exception:
            continue
    return ImageFont.load_default()


def poly_glyph(draw, rect, polylines, color, width):
    """Draw one or more polylines scaled into rect."""
    x0, y0, x1, y1 = rect
    w, h = x1 - x0, y1 - y0
    for line in polylines:
        draw.line([(x0 + px * w, y0 + py * h) for px, py in line],
                  fill=color, width=width, joint="curve")


_GRAD_CACHE = {}
_MASK_CACHE = {}


def _grad_strip(h, top, bot):
    key = (h, top, bot)
    g = _GRAD_CACHE.get(key)
    if g is None:
        g = Image.new("RGBA", (1, h))
        gd = ImageDraw.Draw(g)
        for i in range(h):
            k = i / max(1, h - 1)
            gd.point((0, i), fill=tuple(int(top[j] + (bot[j] - top[j]) * k) for j in range(4)))
        _GRAD_CACHE[key] = g
    return g


def _round_mask(w, h, radius, corners):
    key = (w, h, radius, corners)
    m = _MASK_CACHE.get(key)
    if m is None:
        m = Image.new("L", (w, h), 0)
        md = ImageDraw.Draw(m)
        if radius and corners == "top":
            md.rounded_rectangle([0, 0, w - 1, h - 1 + radius], radius=radius, fill=255)
        elif radius:
            md.rounded_rectangle([0, 0, w - 1, h - 1], radius=radius, fill=255)
        else:
            md.rectangle([0, 0, w - 1, h - 1], fill=255)
        _MASK_CACHE[key] = m
    return m


def vgrad(img, box, top, bot, radius=0, corners="all"):
    """Paint a vertical gradient into box, optionally clipped to rounded corners (cached)."""
    x0, y0, x1, y1 = (int(v) for v in box)
    w, h = x1 - x0, y1 - y0
    if w <= 0 or h <= 0:
        return
    grad = _grad_strip(h, top, bot).resize((w, h), Image.Resampling.NEAREST)
    img.paste(grad, (x0, y0), _round_mask(w, h, radius, corners))


def fit_text(font, text, max_w):
    """Truncate with an ellipsis to max_w px (Pillow's own `length` is ignored with anchor)."""
    if max_w <= 0:
        return ""
    try:
        if font.getlength(text) <= max_w:
            return text
    except Exception:
        return text
    ell = "\u2026"
    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        try:
            fits = font.getlength(text[:mid] + ell) <= max_w
        except Exception:
            fits = True
        if fits:
            lo = mid
        else:
            hi = mid - 1
    return text[:lo] + ell


def render(snap, theme, dpi_scale, layout=None, favicons=None, cfg=None, hover=None):
    """Compose the bar body (NOT premultiplied) plus its hit table.

    layout:   per-tab screen rects from layout_tabs(); None -> the raw UIA rects.
    favicons: Favicons instance (cache keyed by stable tab title) or None.
    hover:    ("tab", i) / ("closetab", i) / ("newtab", None) / ("search", None) or None.
    """
    wx0, wy0, wx1, wy1 = snap.win
    band = snap.band
    W = max(1, wx1 - wx0)
    H = max(1, band[3] - band[1])
    img = Image.new("RGBA", (W, H), (0, 0, 0, 1))     # alpha 1: invisible but clickable
    d = ImageDraw.Draw(img)
    font = load_font(max(11, int(12 * dpi_scale)))
    hit = []
    r_tab = max(4, int((cfg.tab_radius if cfg else 6) * dpi_scale))
    gap = max(1, int(1 * dpi_scale))
    inner = max(2, int(7 * dpi_scale))
    close_w = int(22 * dpi_scale)
    icon_s = int(16 * dpi_scale)
    hover_on = bool(cfg.hover) if cfg else True
    bottom = max(1, int(1 * dpi_scale))

    def local(r):
        return (r[0] - wx0, r[1] - band[1], r[2] - wx0, r[3] - band[1])

    n = len(snap.tabs)
    rects = layout if layout and len(layout) == n else [t["rect"] for t in snap.tabs]
    for i, t in enumerate(snap.tabs):
        x0, y0, x1, y1 = local(rects[i])
        box = (x0 + gap, y0, x1 - gap, y1 - bottom)
        hot = hover_on and hover == ("tab", i) and not t["selected"]
        if t["selected"]:
            vgrad(img, box, theme.tab_active_top, theme.tab_active_bot, r_tab, "top")
        elif hot:
            vgrad(img, box, theme.tab_hover_top, theme.tab_hover_bot, r_tab, "top")
        else:
            vgrad(img, box, theme.tab_fill_top, theme.tab_fill_bot, r_tab, "top")
        # 1px seam between tabs
        if i + 1 < n:
            d.line([(x1 - gap, y0 + r_tab // 2), (x1 - gap, box[3])], fill=theme.tab_edge, width=1)
        cy = (box[1] + box[3]) // 2 + int(1 * dpi_scale)

        fx = box[0] + inner
        icon = favicons.cache.get(_stable(t["name"])) if favicons else None
        if icon is not None:
            if icon.size != (icon_s, icon_s):
                icon = icon.resize((icon_s, icon_s), Image.Resampling.LANCZOS)
            img.paste(icon, (fx, cy - icon_s // 2), icon)
            tx = fx + icon_s + int(5 * dpi_scale)
        else:
            dot = max(3, int(4 * dpi_scale))
            d.ellipse([fx, cy - dot, fx + 2 * dot, cy + dot],
                      fill=(120, 180, 235, 235) if t["selected"] else (230, 238, 246, 120))
            tx = fx + 2 * dot + int(6 * dpi_scale)

        max_w = (box[2] - close_w - int(4 * dpi_scale)) - tx
        d.text((tx, cy), fit_text(font, t["name"], max_w), font=font, anchor="lm",
               fill=theme.text_active if t["selected"] else theme.text_dim)

        gx = box[2] - close_w
        close_hot = hover_on and hover == ("closetab", i)
        poly_glyph(d, (gx + int(6 * dpi_scale), cy - int(6 * dpi_scale),
                       gx + close_w - int(6 * dpi_scale), cy + int(6 * dpi_scale)),
                   GLYPH_CLOSE,
                   theme.close_active if (t["selected"] or close_hot) else theme.close_dim,
                   max(1, int(1.1 * dpi_scale)))
        hit.append((rects[i], ("tab", t)))
        hit.append(((rects[i][2] - close_w - 2, rects[i][1] + 4,
                     rects[i][2] - 6, rects[i][3] - 4), ("closetab", t)))

    # tab-search chevron on the left (Chromium draws one; ours is cut away with the strip)
    if snap.search_r:
        r = snap.search_r
        x0, y0, x1, y1 = local(r)
        if hover_on and hover == ("search", None):
            vgrad(img, (x0 + gap, y0, x1 - gap, y1 - bottom),
                  theme.tab_hover_top, theme.tab_hover_bot, r_tab, "top")
        cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
        s = int(6 * dpi_scale)
        poly_glyph(d, (cx - s, cy - s, cx + s, cy + s), GLYPH_CHEVRON,
                   theme.plus, max(1, int(1.4 * dpi_scale)))
        hit.append((r, ("search", None)))

    # new tab button: just a plus on the glass
    if snap.newtab_r:
        x0, y0, x1, y1 = local(snap.newtab_r)
        if hover_on and hover == ("newtab", None):
            vgrad(img, (x0 + gap, y0, x1 - gap, y1 - bottom),
                  theme.tab_hover_top, theme.tab_hover_bot, r_tab, "top")
        cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
        s = int(6 * dpi_scale)
        poly_glyph(d, (cx - s, cy - s, cx + s, cy + s), GLYPH_PLUS,
                   theme.plus, max(1, int(1.5 * dpi_scale)))
        pad = max(2, int(4 * dpi_scale))
        hit.append(((snap.newtab_r[0] + pad, snap.newtab_r[1] + pad,
                     snap.newtab_r[2] - pad, snap.newtab_r[3] - pad), ("newtab", None)))

    # window buttons stay native (they live in a child window the region cannot cut), but the
    # clicks still have to be routed by us.
    for key, action in (("min_r", "min"), ("max_r", "max"), ("close_r", "close")):
        r = getattr(snap, key)
        if r:
            hit.append((r, (action, None)))
    return img, hit


# ------------------------------------------------------------------ overlay window
class Overlay:
    def __init__(self, target, theme, dpi_scale, cfg=None, favicons=None):
        self.target = target
        self.theme = theme
        self.s = dpi_scale
        self.cfg = cfg or Settings()
        self.fav = favicons
        self.hwnd = None
        self.hit = []
        self.hover = None
        self.pending_hover = None      # set by the hook thread, consumed by the paint loop
        self.layout = []
        self.newtab_rect = None
        self.search_rect = None
        self.band_off = None
        self.band = None
        self.dragging = False
        self.down = (0, 0)
        self.down_rect = (0, 0, 0, 0)
        self.last_click = (0.0, (0, 0))
        self._proc = WNDPROC(self._wndproc)

    def create(self):
        inst = k32.GetModuleHandleW(None)
        wc = WNDCLASS()
        wc.lpfnWndProc = self._proc
        wc.hInstance = inst
        wc.lpszClassName = "GlassTitlebarOverlay"
        wc.hCursor = u32.LoadCursorW(None, 32512)
        if not u32.RegisterClassW(ctypes.byref(wc)) and ctypes.GetLastError() != 1410:
            raise ctypes.WinError(ctypes.GetLastError())
        ex = WS_EX_TOOLWINDOW | WS_EX_LAYERED | WS_EX_NOACTIVATE
        h = u32.CreateWindowExW(ex, "GlassTitlebarOverlay", "", WS_POPUP,
                                -20000, -20000, 10, 10, None, None, inst, None)
        if not h:
            raise ctypes.WinError(ctypes.GetLastError())
        self.hwnd = h
        return h

    # -------------------------------------------------- painting
    def paint(self, snap, hover=None, force=False):
        band = snap.band
        if not band:
            u32.ShowWindow(self.hwnd, 0)
            return
        hover = hover if self.cfg.hover else None
        layout = layout_tabs(snap, self.s, self.cfg)
        img, hit = render(snap, self.theme, self.s, layout, self.fav, self.cfg, hover)
        self.hit = hit
        self.layout = layout
        self.hover = hover
        self.newtab_rect = snap.newtab_r
        self.search_rect = snap.search_r
        self.band = band
        self.band_off = (band[1] - snap.win[1], band[3] - band[1])
        self._blit(img, band[0], band[1])
        dbg(f"painted {img.size[0]}x{img.size[1]} at {band[0]},{band[1]} tabs={len(snap.tabs)} "
            f"layout={layout[:1]} band={band} hover={hover}")

    def freeze(self, box):
        """Freeze what the band looks like right now as an opaque frame.

        The favicon capture has to clear the window region for ~80 ms. Without this the
        browser's own dark tab strip would show through the semi-transparent parts of our
        bar for a few frames; with it the user sees no change at all.
        """
        try:
            shot = _screen_grab(box).convert("RGBA")
        except Exception as e:
            dbg(f"freeze failed {e!r}")
            return
        self._blit(shot, box[0], box[1])

    def _blit(self, img, x, y):
        w, h = img.size
        a = img.getchannel("A")
        pre = ImageChops.multiply(img.convert("RGB"), a.convert("RGB"))
        flat = Image.merge("RGBA", (*pre.split(), a))
        screen = u32.GetDC(None)
        mem = gdi.CreateCompatibleDC(screen)
        bmi = BITMAPINFO()
        bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bmi.bmiHeader.biWidth = w
        bmi.bmiHeader.biHeight = -h            # top-down
        bmi.bmiHeader.biPlanes = 1
        bmi.bmiHeader.biBitCount = 32
        bmi.bmiHeader.biCompression = 0        # BI_RGB
        bits = ctypes.c_void_p()
        hbmp = gdi.CreateDIBSection(mem, ctypes.byref(bmi), 0, ctypes.byref(bits), None, 0)
        old = gdi.SelectObject(mem, hbmp)
        data = flat.tobytes("raw", "BGRA")
        ctypes.memmove(bits, data, len(data))
        blend = BLENDFUNCTION(AC_SRC_OVER, 0, 255, AC_SRC_ALPHA)
        dst = POINT(x, y)
        size = SIZE(w, h)
        src = POINT(0, 0)
        ok = u32.UpdateLayeredWindow(self.hwnd, screen, ctypes.byref(dst), ctypes.byref(size),
                                     mem, ctypes.byref(src), 0, ctypes.byref(blend), ULW_ALPHA)
        gdi.SelectObject(mem, old)
        gdi.DeleteObject(hbmp)
        gdi.DeleteDC(mem)
        u32.ReleaseDC(None, screen)
        u32.SetWindowPos(self.hwnd, 0, x, y, w, h, SWP_NOACTIVATE)
        u32.ShowWindow(self.hwnd, 4)
        self.raise_above()
        if DEBUG:
            rr = RECT()
            u32.GetWindowRect(self.hwnd, ctypes.byref(rr))
            dbg(f"winrect now {(rr.left, rr.top, rr.right, rr.bottom)}")
        if os.environ.get("GLASS_TITLEBAR_DUMP") == "1":
            try:
                img.save(os.path.join(os.environ.get("TEMP", "."), "gt_last.png"))
            except Exception:
                pass
        return ok

    def hover_at(self, x, y):
        """Which drawn control is under the cursor (cheap: a handful of rects)."""
        for i, r in enumerate(self.layout):
            if r[0] <= x < r[2] and r[1] <= y < r[3]:
                if x >= r[2] - int(22 * self.s) - 2:
                    return ("closetab", i)
                return ("tab", i)
        for r, action in ((self.newtab_rect, ("newtab", None)),
                          (self.search_rect, ("search", None))):
            if r and r[0] <= x < r[2] and r[1] <= y < r[3]:
                return action
        return None

    # -------------------------------------------------- input
    def raise_above(self):
        """Keep the overlay directly above the browser window in the Z order."""
        if not self.hwnd or not self.target:
            return
        prev = u32.GetWindow(self.target, 3)      # GW_HWNDPREV
        if prev == self.hwnd:
            return
        u32.SetWindowPos(self.hwnd, prev or 0, 0, 0, 0, 0,
                         SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)

    def hit_test(self, x, y):
        for rect, action in reversed(self.hit):
            if rect[0] <= x < rect[2] and rect[1] <= y < rect[3]:
                return action
        return None

    def _wndproc(self, h, msg, wp, lp):
        t = self.target
        if msg == 0x0084:                      # WM_NCHITTEST
            return 1
        if msg == 0x0021:                      # WM_MOUSEACTIVATE
            return MA_NOACTIVATE
        if msg == 0x0201:                      # WM_LBUTTONDOWN
            x = ctypes.c_short(lp & 0xFFFF).value
            y = ctypes.c_short((lp >> 16) & 0xFFFF).value
            p = POINT(x, y)
            u32.ClientToScreen(h, ctypes.byref(p))
            action = self.hit_test(p.x, p.y)
            dbg(f"click {p.x},{p.y} -> {action[0] if action else 'background'}")
            if action:
                kind, tab = action
                if kind == "tab":
                    self._select_tab(tab)
                elif kind == "closetab":
                    self._close_tab(tab)
                elif kind == "newtab":
                    self._send_key(t, 0x11, 0x54)      # Ctrl+T
                elif kind == "search":
                    self._send_key(t, (0x11, 0x10), 0x41)   # Ctrl+Shift+A
                elif kind in ("min", "max", "close"):
                    self._window_button(kind)
                return 1
            # background: drag the window
            if u32.GetWindowLongW(t, GWL_STYLE) & WS_MAXIMIZE:
                return 1
            self.dragging = True
            self.down = (p.x, p.y)
            self.down_rect = window_rect(t)
            return 1
        if msg == 0x0200 and self.dragging:              # WM_MOUSEMOVE
            p = POINT()
            u32.GetCursorPos(ctypes.byref(p))
            dx, dy = p.x - self.down[0], p.y - self.down[1]
            x0, y0, x1, y1 = self.down_rect
            u32.SetWindowPos(t, 0, x0 + dx, y0 + dy, x1 - x0, y1 - y0,
                             SWP_NOZORDER | SWP_NOACTIVATE)
            return 1
        if msg == 0x0202:                                # WM_LBUTTONUP
            if self.dragging:
                self.dragging = False
                p = POINT()
                u32.GetCursorPos(ctypes.byref(p))
                moved = abs(p.x - self.down[0]) + abs(p.y - self.down[1])
                if moved <= 3:
                    now = time.time()
                    lt, lp_ = self.last_click
                    if now - lt <= u32.GetDoubleClickTime() / 1000 and \
                            abs(p.x - lp_[0]) <= 4 and abs(p.y - lp_[1]) <= 4:
                        if u32.GetWindowLongW(t, GWL_STYLE) & WS_MAXIMIZE:
                            u32.ShowWindow(t, SW_RESTORE)
                        else:
                            u32.ShowWindow(t, SW_MAXIMIZE)
                        self.last_click = (0.0, (0, 0))
                        dbg("dblclick maximize")
                    else:
                        self.last_click = (now, (p.x, p.y))
                return 1
        return u32.DefWindowProcW(h, msg, wp, lp)

    # -------------------------------------------------- actions
    @staticmethod
    def _select_tab(tab):
        try:
            p = tab["el"].GetCurrentPattern(SEL)
            p.QueryInterface(UIA.IUIAutomationSelectionItemPattern).Select()
            dbg(f"select {tab['name'][:20]}")
        except Exception as e:
            dbg(f"select failed {e!r}")

    @staticmethod
    def _close_tab(tab):
        try:
            el = tab.get("close_el")
            if el:
                el.GetCurrentPattern(INV).QueryInterface(UIA.IUIAutomationInvokePattern).Invoke()
                dbg(f"close {tab['name'][:20]}")
        except Exception as e:
            dbg(f"close failed {e!r}")

    def _window_button(self, kind):
        t = self.target
        if not t:
            return
        if kind == "min":
            u32.PostMessageW(t, WM_SYSCOMMAND, SC_MINIMIZE, 0)
        elif kind == "max":
            if u32.GetWindowLongW(t, GWL_STYLE) & WS_MAXIMIZE:
                u32.PostMessageW(t, WM_SYSCOMMAND, SC_RESTORE, 0)
            else:
                u32.PostMessageW(t, WM_SYSCOMMAND, SC_MAXIMIZE, 0)
        else:
            u32.PostMessageW(t, WM_SYSCOMMAND, SC_CLOSE, 0)
        dbg(f"window button {kind}")

    @staticmethod
    def _send_key(t, mod, key):
        """mod may be a single VK or a tuple/list of them (all held for the key press)."""
        mods = list(mod) if isinstance(mod, (tuple, list)) else [mod]
        u32.SetForegroundWindow(t)
        time.sleep(0.02)
        dbg(f"sendkey mods={mods} key={key:#x} fg={u32.GetForegroundWindow():#x} target={t:#x}")
        for m in mods:
            u32.keybd_event(m, 0, 0, 0)
        u32.keybd_event(key, 0, 0, 0)
        u32.keybd_event(key, 0, 2, 0)
        for m in reversed(mods):
            u32.keybd_event(m, 0, 2, 0)


# ------------------------------------------------------------------ input hook
def force_foreground(h):
    """SetForegroundWindow from a background process needs a thread-input attach."""
    if not h or not u32.IsWindow(h):
        return
    if u32.GetForegroundWindow() == h:
        return
    fg = u32.GetForegroundWindow()
    me = k32.GetCurrentThreadId()
    other = u32.GetWindowThreadProcessId(fg, None) if fg else 0
    attached = False
    if other and other != me:
        attached = bool(u32.AttachThreadInput(me, other, True))
    try:
        u32.BringWindowToTop(h)
        u32.SetForegroundWindow(h)
        u32.SetFocus(h)
    finally:
        if attached:
            u32.AttachThreadInput(me, other, False)


class InputHook:
    """Low-level mouse hook for the bar area.

    A layered window with alpha~0 is click-through (DWM hit-tests per pixel), so the overlay
    cannot receive the clicks itself. The hook swallows every click inside the bar and routes
    it to the overlay's hit map, which also keeps the desktop from seeing those clicks.
    """

    def __init__(self, target, overlay):
        self.target = target
        self.overlay = overlay
        self.band = None
        self.lock = threading.Lock()
        self.hook = None
        self.q = queue.Queue()
        self.stop_flag = False
        self.active = False
        self.tid = 0
        self.last_event_ts = 0.0
        self.dragging = False
        self.down_pt = (0, 0)
        self.down_rect = (0, 0, 0, 0)
        self.hover = None
        self.hover_rect = None
        self.last_click = (0.0, (0, 0))
        self._proc = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, ctypes.c_int, wt.WPARAM, wt.LPARAM)(self._hook)

    def _drag_loop(self):
        """SetCursorPos-driven (injected) moves never reach a LL hook, so poll instead."""
        while not self.stop_flag:
            if self.dragging:
                p = POINT()
                u32.GetCursorPos(ctypes.byref(p))
                dx, dy = p.x - self.down_pt[0], p.y - self.down_pt[1]
                x0, y0, x1, y1 = self.down_rect
                u32.SetWindowPos(self.target, 0, x0 + dx, y0 + dy, x1 - x0, y1 - y0,
                                 SWP_NOZORDER | SWP_NOACTIVATE)
            time.sleep(0.012)

    def _drain(self):
        """UIA calls must not run inside a low-level hook (Windows drops slow hooks)."""
        while True:
            item = self.q.get()
            if item is None:
                return
            kind, tab = item
            try:
                if kind == "activate":
                    force_foreground(self.target)
                elif kind == "tab":
                    self.overlay._select_tab(tab)
                elif kind == "closetab":
                    self.overlay._close_tab(tab)
                elif kind == "newtab":
                    self.overlay._send_key(self.target, 0x11, 0x54)
                elif kind == "search":
                    self.overlay._send_key(self.target, (0x11, 0x10), 0x41)   # Ctrl+Shift+A
                elif kind == "nexttabs":
                    self.overlay._send_key(self.target, 0x11, 0x09)           # Ctrl+Tab
                elif kind == "prevtabs":
                    self.overlay._send_key(self.target, (0x11, 0x10), 0x09)   # Ctrl+Shift+Tab
                elif kind in ("min", "max", "close"):
                    self.overlay._window_button(kind)
            except Exception as e:
                dbg(f"action error {e!r}")

    def set_band(self, band):
        with self.lock:
            self.active = band is not None
            self.hover_rect = band

    def _hover_track(self, x, y):
        """Cheap hover bookkeeping. Runs inside the LL hook, so: no UIA, no drawing, no paint
        -- it only records the target and lets the main loop repaint."""
        hb = self.hover_rect
        if hb and hb[0] <= x < hb[2] and hb[1] <= y < hb[3]:
            hv = self.overlay.hover_at(x, y)
        else:
            hv = None
        if hv != self.hover:
            self.hover = hv
            self.overlay.pending_hover = hv

    def in_band(self, x, y):
        """Live geometry: the cached band goes stale the moment the window moves."""
        if not self.active:
            return False
        t = self.target
        off = self.overlay.band_off
        if not t or not off or not u32.IsWindow(t):
            return False
        r = window_rect(t)
        y0 = r[1] + off[0]
        y1 = y0 + off[1]
        pad = 2
        return r[0] <= x < r[2] and (y0 - pad) <= y < (y1 + pad)

    def _hook(self, code, wparam, lparam):
        self.last_event_ts = time.time()
        if code < 0:
            return u32.CallNextHookEx(None, code, wparam, lparam)
        try:
            info = ctypes.cast(lparam, ctypes.POINTER(MSLLHOOKSTRUCT)).contents
            if info.flags & LLMHF_INJECTED and os.environ.get("GLASS_TITLEBAR_IGNORE_INJECTED") == "1":
                return u32.CallNextHookEx(None, code, wparam, lparam)
            x, y = info.pt.x, info.pt.y
            msg = wparam & 0xFFFFFFFF
            t = self.target

            # Mouse moves are by far the most frequent event: handle the drag case, keep hover
            # cheap, and get out.
            if msg == WM_MOUSEMOVE:
                if self.dragging:
                    dx, dy = x - self.down_pt[0], y - self.down_pt[1]
                    x0, y0, x1, y1 = self.down_rect
                    u32.SetWindowPos(t, 0, x0 + dx, y0 + dy, x1 - x0, y1 - y0,
                                     SWP_NOZORDER | SWP_NOACTIVATE)
                    return 1
                try:
                    self._hover_track(x, y)
                except Exception:
                    pass
                return u32.CallNextHookEx(None, code, wparam, lparam)

            live = bool(t) and u32.IsWindow(t)
            if live:
                p = POINT(x, y)
                under = u32.WindowFromPoint(p)
                root = u32.GetAncestor(under, 2) if under else 0
                live = root == t or root == u32.GetDesktopWindow() or root == self.overlay.hwnd
            if not live:
                return u32.CallNextHookEx(None, code, wparam, lparam)

            if msg == WM_LBUTTONDOWN:
                if not self.in_band(x, y):
                    return u32.CallNextHookEx(None, code, wparam, lparam)
                if u32.GetForegroundWindow() != t:
                    self.q.put(("activate", None))     # never block the hook on SetForegroundWindow
                action = self.overlay.hit_test(x, y)
                dbg(f"click {x},{y} -> {action[0] if action else 'background'}")
                if action:
                    # Nothing that can block (UIA, SetForegroundWindow, keybd_event) may run
                    # in a low-level hook: it gets skipped or silently uninstalled when slow.
                    self.q.put(action)
                    return 1
                if u32.GetWindowLongW(t, GWL_STYLE) & WS_MAXIMIZE:
                    return 1
                self.dragging = True
                self.down_pt = (x, y)
                self.down_rect = window_rect(t)
                dbg(f"drag start {x},{y} rect={self.down_rect}")
                if u32.GetForegroundWindow() != t:
                    self.q.put(("activate", None))
                return 1

            if msg == WM_LBUTTONUP:
                if self.dragging:
                    self.dragging = False
                    moved = abs(x - self.down_pt[0]) + abs(y - self.down_pt[1])
                    dbg(f"drag end moved={moved}")
                    if moved <= 3:
                        now = time.time()
                        lt, lp_ = self.last_click
                        if (now - lt) <= u32.GetDoubleClickTime() / 1000.0 and \
                                abs(x - lp_[0]) <= 4 and abs(y - lp_[1]) <= 4:
                            if u32.GetWindowLongW(t, GWL_STYLE) & WS_MAXIMIZE:
                                u32.ShowWindow(t, SW_RESTORE)
                            else:
                                u32.ShowWindow(t, SW_MAXIMIZE)
                            self.q.put(("activate", None))
                            self.last_click = (0.0, (0, 0))
                            dbg("double click -> toggle maximize")
                        else:
                            self.last_click = (now, (x, y))
                    return 1
                if self.in_band(x, y):
                    return 1                                     # a click on a drawn control

            if msg == WM_MOUSEWHEEL and self.in_band(x, y):
                if self.overlay.cfg.wheel_tabs:
                    up = ctypes.c_short((info.mouseData >> 16) & 0xFFFF).value > 0
                    dbg(f"wheel {'up' if up else 'down'} at {x},{y} -> {'prevtabs' if up else 'nexttabs'}")
                    self.q.put(("prevtabs" if up else "nexttabs", None))
                    return 1
                return u32.CallNextHookEx(None, code, wparam, lparam)

            if msg in (WM_RBUTTONDOWN, WM_RBUTTONUP, WM_MBUTTONDOWN, WM_MBUTTONUP) and self.in_band(x, y):
                dbg(f"swallowed button msg {msg}")
                return 1
        except Exception as e:
            dbg(f"hook error {e!r}")
        return u32.CallNextHookEx(None, code, wparam, lparam)

    def start(self):
        threading.Thread(target=self._drain, daemon=True).start()
        threading.Thread(target=self._drag_loop, daemon=True).start()
        threading.Thread(target=self._watch, daemon=True).start()
        threading.Thread(target=self._run, daemon=True).start()

    def _watch(self):
        """Windows silently drops low-level hooks that time out.

        The cursor keeps moving but no events arrive any more, which looks exactly like
        'clicks pass through the title bar'. Detect it and reinstall the hook.
        """
        last_pos = None
        while not self.stop_flag:
            time.sleep(0.7)
            p = POINT()
            u32.GetCursorPos(ctypes.byref(p))
            pos = (p.x, p.y)
            moved = last_pos is not None and pos != last_pos
            last_pos = pos
            if moved and (time.time() - self.last_event_ts) > 1.2 and self.tid:
                dbg("hook stopped delivering, reinstalling")
                u32.PostThreadMessageW(self.tid, WM_APP + 1, 0, 0)

    def _install(self):
        self.hook = u32.SetWindowsHookExW(WH_MOUSE_LL, ctypes.cast(self._proc, ctypes.c_void_p),
                                         k32.GetModuleHandleW(None), 0)
        self.tid = k32.GetCurrentThreadId()
        self.last_event_ts = time.time()
        dbg(f"input hook {self.hook}")
        return self.hook

    def _run(self):
        k32.SetThreadPriority(k32.GetCurrentThread(), 2)     # THREAD_PRIORITY_HIGHEST
        u32.SetWindowsHookExW.argtypes = [ctypes.c_int, ctypes.c_void_p, wt.HMODULE, wt.DWORD]
        u32.SetWindowsHookExW.restype = wt.HHOOK
        u32.CallNextHookEx.argtypes = [wt.HANDLE, ctypes.c_int, wt.WPARAM, wt.LPARAM]
        u32.CallNextHookEx.restype = ctypes.c_ssize_t
        k32.GetModuleHandleW.restype = wt.HMODULE
        if not self._install():
            print("SetWindowsHookExW failed", ctypes.GetLastError(), flush=True)
            return
        msg = wt.MSG()
        while u32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            if msg.message == WM_APP + 1:
                if self.hook:
                    u32.UnhookWindowsHookEx(self.hook)
                if not self._install():
                    print("hook reinstall failed", ctypes.GetLastError(), flush=True)
                continue
            u32.TranslateMessage(ctypes.byref(msg))
            u32.DispatchMessageW(ctypes.byref(msg))

    def stop(self):
        self.stop_flag = True
        if self.hook:
            u32.UnhookWindowsHookEx(self.hook)
            self.hook = None


class CaptionHook(threading.Thread):
    """Forward clicks in the OpenGlass caption corner to the window.

    That corner is a region *hole* (so OpenGlass paints its Win7 buttons there), which means
    Windows never delivers those clicks to the window -- they fall through to whatever is
    behind it. This hook catches them and posts the matching WM_SYSCOMMAND instead.
    """

    SC = {"min": 0xF020, "max": 0xF030, "restore": 0xF120, "close": 0xF060}

    def __init__(self, target):
        super().__init__(daemon=True, name="caption-hook")
        self.target = target
        self.area = None            # the holed corner, screen coords
        self.buttons = {}           # name -> rect
        self.pending = None
        self.down = False
        self.resizing = None
        self.moving = None
        self.restore_drag = None
        self.native_mode = False
        self._mv = 0
        self._mm = 0
        self.drag_t0 = 0.0
        self.last_click = (0.0, (0, 0))
        self.frame_win = None
        self.frame_n = 0
        self.lock = threading.Lock()
        self.stop_flag = False
        self.hook = None
        self.tid = None
        self._proc = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, ctypes.c_int, wt.WPARAM, wt.LPARAM)(
            self._hook)
        self.q = queue.Queue()
        self.last_event_ts = time.time()
        threading.Thread(target=self._worker, daemon=True, name="caption-worker").start()

    def _worker(self):
        """Foreground activation must not run inside the LL hook: AttachThreadInput /
        SetForegroundWindow can block for hundreds of ms and the system silently unhooks a
        slow low-level hook (that was why selecting/resizing worked only sometimes)."""
        while not self.stop_flag:
            try:
                kind, _ = self.q.get(timeout=0.5)
            except queue.Empty:
                continue
            try:
                if kind == "fg":
                    force_foreground(self.target)
            except Exception as e:
                dbg(f"caption worker error {e!r}")

    def _ask_fg(self):
        self.q.put(("fg", None))

    def set_area(self, area, buttons):
        with self.lock:
            self.area = area
            self.buttons = {k: v for k, v in buttons.items() if v}

    def set_frame(self, win, n):
        """Geometry of the four thin hole strips, so clicks there can resize/activate."""
        with self.lock:
            self.frame_win = win
            self.frame_n = n

    def _edge(self, x, y):
        w, n = self.frame_win, self.frame_n
        if not w or not n or not (w[0] <= x < w[2] and w[1] <= y < w[3]):
            return None
        top, bot = y < w[1] + n, y >= w[3] - n
        left, right = x < w[0] + n, x >= w[2] - n
        if not (top or bot or left or right):
            return None
        if top and left:
            return "tl"
        if top and right:
            return "tr"
        if bot and left:
            return "bl"
        if bot and right:
            return "br"
        return "t" if top else "b" if bot else "l" if left else "r"

    @property
    def busy(self):
        """True while a hand move/resize started by this hook is in flight."""
        return bool(self.native_mode or self.moving or self.resizing or self.restore_drag)

    def _hit(self, x, y):
        a = self.area
        if not a or not (a[0] <= x < a[2] and a[1] <= y < a[3]):
            return None
        for name, r in self.buttons.items():
            if r[0] <= x < r[2] and r[1] <= y < r[3]:
                return name
        return None

    def _hook(self, code, wparam, lparam):
        self.last_event_ts = time.time()
        if code < 0:
            return u32.CallNextHookEx(None, code, wparam, lparam)
        try:
            info = ctypes.cast(lparam, ctypes.POINTER(MSLLHOOKSTRUCT)).contents
            msg = wparam & 0xFFFFFFFF
            x, y = info.pt.x, info.pt.y
            if self.native_mode:
                # Windows owns the drag now (modal move/resize loop): every event must reach
                # it untouched, otherwise the loop sees no movement and snaps back.
                if msg == WM_LBUTTONUP:
                    self.native_mode = False
                    self.down = False
                    self.pending = None
                return u32.CallNextHookEx(None, code, wparam, lparam)
            a = self.area
            inside = bool(a) and a[0] <= x < a[2] and a[1] <= y < a[3]
            if (self.moving or self.resizing) and msg in (WM_LBUTTONDOWN, WM_MOUSEMOVE):
                # A latch must never survive a button-up it never saw (a second hook copy or
                # another app swallowing the click): the window then "snaps back" on every
                # mouse move. A fresh press, or a drag older than 20 s, clears it.
                if msg == WM_LBUTTONDOWN or (time.time() - self.drag_t0) > 20:
                    self.moving = None
                    self.resizing = None
                    self.restore_drag = None
                    self.down = False
                    self.pending = None
            if msg == WM_LBUTTONDOWN:
                trace(f"down {x},{y} inside={inside} area={a} frame={self.frame_win} n={self.frame_n}")
                # The frame strips win over the caption: the top border overlaps the caption
                # band, and treating it as caption made the top edge impossible to resize.
                edge = None if u32.IsZoomed(self.target) else self._edge(x, y)
                if edge:
                    self.resizing = (edge, window_rect(self.target), (x, y))
                    self.drag_t0 = time.time()
                    self.down = True
                    self._ask_fg()
                    trace(f"resize start {edge}")
                    return 1
                if inside:
                    hit = self._hit(x, y)
                    self.pending = hit
                    self.down = True
                    trace(f"hit={self.pending} zoomed={u32.IsZoomed(self.target)}")
                    self._ask_fg()
                    if not hit:
                        if u32.IsZoomed(self.target):
                            # Windows behaviour: dragging a maximised window's caption
                            # restores it and keeps the grab point under the cursor.
                            mr = window_rect(self.target)
                            self.restore_drag = (x, y, mr, (x - mr[0]) / max(1, mr[2] - mr[0]))
                        else:
                            self.moving = (window_rect(self.target), (x, y))
                        self.drag_t0 = time.time()
                    return 1            # never let it reach the desktop behind the hole
            elif msg == WM_MOUSEMOVE and self.restore_drag:
                x0, y0, mr, ratio = self.restore_drag
                if abs(x - x0) + abs(y - y0) > 8:
                    self.restore_drag = None
                    u32.ShowWindow(self.target, 9)          # SW_RESTORE
                    nr = window_rect(self.target)
                    nw = max(1, nr[2] - nr[0])
                    left = x - int(ratio * nw)
                    u32.SetWindowPos(self.target, 0, left, nr[1], 0, 0,
                                     SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE)
                    self.moving = (window_rect(self.target), (x, y))
                    self.drag_t0 = time.time()
                    trace(f"restore-drag from maximized -> {self.moving[0]}")
                return 1
            elif msg == WM_MOUSEMOVE and self.moving:
                r0, (sx, sy) = self.moving
                self._mv += 1
                if self._mv <= 2:
                    dbg(f"mv gask={u32.GetAsyncKeyState(0x01):#010x} mv={self._mv}")
                if self._mv % 10 == 1:
                    trace(f"drag {x},{y} -> {r0[0] + (x - sx)},{r0[1] + (y - sy)}")
                u32.SetWindowPos(self.target, 0, r0[0] + (x - sx), r0[1] + (y - sy), 0, 0,
                                 SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE)
                return 1
            elif msg == WM_MOUSEMOVE and self.resizing:
                edge, r0, (sx, sy) = self.resizing
                l, t, r, b = r0
                dx, dy = x - sx, y - sy
                sc = (u32.GetDpiForWindow(self.target) or 96) / 96.0
                minw = max(480, int(500 * sc))      # Chromium refuses to go below 500 DIP
                minh = max(320, int(200 * sc))
                if "l" in edge:
                    l = min(l + dx, r - minw)
                if "r" in edge:
                    r = max(r + dx, l + minw)
                if "t" in edge:
                    t = min(t + dy, b - minh)
                if "b" in edge:
                    b = max(b + dy, t + minh)
                u32.SetWindowPos(self.target, 0, l, t, r - l, b - t,
                                 SWP_NOZORDER | SWP_NOACTIVATE)
                self._mv += 1
                if self._mv <= 4:
                    trace(f"resize {edge} ({l},{t},{r - l},{b - t}) now={window_rect(self.target)}")
                return 1
            elif msg == WM_LBUTTONUP:
                if self.restore_drag:
                    self.restore_drag = None
                    self.down = False
                    return 1
                if self.moving:
                    r0, (sx, sy) = self.moving
                    self.moving = None
                    self.down = False
                    if abs(x - sx) + abs(y - sy) <= 4:
                        now = time.time()
                        lt, lp_ = self.last_click
                        if ((now - lt) <= u32.GetDoubleClickTime() / 1000.0
                                and abs(x - lp_[0]) <= 4 and abs(y - lp_[1]) <= 4):
                            u32.PostMessageW(self.target, WM_SYSCOMMAND,
                                             0xF120 if u32.IsZoomed(self.target) else 0xF030, 0)
                            trace("caption double click -> toggle maximize")
                            self.last_click = (0.0, (0, 0))
                        else:
                            self.last_click = (now, (x, y))
                    return 1
                if self.resizing:
                    self.resizing = None
                    self.down = False
                    return 1
                self.moving = None
                self.resizing = None
                self.down = False
                if self.pending or inside:
                    name, self.pending = self.pending, None
                    self.down = False
                    if name:
                        if name == "max":
                            name = "restore" if u32.IsZoomed(self.target) else "max"
                        u32.PostMessageW(self.target, WM_SYSCOMMAND, self.SC[name], 0)
                        trace(f"caption click -> {name}")
                    return 1
        except Exception:
            pass
        return u32.CallNextHookEx(None, code, wparam, lparam)

    def _install(self):
        self.hook = u32.SetWindowsHookExW(WH_MOUSE_LL, ctypes.cast(self._proc, ctypes.c_void_p),
                                         k32.GetModuleHandleW(None), 0)
        self.tid = k32.GetCurrentThreadId()
        return self.hook

    def _watch(self):
        """A low-level hook that takes too long gets dropped by Windows without a word; if the
        cursor moves but no events arrive, reinstall it."""
        last = None
        while not self.stop_flag:
            time.sleep(0.7)
            p = POINT()
            u32.GetCursorPos(ctypes.byref(p))
            pos = (p.x, p.y)
            moved = last is not None and pos != last
            last = pos
            if moved and self.tid and (time.time() - self.last_event_ts) > 1.2:
                dbg("caption hook stopped delivering, reinstalling")
                u32.PostThreadMessageW(self.tid, WM_APP + 1, 0, 0)

    def _run(self):
        k32.SetThreadPriority(k32.GetCurrentThread(), 2)
        u32.SetWindowsHookExW.argtypes = [ctypes.c_int, ctypes.c_void_p, wt.HMODULE, wt.DWORD]
        u32.SetWindowsHookExW.restype = wt.HHOOK
        u32.CallNextHookEx.argtypes = [wt.HANDLE, ctypes.c_int, wt.WPARAM, wt.LPARAM]
        u32.CallNextHookEx.restype = ctypes.c_ssize_t
        k32.GetModuleHandleW.restype = wt.HMODULE
        if not self._install():
            print("caption hook failed", ctypes.GetLastError(), flush=True)
            return
        threading.Thread(target=self._watch, daemon=True, name="caption-watch").start()
        msg = wt.MSG()
        while u32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            if msg.message == WM_APP + 1:
                if self.hook:
                    u32.UnhookWindowsHookEx(self.hook)
                    self.hook = None
                self._install()
                continue
            u32.TranslateMessage(ctypes.byref(msg))
            u32.DispatchMessageW(ctypes.byref(msg))

    def run(self):
        self._run()

    def stop(self):
        self.stop_flag = True
        if self.hook:
            u32.UnhookWindowsHookEx(self.hook)
            self.hook = None


# ------------------------------------------------------------ native tab strip mode
# The self-drawn tab bar (layout_tabs / render / Overlay / Favicons) is PARKED, not removed:
# it can only show icons by capturing pixels of the native strip, which is fragile (stray
# backgrounds, DPI changes, sites whose icon does not key out). The product path now keeps
# Chromium's own tab strip and cuts away only the strip BACKGROUND (comb_region), so
# favicons, close buttons, hit-testing and drag-reorder are 100% native. See FINDINGS §11.
NATIVE_TABS = True


def attach_loop(hwnd, cfg, scale, dry_run=False, stop_event=None, log=print):
    """Manage ONE window until it dies or stop_event is set (blocking).

    Split out of main() so the daemon can run several of these in parallel threads.
    """
    draw_tabs = (not NATIVE_TABS) and not dry_run
    worker = UiaWorker(hwnd)
    worker.start()
    fav = None if (not draw_tabs or not cfg.favicons) else Favicons(hwnd, scale, cfg)
    overlay = None if not draw_tabs else Overlay(hwnd, Theme(cfg.theme == "light"), scale, cfg, fav)
    if overlay:
        overlay.create()
    hook = None
    if overlay:
        hook = InputHook(hwnd, overlay)
        hook.start()
    cap = CaptionHook(hwnd) if (not draw_tabs and cfg.gl_buttons) else None
    if cap:
        cap.start()

    applied = None
    child = None
    pending = None
    pend_n = 0
    last_snap = None
    last_snap_t = 0.0
    painted_sig = None
    last_paint = 0.0
    last_cap = 0.0

    def restore_regions():
        """Parent AND D3D child, otherwise the native strip stays clipped (or the hole stays)."""
        if u32.IsWindow(hwnd):
            u32.SetWindowRgn(hwnd, None, True)
        if child and u32.IsWindow(child):
            u32.SetWindowRgn(child, None, True)

    try:
        while not (stop_event and stop_event.is_set()):
            if not u32.IsWindow(hwnd):
                log("window gone")
                break
            if u32.IsIconic(hwnd) or not u32.IsWindowVisible(hwnd):
                if hook:
                    hook.set_band(None)
                if overlay:
                    u32.ShowWindow(overlay.hwnd, 0)
                if applied:
                    trace(f"clear region: iconic/hidden {hwnd:x}")
                    restore_regions()
                    applied = None
                time.sleep(0.2)
                continue

            win = window_rect(hwnd)
            if cap and cap.busy:
                # A hand move/resize is in flight: the region is expressed in window
                # coordinates so it follows the window by itself. Touching it here (or
                # re-reading UIA, which still reports the old rect) is what made the hole
                # blink away mid-drag and the window look like it reset.
                time.sleep(0.05)
                continue
            if is_fullscreen(hwnd, win):
                if applied:
                    restore_regions()
                    applied = None
                    pending, pend_n = None, 0
                    trace(f"clear region: fullscreen {hwnd:x}")
                    log("fullscreen -> region cleared")
                if overlay:
                    u32.ShowWindow(overlay.hwnd, 0)
                if cap:
                    cap.set_area(None, {})
                    cap.set_frame(None, 0)
                time.sleep(0.25)
                continue
            snap = worker.latest()
            if not snap or not snap.band or snap.win != win:
                # A hand-drag moves the window every few ms, so the UIA snapshot is always one
                # step behind. Being strict here cleared the hole and repainted the native
                # frame on every loop while dragging — the window looked like it "reset".
                # A pure move (same size) is handled by shifting the last good snapshot.
                if (last_snap and last_snap.band and (time.time() - last_snap_t) < 10.0):
                    # Size may have changed too (restore-from-maximised, edge drag): the band
                    # lives at the top of the window, so shifting it is still right, and the
                    # frame cuts are rebuilt from the *current* window rect anyway.
                    snap = clone_snapshot(last_snap, win)
                else:
                    # Never tear the frame down just because UIA is a beat behind: if the
                    # window still has the size we last applied the region for, the region is
                    # still correct (it lives in window coordinates). Only a real state
                    # change (minimised, fullscreen, resize) may open the native frame.
                    if applied and (win[2] - win[0], win[3] - win[1]) == applied[0]:
                        time.sleep(0.1)
                        continue
                    if hook:
                        hook.set_band(None)
                    if applied:
                        trace(f"clear region: no usable snapshot (win={win})")
                        restore_regions()
                        applied = None
                    if overlay:
                        u32.ShowWindow(overlay.hwnd, 0)
                    time.sleep(0.15)
                    continue
            elif snap is not None:
                last_snap, last_snap_t = snap, time.time()

            band = (win[0] + 1, snap.band[1], win[2] - 1, snap.band[3])
            if hook:
                hook.set_band(band)
            if child is None or not u32.IsWindow(child):
                child = d3d_child(hwnd)
            if draw_tabs:
                cuts = None
                n = cr = 0
                key = (band, None)
            else:
                # Native strip mode: thin glass frame on four sides, and the strip area from
                # the + button to the right edge is handed to OpenGlass (its Win7 caption
                # buttons get drawn there). Tab bodies are never touched.
                n = max(1, int(round(cfg.frame_px * scale)))
                cr = max(0, int(round(cfg.corner_px * scale)))
                if cap:
                    cap.set_frame(win, n)
                # The frame itself comes from insetting the region (frame_region); only the
                # OpenGlass caption corner is subtracted on top of it.
                cuts = []
                if cfg.gl_buttons and snap.band:
                    # Cut over the native caption buttons; UIA gives us their real rects.
                    btn_left = min((r[0] for r in (snap.min_r, snap.max_r, snap.close_r) if r),
                                   default=None)
                    if btn_left is None:
                        x = win[2] - int(3 * 46 * scale) - int(10 * scale)
                    else:
                        x = btn_left - int(6 * scale)
                    x = max(win[0] + n, x) // 2 * 2
                    corner = (x, snap.band[1] // 2 * 2, win[2], snap.band[3] // 2 * 2)
                    # bottom-left corner rounded: the window keeps a small arc where the cut
                    # meets the toolbar instead of a hard 90 degree notch
                    cuts.extend(round_corner_cut(corner[0], corner[1], corner[2], corner[3],
                                                 max(3, int(round(6 * scale)))))
                    if cap:
                        cap.set_area(corner, {"min": snap.min_r, "max": snap.max_r,
                                              "close": snap.close_r})
                elif cap:
                    cap.set_area(None, {})
                cuts = tuple(cuts)
                # Keys are window-RELATIVE: a plain move does not change the region (it is
                # expressed in window coordinates), so re-applying it on every mouse move
                # during a drag is pure flicker.
                rel = tuple((c[0] - win[0], c[1] - win[1], c[2] - win[0], c[3] - win[1])
                            for c in cuts)
                key = ((win[2] - win[0], win[3] - win[1]), n, cr, rel)
            if applied != key:
                # A size change must be applied at once; a band appearing/disappearing has to
                # be stable for 3 samples first, otherwise UIA flicker in fullscreen / during
                # tab animations makes the hole blink.
                size_changed = applied is not None and applied[0] != key[0]
                pend_n = pend_n + 1 if pending == key else 1
                pending = key
                if size_changed or pend_n >= 3:
                    if draw_tabs:
                        rgn = clip_region(win, band)
                        crgn = child_cut_region(child, band)
                    else:
                        rgn = frame_region(win, cuts, n, cr)
                        crgn = None
                    if rgn:
                        u32.SetWindowRgn(hwnd, rgn, True)
                    if crgn:
                        u32.SetWindowRgn(child, crgn, True)
                    applied = key
                    trace(f"apply region win={win} cuts={len(cuts or ())} n={n} r={cr}")
                    pending, pend_n = None, 0
                    log(f"frame {band} tabs={len(snap.tabs)} native={not draw_tabs} "
                        f"cuts={len(cuts or ())} child={child and hex(child)}")
            if overlay:
                sig = (snap.signature(), band)
                now = time.time()
                # Icons: the capture clears the region for ~80 ms, so it is rate-limited and
                # done right before a repaint (the overlay freezes the bar first -> no flash).
                if fav and (now - last_cap) >= 1.0 and fav.missing(snap):
                    last_cap = now
                    if fav.capture(snap, overlay, band, win):
                        painted_sig = None
                if overlay.pending_hover != overlay.hover and (now - last_paint) >= 0.04:
                    overlay.paint(snap, overlay.pending_hover)
                    painted_sig = sig
                    last_paint = now
                # throttle: a full recompose is ~10 ms of GIL, and the mouse hook lives here too
                elif sig != painted_sig and (now - last_paint) >= 0.25:
                    overlay.paint(snap, overlay.pending_hover)
                    painted_sig = sig
                    last_paint = now
                else:
                    overlay.raise_above()
            time.sleep(0.1)
    except Exception as e:
        log(f"attach loop error {e!r}")
    finally:
        worker.stop()
        if hook:
            hook.stop()
        if cap:
            cap.stop()
        if overlay:
            u32.DestroyWindow(overlay.hwnd)
        restore_regions()
        log("region reset")


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--hwnd", type=lambda s: int(s, 0))
    g.add_argument("--pid", type=int)
    ap.add_argument("--theme", choices=("dark", "light"), default=None)
    ap.add_argument("--settings", default=None, help="settings.json path")
    ap.add_argument("--tab-max-width", type=int, default=None, help="CSS px cap for a tab")
    ap.add_argument("--no-hover", action="store_true")
    ap.add_argument("--no-favicons", action="store_true")
    ap.add_argument("--dry-run", action="store_true", help="cut the hole only, no redraw")
    ap.add_argument("--reset", action="store_true", help="only restore the window region and exit")
    ap.add_argument("--scale", type=float, default=0.0)
    ap.add_argument("--fix-timeout", action="store_true",
                    help="raise HKCU LowLevelHooksTimeout to 1000 ms (stops clicks leaking when "
                         "the hook is slow); takes effect for newly installed hooks")
    a = ap.parse_args()

    hwnd = a.hwnd or find_window_by_pid(a.pid)
    if not hwnd:
        print("no Chromium window found")
        return 1

    if a.reset:
        u32.SetWindowRgn(hwnd, None, True)
        cu = d3d_child(hwnd)
        if cu:
            u32.SetWindowRgn(cu, None, True)
        u32.RedrawWindow(hwnd, None, None, 0x0001 | 0x0080 | 0x0100)
        print(f"region reset on {hwnd}")
        return 0

    if a.fix_timeout:
        import winreg
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Control Panel\Desktop") as k:
            winreg.SetValueEx(k, "LowLevelHooksTimeout", 0, winreg.REG_DWORD, 1000)
        print("LowLevelHooksTimeout = 1000 ms (restart the tool / hook to pick it up)")
    cfg = Settings(a.settings, theme=a.theme, tab_max_width=a.tab_max_width,
                   hover=False if a.no_hover else None,
                   favicons=False if a.no_favicons else None)
    dpi = u32.GetDpiForWindow(hwnd) or 96
    scale = a.scale or dpi / 96.0
    u32.SetWindowRgn(hwnd, None, True)          # clear a hole left behind by a killed run
    cu = d3d_child(hwnd)
    if cu:
        u32.SetWindowRgn(cu, None, True)
    print(f"target hwnd={hwnd} rect={window_rect(hwnd)} dpi={dpi} scale={scale:.2f} "
          f"settings={cfg.path}", flush=True)
    try:
        attach_loop(hwnd, cfg, scale, dry_run=a.dry_run)
    except KeyboardInterrupt:
        pass
    return 0


def find_window_by_pid(pid):
    hits = []

    def cb(h, l):
        if not u32.IsWindowVisible(h):
            return True
        p = wt.DWORD(); u32.GetWindowThreadProcessId(h, ctypes.byref(p))
        if p.value != pid:
            return True
        b = ctypes.create_unicode_buffer(128)
        u32.GetClassNameW(h, b, 128)
        if not b.value.startswith("Chrome_WidgetWin_"):
            return True
        r = window_rect(h)
        if r[2] - r[0] < 300:
            return True
        hits.append((h, r))
        return True

    u32.EnumWindows(CW(cb), 0)
    hits.sort(key=lambda x: -(x[1][2] - x[1][0]) * (x[1][3] - x[1][1]))
    return hits[0][0] if hits else None


if __name__ == "__main__":
    sys.exit(main())
