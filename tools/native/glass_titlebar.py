"""
glass_titlebar.py - thin glass frame around a Chromium browser window.

A thin strip on all four sides is cut out of the window with SetWindowRgn, which exposes the
Aero/OpenGlass glass DWM already renders behind it, and the top-right corner (from the native
`+` to the window edge) is cut out as well so OpenGlass can paint Win7 caption capsules there.
The tab strip itself is Chromium's own and is never touched: favicons, close buttons,
hit-testing and drag-reorder all stay native.

A UIA worker only supplies the tab band rectangle (and the native button rects used to size the
hole); an invisible layered window (TouchOverlay) covers the holed corner and turns clicks on
the drawn capsules into WM_SYSCOMMAND, plus drag / double-click on empty caption.

usage
  python glass_titlebar.py --hwnd 0x20FC4
  python glass_titlebar.py --pid 1072
Ctrl+C resets the window region and removes the overlay.
"""
from __future__ import annotations

import argparse
import ctypes
import ctypes.wintypes as wt
import json
import os
import queue
import sys
import threading
import time

import comtypes.client
from comtypes.gen import UIAutomationClient as UIA

u32 = ctypes.windll.user32
gdi = ctypes.windll.gdi32
k32 = ctypes.windll.kernel32
u32.SetProcessDPIAware()

DEBUG = os.environ.get("GLASS_TITLEBAR_DEBUG") == "1"
DEBUG_LOG = os.path.join(os.environ.get("LOCALAPPDATA") or os.environ.get("TEMP", "."),
                         "edge-win7-glass", "tool-debug.log")
try:
    os.makedirs(os.path.dirname(DEBUG_LOG), exist_ok=True)
except OSError:
    pass

_log_q = queue.Queue()


def dbg(msg):
    """Never touch the disk on the caller's thread: callers are latency sensitive."""
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
ULW_ALPHA = 0x02
WM_MOUSEACTIVATE = 0x0021
WM_MOUSEMOVE, WM_LBUTTONDOWN, WM_LBUTTONUP = 0x0200, 0x0201, 0x0202
WM_RBUTTONDOWN, WM_MBUTTONDOWN = 0x0204, 0x0207
SW_SHOWNOACTIVATE = 4

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
u32.GetForegroundWindow.restype = wt.HWND
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


class WNDCLASS(ctypes.Structure):
    _fields_ = [("style", ctypes.c_uint), ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int), ("hInstance", wt.HINSTANCE), ("hIcon", wt.HICON),
                ("hCursor", wt.HANDLE), ("hbrBackground", wt.HBRUSH), ("lpszMenuName", wt.LPCWSTR),
                ("lpszClassName", wt.LPCWSTR)]


# ------------------------------------------------------------------ UIA
TAB = UIA.UIA_TabItemControlTypeId
BTN = UIA.UIA_ButtonControlTypeId
SEL = UIA.UIA_SelectionItemPatternId


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
def hwnd_int(h):
    """HWND as a plain int. ctypes simple types (c_void_p) compare by *identity*, not value,
    so `GetForegroundWindow() == hwnd` is False even for the same window; compare .value
    instead. Accepts an int, a c_void_p, or None."""
    if h is None:
        return 0
    return h.value if isinstance(h, ctypes.c_void_p) else int(h)


def window_rect(h):
    r = RECT(); u32.GetWindowRect(h, ctypes.byref(r))
    return r.left, r.top, r.right, r.bottom


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


def frame_region(win, cuts, inset=0, radius=0, left=0):
    """Window region = inset rounded rectangle (glass frame) minus `cuts` (screen coords).

    The inset gives the four-sided glass frame; `radius` rounds the two TOP corners so the
    frame does not look like a hard rectangle (bottom corners stay square, like Win7).
    """
    wx0, wy0, wx1, wy1 = win
    W, H = wx1 - wx0, wy1 - wy0
    if inset > 0:
        x0, y0, x1, y1 = max(inset, left), inset, W - inset + 1, H - inset + 1
    else:
        x0, y0, x1, y1 = 0, 0, W, H
    def arc_off(r, i):
        """Horizontal inset of row i (0 = top) of a quarter circle of radius r."""
        dy = r - (i + 0.5)
        return r - int(round(max(0.0, r * r - dy * dy) ** 0.5))

    if radius > 0 and (x1 - x0) > 2 * radius and (y1 - y0) > 2 * radius:
        # Exact scanline quarter circles (CreateRoundRectRgn's ellipse is lumpy).
        rgn = gdi.CreateRectRgn(x0, y0 + radius, x1, y1)
        for i in range(radius):
            off = arc_off(radius, i)
            rr = gdi.CreateRectRgn(x0 + off, y0 + i, x1 - off, y0 + i + 1)
            gdi.CombineRgn(rgn, rgn, rr, 2)
            gdi.DeleteObject(rr)
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
        # Convex quarter circle where the cut's left edge meets the frame's top edge.
        if radius > 0 and cy0 <= y0 and cx1 >= W - 1 and cx0 - x0 > radius:
            for i in range(radius):
                off = arc_off(radius, i)
                if off <= 0:
                    continue
                rr = gdi.CreateRectRgn(cx0 - off, y0 + i, cx0, y0 + i + 1)
                gdi.CombineRgn(rgn, rgn, rr, 4)
                gdi.DeleteObject(rr)
    return rgn


def win7_caption_buttons(win, band, scale, cfg):
    """Screen rects of the Windows 7 caption capsules that OpenGlass paints in the hole.

    `CaptionButtons=2` uses Win7 metrics: min/max 30 DIP wide, close 50 DIP, the group's
    right edge 7 DIP in from the window edge. Chromium's own buttons are 46 DIP wide and end
    ~6 DIP in, so the two sets are offset by tens of pixels at 200% DPI: forwarding clicks by
    the UIA rects made a click on the drawn `−` hit Chromium's `□` (FINDINGS §11.12).
    The hole and the hit table must both come from *these* rects.
    """
    pad = int(round(cfg.btn_pad_right_px * scale))
    minw = max(4, int(round(cfg.btn_min_px * scale)))
    closew = max(4, int(round(cfg.btn_close_px * scale)))
    top = win[1] + int(round(cfg.btn_top_px * scale))
    height = int(round(cfg.btn_h_px * scale)) if cfg.btn_h_px else (band[3] - band[1])
    bottom = top + max(8, height)
    close_r = win[2] - pad
    out = {}
    out["close"] = (close_r - closew, top, close_r, bottom)
    max_r = close_r - closew
    out["max"] = (max_r - minw, top, max_r, bottom)
    min_r = max_r - minw
    out["min"] = (min_r - minw, top, min_r, bottom)
    return out


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


def force_foreground(h):
    """SetForegroundWindow from a background process needs a thread-input attach."""
    if not h or not u32.IsWindow(h):
        return
    if hwnd_int(u32.GetForegroundWindow()) == hwnd_int(h):
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


# ------------------------------------------------------------------ settings / layout
SETTINGS_PATH = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")),
                             "edge-win7-glass", "settings.json")


class Settings:
    """Tunables, read from %APPDATA%\\edge-win7-glass\\settings.json (CLI wins over file)."""

    DEFAULTS = {
        "frame_px": 4,             # CSS px; thin glass frame on all four sides
        "corner_px": 6,            # CSS px; radius of the two top corners of the frame
        "gl_buttons": True,        # hand the top-right corner to OpenGlass caption buttons
        # OpenGlass CaptionButtons=2 draws *Windows 7* metrics; Chromium's own buttons are
        # 46 DIP wide with a different right margin, so hit-testing the UIA rects makes a
        # click on a drawn capsule fire its neighbour (FINDINGS 11.12). These describe the
        # set that is actually painted inside the hole.
        "btn_pad_right_px": 7,     # DIP; right edge of the capsule group -> window right edge
        "btn_min_px": 30,          # DIP; width of the minimise AND maximise capsule
        "btn_close_px": 50,        # DIP; width of the close capsule
        "btn_top_px": 0,           # DIP; capsule top relative to the window top
        "btn_h_px": 0,             # DIP; capsule height, 0 = the whole tab band
        "btn_h_fix_px": 0,         # DIP; 挖孔高度修正，负值减小（解决挖孔底部侵入窗口内容区）
        "port": 8721,              # local settings page
        "autostart": False,
        "lang": "auto",            # UI language: "auto" (follow Windows) / "zh" / "en"
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


# ------------------------------------------------------------ touch overlay input
class TouchOverlay(threading.Thread):
    """Invisible layered window that owns the OpenGlass caption corner's input.

    The caption corner is a region *hole* (OpenGlass paints its Win7 capsules there), so input
    in that area falls through to whatever sits behind the browser. The old answer was a global
    WH_MOUSE_LL hook, whose callbacks Windows silently unloads when they run long, which needs
    a watchdog, and which breaks under two daemon copies (one eats the other's LBUTTONUP).

    Instead this overlays an invisible (alpha=1) layered window on exactly the hole. Its own
    WndProc receives the mouse messages and drives the browser directly:
      * on a capsule  -> WM_SYSCOMMAND (SC_MINIMIZE / SC_MAXIMIZE|SC_RESTORE / SC_CLOSE)
      * on empty caption -> drag the window; a double-click toggles maximise
      * any click in the hole -> bring the window to the foreground first
    The capsule rects come from win7_caption_buttons() -- the *drawn* Win7 metrics, never
    Chromium's UIA button rects -- so a click on the drawn `-` never fires the native `□`
    (FINDINGS 11.12/11.13). The overlay rect is the exact hole rect, so hole, hit table and
    input surface all share one source of geometry.

    Only the TOP caption corner is handled here: the four-side resize borders are out of scope
    for now (a separate overlay can cover those later).
    """

    SC = {"min": 0xF020, "max": 0xF030, "restore": 0xF120, "close": 0xF060}

    def __init__(self, target):
        super().__init__(daemon=True, name="touch-overlay")
        self.target = target
        self.area = None            # screen rect of the holed corner
        self.buttons = {}           # name -> rect (the Win7 capsules OpenGlass paints)
        self.hwnd = None
        self.moving = None          # (start window rect, grab point in screen coords)
        self.restore_drag = None    # (x0, y0, start rect, grab ratio) while maximised
        self.down = False
        self.pending = None         # capsule name hit on button-down
        self.last_click = (0.0, (0, 0))
        self.drag_t0 = 0.0
        self.stop_flag = False
        self.lock = threading.Lock()
        self.q = queue.Queue()
        self._proc = WNDPROC(self._wndproc)
        # 64-bit handles: without argtypes ctypes passes Python ints as 32-bit c_int and
        # truncates the HWND. Set these here (types match gt_daemon._setup_win32 so they do
        # not fight over a shared process). RegisterClassW / GetCursorPos stay untyped: they
        # take a custom WNDCLASS / POINT struct that differs between modules (FINDINGS 10.1).
        u32.CreateWindowExW.argtypes = [wt.DWORD, wt.LPCWSTR, wt.LPCWSTR, wt.DWORD,
                                        ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                        wt.HWND, wt.HMENU, wt.HINSTANCE, ctypes.c_void_p]
        u32.CreateWindowExW.restype = wt.HWND
        u32.GetWindow.argtypes = [wt.HWND, wt.UINT]
        u32.GetWindow.restype = wt.HWND
        u32.SetWindowPos.argtypes = [wt.HWND, wt.HWND, ctypes.c_int, ctypes.c_int,
                                     ctypes.c_int, ctypes.c_int, wt.UINT]
        u32.SetWindowPos.restype = wt.BOOL
        u32.ShowWindow.argtypes = [wt.HWND, ctypes.c_int]
        u32.PostMessageW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
        u32.PostMessageW.restype = wt.BOOL
        u32.GetMessageW.argtypes = [ctypes.POINTER(wt.MSG), wt.HWND, wt.UINT, wt.UINT]
        u32.TranslateMessage.argtypes = [ctypes.POINTER(wt.MSG)]
        u32.DispatchMessageW.argtypes = [ctypes.POINTER(wt.MSG)]
        u32.DispatchMessageW.restype = ctypes.c_ssize_t
        u32.SetCapture.argtypes = [wt.HWND]
        u32.ReleaseCapture.argtypes = []
        u32.GetDoubleClickTime.restype = wt.UINT
        threading.Thread(target=self._worker, daemon=True, name="touch-worker").start()

    @property
    def busy(self):
        """True while a hand move started by this overlay is in flight."""
        return bool(self.moving or self.restore_drag)

    # -------------------------------------------------- foreground activation
    def _worker(self):
        """SetForegroundWindow / AttachThreadInput can block for hundreds of ms; run them off
        the message-loop thread (a slow LL hook callback got silently dropped -- same applies)."""
        while not self.stop_flag:
            try:
                self.q.get(timeout=0.5)
            except queue.Empty:
                continue
            try:
                force_foreground(self.target)
            except Exception as e:
                dbg(f"touch worker error {e!r}")

    def _ask_fg(self):
        self.q.put(1)

    # -------------------------------------------------- geometry
    def set_area(self, area, buttons):
        """Move/resize the overlay to cover `area` (the hole) and record the capsule rects."""
        with self.lock:
            self.area = area
            self.buttons = {k: v for k, v in buttons.items() if v}
        self._reposition()

    def clear(self):
        self.set_area(None, {})

    def _hit(self, x, y):
        a = self.area
        if not a or not (a[0] <= x < a[2] and a[1] <= y < a[3]):
            return None
        for name, r in self.buttons.items():
            if r[0] <= x < r[2] and r[1] <= y < r[3]:
                return name
        return None

    # -------------------------------------------------- window plumbing
    def _reposition(self):
        if not self.hwnd:
            return
        a = self.area
        if not a:
            u32.ShowWindow(self.hwnd, 0)
            return
        x, y, x1, y1 = a
        w, h = x1 - x, y1 - y
        if w <= 0 or h <= 0:
            u32.ShowWindow(self.hwnd, 0)
            return
        # Per-pixel alpha of 1 is invisible to the eye but NOT transparent to DWM hit-testing
        # (only alpha 0 lets the mouse through), so the whole window stays clickable.
        screen = u32.GetDC(None)
        mem = gdi.CreateCompatibleDC(screen)
        bmi = BITMAPINFO()
        bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bmi.bmiHeader.biWidth = w
        bmi.bmiHeader.biHeight = -h
        bmi.bmiHeader.biPlanes = 1
        bmi.bmiHeader.biBitCount = 32
        bits = ctypes.c_void_p()
        hbmp = gdi.CreateDIBSection(mem, ctypes.byref(bmi), 0, ctypes.byref(bits), None, 0)
        old = gdi.SelectObject(mem, hbmp)
        ctypes.memset(bits, 1, w * h * 4)       # BGRA, every byte 1 -> alpha 1 everywhere
        blend = BLENDFUNCTION(AC_SRC_OVER, 0, 255, AC_SRC_ALPHA)
        dst = POINT(x, y)
        size = SIZE(w, h)
        src = POINT(0, 0)
        u32.UpdateLayeredWindow(self.hwnd, screen, ctypes.byref(dst), ctypes.byref(size),
                                mem, ctypes.byref(src), 0, ctypes.byref(blend), ULW_ALPHA)
        gdi.SelectObject(mem, old)
        gdi.DeleteObject(hbmp)
        gdi.DeleteDC(mem)
        u32.ReleaseDC(None, screen)
        u32.SetWindowPos(self.hwnd, 0, x, y, w, h, SWP_NOACTIVATE)
        u32.ShowWindow(self.hwnd, SW_SHOWNOACTIVATE)
        self._raise_above()

    def _raise_above(self):
        """Keep the overlay directly above the browser window (it must win the hit test)."""
        prev = u32.GetWindow(self.target, 3)      # GW_HWNDPREV
        if hwnd_int(prev) == hwnd_int(self.hwnd):
            return
        u32.SetWindowPos(self.hwnd, prev or 0, 0, 0, 0, 0,
                         SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)

    def refresh_zorder(self, foreground):
        """Track the target's Z-order so a foreground window's hole never falls through to a
        *sibling* window's overlay (multi-window confusion).

        `_raise_above` only runs when the hole geometry changes (`set_area`); switching
        foreground between two managed windows moves the browser windows in Z-order but not
        the overlays, so a stale overlay of a background window can sit above the foreground
        window and eat its caption clicks. Re-fix the overlay's band on every foreground
        change:
          * foreground -> HWND_TOP, so it beats any stale sibling overlay;
          * background -> just above its own target, below the foreground window, so it can
            still catch a click on a *visible* caption corner (to bring the window forward)
            without stealing clicks from the window in front.
        """
        if not self.hwnd:
            return
        if foreground:
            u32.SetWindowPos(self.hwnd, 0, 0, 0, 0, 0,
                             SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)
        else:
            self._raise_above()

    # -------------------------------------------------- mouse handling
    def _wndproc(self, h, msg, wp, lp):
        if msg == WM_MOUSEACTIVATE:
            return MA_NOACTIVATE
        try:
            if msg in (WM_LBUTTONDOWN, WM_MOUSEMOVE, WM_LBUTTONUP):
                p = POINT()
                u32.GetCursorPos(ctypes.byref(p))
                return self._mouse(msg, p.x, p.y)
            if msg in (WM_RBUTTONDOWN, WM_MBUTTONDOWN):
                return 0               # swallow right/middle clicks in the hole
        except Exception as e:
            dbg(f"touch wndproc error {e!r}")
        return u32.DefWindowProcW(h, msg, wp, lp)

    def _mouse(self, msg, x, y):
        if msg == WM_LBUTTONDOWN:
            self._ask_fg()
            u32.SetCapture(self.hwnd)      # keep the drag alive when the cursor leaves the hole
            self.down = True
            self.drag_t0 = time.time()
            self.pending = self._hit(x, y)
            trace(f"touch down {x},{y} hit={self.pending}")
            if not self.pending:
                if u32.IsZoomed(self.target):
                    mr = window_rect(self.target)
                    self.restore_drag = (x, y, mr, (x - mr[0]) / max(1, mr[2] - mr[0]))
                else:
                    self.moving = (window_rect(self.target), (x, y))
            return 0
        if msg == WM_MOUSEMOVE:
            if self.restore_drag:
                x0, y0, mr, ratio = self.restore_drag
                if abs(x - x0) + abs(y - y0) > 8:
                    self.restore_drag = None
                    u32.ShowWindow(self.target, 9)          # SW_RESTORE
                    nr = window_rect(self.target)
                    nw = max(1, nr[2] - nr[0])
                    u32.SetWindowPos(self.target, 0, x - int(ratio * nw), nr[1], 0, 0,
                                     SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE)
                    self.moving = (window_rect(self.target), (x, y))
                    trace(f"touch restore-drag -> {self.moving[0]}")
            elif self.moving:
                r0, (sx, sy) = self.moving
                u32.SetWindowPos(self.target, 0, r0[0] + (x - sx), r0[1] + (y - sy), 0, 0,
                                 SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE)
            return 0
        if msg == WM_LBUTTONUP:
            u32.ReleaseCapture()
            if self.restore_drag:
                self.restore_drag = None
                self.down = False
                return 0
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
                        trace("touch double click -> toggle maximize")
                        self.last_click = (0.0, (0, 0))
                    else:
                        self.last_click = (now, (x, y))
                return 0
            name, self.pending = self.pending, None
            self.down = False
            if name:
                if name == "max":
                    name = "restore" if u32.IsZoomed(self.target) else "max"
                u32.PostMessageW(self.target, WM_SYSCOMMAND, self.SC[name], 0)
                trace(f"touch click -> {name}")
            return 0
        return 0

    # -------------------------------------------------- thread / message loop
    def run(self):
        inst = k32.GetModuleHandleW(None)
        wc = WNDCLASS()
        wc.lpfnWndProc = _OVERLAY_PROC     # shared by every instance; dispatches by hwnd
        wc.hInstance = inst
        wc.lpszClassName = "GlassTouchOverlay"
        wc.hCursor = u32.LoadCursorW(None, 32512)
        if not u32.RegisterClassW(ctypes.byref(wc)) and k32.GetLastError() != 1410:
            dbg(f"touch register class failed {k32.GetLastError()}")
            return
        ex = WS_EX_TOOLWINDOW | WS_EX_LAYERED | WS_EX_NOACTIVATE
        h = u32.CreateWindowExW(ex, "GlassTouchOverlay", "", WS_POPUP,
                                -20000, -20000, 10, 10, None, None, inst, None)
        if not h:
            dbg(f"touch create failed {ctypes.GetLastError()}")
            return
        self.hwnd = h
        _OVERLAYS[hwnd_int(h)] = self
        trace(f"touch overlay created hwnd={h:x}")
        if self.stop_flag:                 # stop() raced ahead of window creation
            u32.DestroyWindow(h)
            self.hwnd = None
            return
        with self.lock:
            a, b = self.area, self.buttons
        if a:
            self._reposition()             # an area may have been set before the window existed
        msg = wt.MSG()
        while not self.stop_flag and u32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            u32.TranslateMessage(ctypes.byref(msg))
            u32.DispatchMessageW(ctypes.byref(msg))
        if self.hwnd:
            _OVERLAYS.pop(hwnd_int(self.hwnd), None)
            u32.DestroyWindow(self.hwnd)
            self.hwnd = None

    def stop(self):
        self.stop_flag = True
        if self.hwnd:
            u32.PostMessageW(self.hwnd, 0x8001, 0, 0)   # WM_APP+1: wake GetMessage so it exits


# One window class serves every overlay in the process, and RegisterClassW keeps only the
# FIRST registration's WndProc. A per-instance bound method therefore made every later
# overlay run the first instance's handler, so clicks in window B's caption corner moved,
# minimised or closed window A. Dispatch by overlay hwnd instead.
_OVERLAYS = {}


def _overlay_wndproc(h, msg, wp, lp):
    ov = _OVERLAYS.get(hwnd_int(h))
    if ov is None:
        return u32.DefWindowProcW(h, msg, wp, lp)
    return ov._wndproc(h, msg, wp, lp)


_OVERLAY_PROC = WNDPROC(_overlay_wndproc)




def attach_loop(hwnd, cfg, scale, stop_event=None, log=print):
    """Manage ONE window until it dies or stop_event is set (blocking).

    Split out of main() so the daemon can run several of these in parallel threads.

    The tab strip is Chromium's own. This only cuts a thin glass frame on the four sides and
    subtracts the top-right corner for OpenGlass' Win7 caption capsules; TouchOverlay turns a
    click on those capsules back into WM_SYSCOMMAND on the browser window.
    """
    worker = UiaWorker(hwnd)
    worker.start()
    cap = TouchOverlay(hwnd) if cfg.gl_buttons else None
    if cap:
        cap.start()

    applied = None
    pending = None
    pend_n = 0
    last_snap = None
    last_snap_t = 0.0
    btn_sig = None
    was_fg = None

    def restore_region():
        """Parent region, plus the D3D child in case an older build left a hole there."""
        if u32.IsWindow(hwnd):
            u32.SetWindowRgn(hwnd, None, True)
        child = d3d_child(hwnd)
        if child and u32.IsWindow(child):
            u32.SetWindowRgn(child, None, True)

    try:
        while not (stop_event and stop_event.is_set()):
            if not u32.IsWindow(hwnd):
                log("window gone")
                break
            if u32.IsIconic(hwnd) or not u32.IsWindowVisible(hwnd):
                if cap:
                    cap.clear()
                if applied:
                    trace(f"clear region: iconic/hidden {hwnd:x}")
                    restore_region()
                    applied = None
                time.sleep(0.2)
                continue

            win = window_rect(hwnd)
            if cap:
                fg = hwnd_int(u32.GetForegroundWindow()) == hwnd_int(hwnd)
                if fg != was_fg:
                    was_fg = fg
                    cap.refresh_zorder(fg)
                    trace(f"zorder fg={fg} hwnd={hwnd:x}")
            if cap and cap.busy:
                # A hand move started by the overlay is in flight: the region is expressed in
                # window coordinates so it follows the window by itself. Touching it (or
                # re-reading UIA, which still reports the old rect) is what made the hole blink
                # away mid-drag and the window look like it reset.
                time.sleep(0.05)
                continue
            if is_fullscreen(hwnd, win):
                if applied:
                    restore_region()
                    applied = None
                    pending, pend_n = None, 0
                    trace(f"clear region: fullscreen {hwnd:x}")
                    log("fullscreen -> region cleared")
                if cap:
                    cap.clear()
                time.sleep(0.25)
                continue
            snap = worker.latest()
            if not snap or not snap.band or snap.win != win:
                # A hand-drag moves the window every few ms, so the UIA snapshot is always one
                # step behind. Being strict here cleared the hole and repainted the native
                # frame on every loop while dragging -- the window looked like it "reset".
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
                    if applied:
                        trace(f"clear region: no usable snapshot (win={win})")
                        restore_region()
                        applied = None
                    if cap:
                        cap.clear()
                    time.sleep(0.15)
                    continue
            elif snap is not None:
                last_snap, last_snap_t = snap, time.time()

            band = (win[0] + 1, snap.band[1], win[2] - 1, snap.band[3])
            # Thin glass frame on four sides, and the strip area from the + button to the
            # right edge handed to OpenGlass (its Win7 caption buttons are drawn there).
            # Tab bodies are never touched.
            n = max(1, int(round(cfg.frame_px * scale)))
            cr = max(0, int(round(cfg.corner_px * scale)))
            # The frame itself comes from insetting the region (frame_region); only the
            # OpenGlass caption corner is subtracted on top of it.
            cuts = []
            if cfg.gl_buttons and snap.band:
                # Two geometries have to agree: the hole (what OpenGlass paints in) starts
                # at the right of the native `+` -- that area is empty strip background and
                # the `+` keeps its own hit-testing -- while the Win7 capsules OpenGlass
                # draws come from win7_caption_buttons(), never from Chromium's UIA button
                # rects (46 DIP wide, 6 DIP right margin: tens of px off at 200% DPI).
                # Nothing swallows clicks here any more, so the hole covers every pixel a
                # native button could occupy: a click that reaches one fires a command
                # nobody drew.
                btns = win7_caption_buttons(win, snap.band, scale, cfg)
                native = (snap.min_r, snap.max_r, snap.close_r)
                x = btns["min"][0] - int(2 * scale)        # hole always covers the capsules
                if snap.newtab_r:
                    x = min(x, snap.newtab_r[2] + int(2 * scale))
                else:
                    btn_left = min((r[0] for r in native if r), default=None)
                    if btn_left is not None:
                        x = min(x, btn_left - int(6 * scale))
                # Chromium's own buttons must sit fully inside the hole as well: wherever one
                # pokes out, a click can reach a button that is not even drawn. Without a
                # hook to block those clicks, the hole has to cover them itself.
                for r in native:
                    if r:
                        x = min(x, r[0] - int(2 * scale))
                x = max(win[0] + n, x) // 2 * 2
                # 挖孔底部修正：band[3]（UIA 标签带底部）可能比真实标题栏下缘低几个像素，
                # 导致挖孔侵入窗口内容区；btn_h_fix_px（负值）把挖孔底部往上收。
                fix = int(round(cfg.btn_h_fix_px * scale))
                corner = (x, snap.band[1] // 2 * 2, win[2], (snap.band[3] + fix) // 2 * 2)
                # bottom-left corner rounded: the window keeps a small arc where the cut
                # meets the toolbar instead of a hard 90 degree notch
                cuts.extend(round_corner_cut(corner[0], corner[1], corner[2], corner[3],
                                             max(3, int(round(6 * scale)))))
                if cap:
                    cap.set_area(corner, btns)
                if btns != btn_sig:
                    btn_sig = btns
                    trace("buttons hole=%s %s" % (corner, " ".join(
                        f"{k}={v}" for k, v in btns.items())))
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
                    # Edge's visible content starts at its client left edge (the window rect
                    # has an invisible resize border), so the left arc must start there or
                    # the content clips it into a flat ellipse.
                    pt = wt.POINT(0, 0)
                    u32.ClientToScreen(hwnd, ctypes.byref(pt))
                    rgn = frame_region(win, cuts, n, cr, max(0, pt.x - win[0]))
                    if rgn:
                        u32.SetWindowRgn(hwnd, rgn, True)
                    applied = key
                    trace(f"apply region win={win} cuts={len(cuts)} n={n} r={cr}")
                    pending, pend_n = None, 0
                    log(f"frame {band} tabs={len(snap.tabs)} cuts={len(cuts)}")
            time.sleep(0.1)
    except Exception as e:
        log(f"attach loop error {e!r}")
    finally:
        worker.stop()
        if cap:
            cap.stop()
        restore_region()
        log("region reset")


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--hwnd", type=lambda s: int(s, 0))
    g.add_argument("--pid", type=int)
    ap.add_argument("--settings", default=None, help="settings.json path")
    ap.add_argument("--reset", action="store_true", help="only restore the window region and exit")
    ap.add_argument("--scale", type=float, default=0.0)
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

    cfg = Settings(a.settings)
    dpi = u32.GetDpiForWindow(hwnd) or 96
    scale = a.scale or dpi / 96.0
    u32.SetWindowRgn(hwnd, None, True)          # clear a hole left behind by a killed run
    cu = d3d_child(hwnd)
    if cu:
        u32.SetWindowRgn(cu, None, True)
    print(f"target hwnd={hwnd} rect={window_rect(hwnd)} dpi={dpi} scale={scale:.2f} "
          f"settings={cfg.path}", flush=True)
    try:
        attach_loop(hwnd, cfg, scale)
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
