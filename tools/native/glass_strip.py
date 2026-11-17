"""
glass_strip.py - make a Chromium browser's tab-strip background show the Aero/OpenGlass
glass that already sits behind it, without injecting anything.

Mechanism
---------
Chromium extends its window frame into the tab strip, so DWM/OpenGlass already renders glass
behind that strip; Chromium then paints opaque pixels over it. Removing exactly those
background pixels with SetWindowRgn exposes the glass. Tabs, the new-tab button and the
window buttons are excluded, so only the *gaps* are cut.

Tab/button rectangles come from UI Automation (Chromium exposes TabItem elements with real
screen rects), so holes follow open/close/drag automatically.

A region hole is also a hole for the mouse, so a low-level mouse hook swallows clicks landing
in a hole and re-implements the two actions that matter there: drag to move the window and
double-click to maximize. Swallowing also keeps the desktop from receiving those clicks.

usage
  python glass_strip.py --pid 1234
  python glass_strip.py --hwnd 0x20FC4 [--dry-run] [--no-clicks]
Ctrl+C resets the region and exits.
"""
from __future__ import annotations

import argparse
import ctypes
import ctypes.wintypes as wt
import os
import sys
import threading
import time

import comtypes.client
from comtypes.gen import UIAutomationClient as UIA

u32 = ctypes.windll.user32
gdi = ctypes.windll.gdi32
k32 = ctypes.windll.kernel32
u32.SetProcessDPIAware()

DEBUG = os.environ.get("GLASS_STRIP_DEBUG") == "1"
ALLOW_INJECTED = os.environ.get("GLASS_STRIP_ALLOW_INJECTED") == "1"
DEBUG_LOG = os.path.join(os.environ.get("TEMP", "."), "glass_strip_debug.log")


def dbg(msg):
    if not DEBUG:
        return
    try:
        with open(DEBUG_LOG, "a", encoding="utf-8") as f:
            f.write(f"{time.time():.2f} {msg}\n")
    except Exception:
        pass


GWL_STYLE = -16
WS_MAXIMIZE = 0x01000000
SW_MAXIMIZE, SW_RESTORE = 3, 9
WH_MOUSE_LL = 14
WM_LBUTTONDOWN, WM_LBUTTONUP = 0x0201, 0x0202
WM_RBUTTONDOWN, WM_RBUTTONUP = 0x0204, 0x0205
WM_MBUTTONDOWN, WM_MBUTTONUP = 0x0207, 0x0208
WM_MOUSEMOVE = 0x0200
LLMHF_INJECTED = 0x00000001
SWP_NOZORDER, SWP_NOACTIVATE = 0x0004, 0x0010

CW = ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)


class RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [("pt", POINT), ("mouseData", wt.DWORD), ("flags", wt.DWORD),
                ("time", wt.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


u32.GetWindowLongW.restype = ctypes.c_long
u32.SetWindowRgn.argtypes = [wt.HWND, wt.HANDLE, wt.BOOL]
k32.GetModuleHandleW.restype = wt.HMODULE
u32.CallNextHookEx.argtypes = [wt.HANDLE, ctypes.c_int, wt.WPARAM, wt.LPARAM]
u32.CallNextHookEx.restype = ctypes.c_ssize_t
u32.SetWindowsHookExW.argtypes = [ctypes.c_int, ctypes.c_void_p, wt.HMODULE, wt.DWORD]
u32.SetWindowsHookExW.restype = wt.HHOOK
u32.UnhookWindowsHookEx.argtypes = [wt.HHOOK]
u32.GetMessageW.argtypes = [ctypes.POINTER(wt.MSG), wt.HWND, wt.UINT, wt.UINT]


# ------------------------------------------------------------------ UIA
class UIA_helper:
    def __init__(self):
        self.uia = comtypes.client.CreateObject(UIA.CUIAutomation, interface=UIA.IUIAutomation)

    def strip_rects(self, hwnd):
        """-> (tabs, protected) screen-coord rects found under the browser window."""
        root = self.uia.ElementFromHandle(hwnd)
        tabs, prot = [], []
        for ctype in (UIA.UIA_TabItemControlTypeId, UIA.UIA_ButtonControlTypeId):
            cond = self.uia.CreatePropertyCondition(UIA.UIA_ControlTypePropertyId, ctype)
            found = root.FindAll(UIA.TreeScope_Descendants, cond)
            for i in range(found.Length):
                el = found.GetElement(i)
                try:
                    r = el.CurrentBoundingRectangle
                except Exception:
                    continue
                if r.right <= r.left or r.bottom <= r.top:
                    continue
                (tabs if ctype == UIA.UIA_TabItemControlTypeId else prot).append(
                    (r.left, r.top, r.right, r.bottom))
        return tabs, prot


# ------------------------------------------------------------------ UIA worker
class UiaWorker:
    """Polls UIA in its own thread and publishes the latest sample.

    Chromium's UIA tree can block for seconds (it did in fullscreen), which used to stall the
    main loop and leave stale holes cut into the page. The main loop now only uses fresh
    samples and clears the holes whenever it has none.
    """

    def __init__(self, hwnd):
        self.hwnd = hwnd
        self.lock = threading.Lock()
        self.sample = None          # (win, tabs, prot, timestamp)
        self.thread = None
        self.gen = 0

    def start(self):
        self.gen += 1
        self.thread = threading.Thread(target=self._run, args=(self.gen,), daemon=True)
        self.thread.start()

    def _run(self, gen):
        ole32 = ctypes.windll.ole32
        ole32.CoInitializeEx(None, 0x2)        # STA: UIA needs COM on every worker thread
        try:
            while self.gen == gen:
                t0 = time.time()
                try:
                    helper = UIA_helper()      # fresh COM object: a hung call must not stick
                    win = window_rect(self.hwnd)
                    tabs, prot = helper.strip_rects(self.hwnd)
                    if self.gen != gen:
                        return
                    with self.lock:
                        self.sample = (win, tabs, prot, time.time())
                except Exception as e:
                    dbg(f"uia worker error {e}")
                cost = time.time() - t0
                time.sleep(0.25 if cost < 0.25 else 0.05)
        finally:
            ole32.CoUninitialize()

    def latest(self, max_age=1.5):
        with self.lock:
            s = self.sample
        if not s:
            return None
        win, tabs, prot, ts = s
        if time.time() - ts > max_age:
            return None
        return s

    def maybe_restart(self, max_silence=3.0):
        """Chromium's UIA can block for good (seen in fullscreen): abandon the thread."""
        with self.lock:
            ts = self.sample[3] if self.sample else 0.0
        if time.time() - ts > max_silence:
            dbg("uia worker restart")
            self.start()
            return True
        return False

    def stop(self):
        self.gen += 1


# ------------------------------------------------------------------ geometry
def window_rect(h):
    r = RECT(); u32.GetWindowRect(h, ctypes.byref(r))
    return r.left, r.top, r.right, r.bottom


def nc_top_of(h, win):
    c = POINT(0, 0)
    u32.ClientToScreen(h, ctypes.byref(c))
    return c.y - win[1]


def strip_band(h, tabs, prot, win):
    """(y0, y1) of a believable tab strip, else None.

    Guards against stale/misreported UIA rects -- those are what made holes land on the page
    area after a window move or in fullscreen, killing every click there.
    """
    if not tabs:
        return None
    if nc_top_of(h, win) < 20:               # fullscreen (F11) has no caption: never cut
        return None
    y0 = min(t[1] for t in tabs)
    y1 = max(t[3] for t in tabs)
    if not (16 <= y1 - y0 <= 100):
        return None
    if y0 < win[1] + 6 or y1 > win[1] + 200:
        return None
    for t in tabs + prot:
        if t[2] < win[0] or t[0] > win[2] or t[3] < win[1] or t[1] > win[3]:
            return None
    return y0, y1


def compute_holes(tabs, protected, win, min_gap, band):
    if not band:
        return []
    y0, y1 = band
    blockers = sorted((t for t in (tabs + protected) if t[3] > y0 and t[1] < y1),
                      key=lambda t: t[0])
    wx0, _wy0, wx1, _wy1 = win
    x, right = wx0 + 6, wx1 - 6
    holes = []
    for b in blockers:
        if b[0] - x >= min_gap:
            holes.append((x, y0, b[0] - 2, y1))
        x = max(x, b[2] + 2)
    if right - x >= min_gap:
        holes.append((x, y0, right, y1))
    return [h for h in holes if h[2] - h[0] >= min_gap
            and h[0] >= wx0 and h[2] <= wx1 and h[1] >= win[1] and h[3] <= win[3]]


def build_region(win, holes):
    """Region = window rect minus holes (screen coords in, window-region handle out)."""
    wx0, wy0, wx1, wy1 = win
    W, H = wx1 - wx0, wy1 - wy0
    local = [(max(0, a - wx0), max(0, b - wy0), min(W, c - wx0), min(H, d - wy0))
             for a, b, c, d in holes]
    local = [r for r in local if r[2] > r[0] and r[3] > r[1]]
    ys = sorted({0, H} | {y for r in local for y in (r[1], r[3])})
    rgn = gdi.CreateRectRgn(0, 0, 0, 0)
    for i in range(len(ys) - 1):
        y1, y2 = ys[i], ys[i + 1]
        if y2 <= y1:
            continue
        band = [r for r in local if r[1] <= y1 and r[3] >= y2]
        xs = sorted({0, W} | {x for r in band for x in (r[0], r[2])})
        for j in range(len(xs) - 1):
            x1, x2 = xs[j], xs[j + 1]
            if x2 <= x1 or any(a <= x1 and x2 <= c for a, _b, c, _d in band):
                continue
            rr = gdi.CreateRectRgn(x1, y1, x2, y2)
            gdi.CombineRgn(rgn, rgn, rr, 2)     # RGN_OR
            gdi.DeleteObject(rr)
    return rgn


# ------------------------------------------------------------------ click guard
class ClickGuard:
    """Low-level mouse hook: swallows clicks in the holes, re-adds drag + double-click."""

    def __init__(self, target):
        self.target = target
        self.holes = []
        self.lock = threading.Lock()
        self.hook = None
        self.thread = None
        self.dragging = False
        self.down_pt = (0, 0)
        self.down_rect = (0, 0, 0, 0)
        self.last_click_time = 0.0
        self.last_click_pt = (0, 0)
        self._proc = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, ctypes.c_int, wt.WPARAM, wt.LPARAM)(self._hook)

    def set_holes(self, holes):
        with self.lock:
            self.holes = list(holes)

    def in_hole(self, x, y):
        with self.lock:
            return any(a <= x < c and b <= y < d for a, b, c, d in self.holes)

    def _hook(self, code, wparam, lparam):
        if code < 0:
            return u32.CallNextHookEx(None, code, wparam, lparam)
        try:
            info = ctypes.cast(lparam, ctypes.POINTER(MSLLHOOKSTRUCT)).contents
            if info.flags & LLMHF_INJECTED and not ALLOW_INJECTED:
                return u32.CallNextHookEx(None, code, wparam, lparam)
            x, y = info.pt.x, info.pt.y
            msg = wparam & 0xFFFFFFFF
            t = self.target
            active = bool(t) and u32.IsWindow(t) and u32.GetForegroundWindow() == t \
                and self.in_hole(x, y)
            if msg == WM_LBUTTONDOWN:
                if not active:
                    return u32.CallNextHookEx(None, code, wparam, lparam)
                if u32.GetWindowLongW(t, GWL_STYLE) & WS_MAXIMIZE:
                    return 1
                self.dragging = True
                self.down_pt = (x, y)
                self.down_rect = window_rect(t)
                u32.SetForegroundWindow(t)
                dbg(f"drag start {x},{y} rect={self.down_rect}")
                return 1
            if msg == WM_MOUSEMOVE and self.dragging:
                dx, dy = x - self.down_pt[0], y - self.down_pt[1]
                x0, y0, x1, y1 = self.down_rect
                u32.SetWindowPos(t, 0, x0 + dx, y0 + dy, x1 - x0, y1 - y0,
                                 SWP_NOZORDER | SWP_NOACTIVATE)
                return 1
            if msg == WM_LBUTTONUP:
                if self.dragging:
                    self.dragging = False
                    moved = abs(x - self.down_pt[0]) + abs(y - self.down_pt[1])
                    dbg(f"drag end moved={moved}")
                    if moved <= 3:
                        now = time.time()
                        dbl = (now - self.last_click_time) <= (u32.GetDoubleClickTime() / 1000.0)
                        near = abs(x - self.last_click_pt[0]) <= 4 and \
                               abs(y - self.last_click_pt[1]) <= 4
                        if dbl and near:
                            if u32.GetWindowLongW(t, GWL_STYLE) & WS_MAXIMIZE:
                                u32.ShowWindow(t, SW_RESTORE)
                            else:
                                u32.ShowWindow(t, SW_MAXIMIZE)
                            u32.SetForegroundWindow(t)
                            self.last_click_time = 0.0
                            dbg("double click -> toggle maximize")
                        else:
                            self.last_click_time = now
                            self.last_click_pt = (x, y)
                    return 1
                if active:
                    return 1
            if msg in (WM_RBUTTONDOWN, WM_RBUTTONUP, WM_MBUTTONDOWN, WM_MBUTTONUP) and active:
                return 1                         # keep the desktop out of it
        except Exception as e:
            dbg(f"hook error {e}")
        return u32.CallNextHookEx(None, code, wparam, lparam)

    def start(self):
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self):
        self.hook = u32.SetWindowsHookExW(WH_MOUSE_LL, ctypes.cast(self._proc, ctypes.c_void_p),
                                          k32.GetModuleHandleW(None), 0)
        dbg(f"hook installed {self.hook}")
        if not self.hook:
            print("SetWindowsHookExW failed", ctypes.GetLastError(), flush=True)
            return
        msg = wt.MSG()
        while u32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            u32.TranslateMessage(ctypes.byref(msg))
            u32.DispatchMessageW(ctypes.byref(msg))

    def stop(self):
        if self.hook:
            u32.UnhookWindowsHookEx(self.hook)
            self.hook = None


# ------------------------------------------------------------------ main
def find_window_by_pid(pid):
    hits = []

    def cb(h, l):
        if not u32.IsWindowVisible(h):
            return True
        p = wt.DWORD(); u32.GetWindowThreadProcessId(h, ctypes.byref(p))
        if p.value != pid:
            return True
        b = ctypes.create_unicode_buffer(256)
        u32.GetClassNameW(h, b, 256)
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


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--pid", type=int)
    g.add_argument("--hwnd", type=lambda s: int(s, 0))
    ap.add_argument("--interval", type=float, default=0.25)
    ap.add_argument("--min-gap", type=int, default=18)
    ap.add_argument("--dry-run", action="store_true", help="print holes, never touch the window")
    ap.add_argument("--no-clicks", action="store_true", help="do not install the mouse hook")
    a = ap.parse_args()

    hwnd = a.hwnd or find_window_by_pid(a.pid)
    if not hwnd:
        print("no Chromium window found")
        return 1
    print(f"target hwnd={hwnd} rect={window_rect(hwnd)}", flush=True)

    uia = UiaWorker(hwnd)
    uia.start()
    guard = None
    if not (a.dry_run or a.no_clicks):
        guard = ClickGuard(hwnd)
        guard.start()

    def clear(why):
        nonlocal cleared, last_sig, candidate
        if not cleared:
            u32.SetWindowRgn(hwnd, None, True)
            cleared = True
            print(f"holes cleared ({why})", flush=True)
        last_sig = candidate = None
        if guard:
            guard.set_holes([])

    last_sig = None
    candidate = None
    applied_win = None
    cleared = True
    try:
        while True:
            if not u32.IsWindow(hwnd):
                print("target window gone", flush=True)
                break
            if u32.IsIconic(hwnd) or not u32.IsWindowVisible(hwnd):
                clear("minimized/hidden")
                time.sleep(a.interval)
                continue

            win = window_rect(hwnd)
            # cheap, non-blocking guards first: fullscreen or a moving window means no holes
            if nc_top_of(hwnd, win) < 20:
                clear("fullscreen")
                applied_win = win
                time.sleep(a.interval)
                continue
            if win != applied_win:
                clear("window moved")
                applied_win = win

            sample = uia.latest()
            if not sample or sample[0] != win:
                uia.maybe_restart()
                clear("no fresh UIA sample")
                time.sleep(a.interval)
                continue
            _w, tabs, prot, _ts = sample

            band = strip_band(hwnd, tabs, prot, win)
            holes = compute_holes(tabs, prot, win, a.min_gap, band)
            sig = tuple(holes)

            if not holes:
                clear("no valid tab strip")
                time.sleep(a.interval)
                continue

            if sig != candidate:                  # debounce: same sample twice in a row
                candidate = sig
                time.sleep(a.interval)
                continue

            if sig != last_sig:
                last_sig = sig
                if a.dry_run:
                    print(f"tabs={len(tabs)} prot={len(prot)} holes={holes}", flush=True)
                else:
                    u32.SetWindowRgn(hwnd, build_region(win, holes), True)
                    cleared = False
                    print(f"tabs={len(tabs)} prot={len(prot)} holes={len(holes)} "
                          f"band={band} first={holes[0]}", flush=True)
            if guard:
                guard.set_holes(holes)
            time.sleep(a.interval)
    except KeyboardInterrupt:
        pass
    finally:
        if guard:
            guard.stop()
        if not a.dry_run:
            uia.stop()
        if not a.dry_run and u32.IsWindow(hwnd):
            u32.SetWindowRgn(hwnd, None, True)
        print("region reset", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
