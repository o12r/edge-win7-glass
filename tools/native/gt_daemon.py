"""
gt_daemon.py - background service for the glass title bar.

One process that
  * watches for Chromium browser windows and attaches the glass bar to each of them,
  * serves a settings page on http://127.0.0.1:8721 (edit settings.json from the browser),
  * sits in the notification area (tray menu: settings / pause / autostart / quit).

usage
  pythonw tools/native/gt_daemon.py          # start (or just: no console window)
  python  tools/native/gt_daemon.py --console
  python  tools/native/gt_daemon.py --quit   # ask the running instance to exit
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import json
import os
import re
import subprocess
import sys
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import glass_titlebar as gt  # noqa: E402
import gt_i18n as i18n       # noqa: E402

u32 = ctypes.windll.user32
k32 = ctypes.windll.kernel32
shell32 = ctypes.windll.shell32
u32.SetProcessDPIAware()

APP_DATA = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "edge-win7-glass")
os.makedirs(APP_DATA, exist_ok=True)
LOG_PATH = os.path.join(APP_DATA, "daemon.log")
MUTEX = "Local\\edge-win7-glass-daemon"

BROWSERS = {"msedge.exe", "chrome.exe", "brave.exe", "vivaldi.exe",
            "chromium.exe", "opera.exe", "yandex.exe", "thorium.exe"}
WM_TRAY, WM_RELOAD = 0x8001, 0x8002


def _setup_win32():
    """The 64-bit handles come back truncated unless restype/argtypes are set explicitly."""
    CB = ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
    u32.EnumWindows.argtypes = [CB, wt.LPARAM]
    u32.IsWindowVisible.argtypes = [wt.HWND]
    u32.IsWindow.argtypes = [wt.HWND]
    u32.IsWindowVisible.restype = wt.BOOL
    u32.IsWindow.restype = wt.BOOL
    u32.GetClassNameW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
    u32.GetWindowTextW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
    # No argtypes for GetWindowRect / GetCursorPos: glass_titlebar defines its own RECT/POINT
    # and passes those, and ctypes rejects a pointer to a *different* Structure class.
    u32.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.POINTER(wt.DWORD)]
    u32.SetForegroundWindow.argtypes = [wt.HWND]
    k32.GetModuleHandleW.restype = wt.HMODULE
    # NOTE: no RegisterClassW argtypes here -- glass_titlebar passes its OWN WNDCLASS struct,
    # and ctypes rejects a pointer to a different Structure type.
    u32.CreateWindowExW.argtypes = [wt.DWORD, wt.LPCWSTR, wt.LPCWSTR, wt.DWORD,
                                    ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                    wt.HWND, wt.HMENU, wt.HINSTANCE, ctypes.c_void_p]
    u32.CreateWindowExW.restype = wt.HWND
    u32.DefWindowProcW.argtypes = [wt.HWND, ctypes.c_uint, wt.WPARAM, wt.LPARAM]
    u32.DefWindowProcW.restype = ctypes.c_ssize_t
    u32.LoadIconW.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    u32.LoadIconW.restype = wt.HICON
    u32.CreatePopupMenu.restype = wt.HMENU
    u32.AppendMenuW.argtypes = [wt.HMENU, wt.UINT, ctypes.c_size_t, wt.LPCWSTR]
    u32.AppendMenuW.restype = wt.BOOL
    u32.TrackPopupMenu.argtypes = [wt.HMENU, wt.UINT, ctypes.c_int, ctypes.c_int,
                                   ctypes.c_int, wt.HWND, ctypes.c_void_p]
    u32.TrackPopupMenu.restype = ctypes.c_int
    u32.DestroyMenu.argtypes = [wt.HMENU]
    u32.DestroyMenu.restype = wt.BOOL
    u32.GetMessageW.argtypes = [ctypes.POINTER(wt.MSG), wt.HWND, wt.UINT, wt.UINT]
    u32.GetMessageW.restype = wt.BOOL
    u32.TranslateMessage.argtypes = [ctypes.POINTER(wt.MSG)]
    u32.DispatchMessageW.argtypes = [ctypes.POINTER(wt.MSG)]
    u32.DispatchMessageW.restype = ctypes.c_ssize_t
    u32.PostQuitMessage.argtypes = [ctypes.c_int]
    u32.PostMessageW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
    u32.PostMessageW.restype = wt.BOOL
    shell32.Shell_NotifyIconW.argtypes = [wt.DWORD, ctypes.POINTER(NOTIFYICONDATAW)]
    shell32.Shell_NotifyIconW.restype = wt.BOOL


# WNDCLASS / NOTIFYICONDATAW are referenced by _setup_win32, so it runs after they exist.


def log(msg):
    line = f"{time.strftime('%H:%M:%S')} {msg}"
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass
    if sys.stdout and sys.stdout.isatty():
        print(line, flush=True)


# ------------------------------------------------------------------ win32 helpers
def process_exe(hwnd):
    pid = wt.DWORD()
    u32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    h = k32.OpenProcess(0x1000, False, pid)         # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(1024)
        size = wt.DWORD(1024)
        if k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
            return os.path.basename(buf.value).lower()
    finally:
        k32.CloseHandle(h)
    return ""


def process_path(hwnd):
    """Full executable path of the process that owns `hwnd` (to relaunch it later)."""
    pid = wt.DWORD()
    u32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    h = k32.OpenProcess(0x1000, False, pid)         # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(1024)
        size = wt.DWORD(1024)
        if k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
            return buf.value
    finally:
        k32.CloseHandle(h)
    return ""


def process_user_data_dir(hwnd):
    """`--user-data-dir` value of the process owning `hwnd`, or None (default profile)."""
    pid = wt.DWORD()
    u32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    try:
        r = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command",
             f"(Get-CimInstance Win32_Process -Filter 'ProcessId={pid.value}').CommandLine"],
            capture_output=True, text=True, timeout=8)
        m = re.search(r"--user-data-dir=([\"']?)([^\"' ]+)", r.stdout)
        if m:
            return m.group(2)
    except Exception:
        pass
    return None


def window_class(h):
    b = ctypes.create_unicode_buffer(256)
    u32.GetClassNameW(h, b, 256)
    return b.value


def window_title(h):
    b = ctypes.create_unicode_buffer(512)
    u32.GetWindowTextW(h, b, 512)
    return b.value


def browser_windows():
    out = []

    def cb(h, l):
        if not u32.IsWindowVisible(h):
            return True
        if not window_class(h).startswith("Chrome_WidgetWin_1"):
            return True
        r = gt.RECT()
        u32.GetWindowRect(h, ctypes.byref(r))
        if r.right - r.left < 400 or r.bottom - r.top < 200:
            return True
        if process_exe(h) not in BROWSERS:
            return True
        out.append(h)
        return True

    CB = ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
    u32.EnumWindows(CB(cb), 0)
    return out


def autostart_cmd():
    exe = sys.executable.replace("python.exe", "pythonw.exe")
    return f'"{exe}" "{os.path.abspath(__file__)}"'


def set_autostart(on):
    import winreg
    key = r"Software\Microsoft\Windows\CurrentVersion\Run"
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key) as k:
        if on:
            winreg.SetValueEx(k, "EdgeWin7Glass", 0, winreg.REG_SZ, autostart_cmd())
        else:
            try:
                winreg.DeleteValue(k, "EdgeWin7Glass")
            except FileNotFoundError:
                pass


def autostart_state():
    import winreg
    key = r"Software\Microsoft\Windows\CurrentVersion\Run"
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key) as k:
            winreg.QueryValueEx(k, "EdgeWin7Glass")
            return True
    except OSError:
        return False


# ------------------------------------------------------------------ tray icon
class GUID(ctypes.Structure):
    _fields_ = [("Data1", wt.DWORD), ("Data2", wt.WORD), ("Data3", wt.WORD),
                ("Data4", ctypes.c_ubyte * 8)]


class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [("cbSize", wt.DWORD), ("hWnd", wt.HWND), ("uID", wt.UINT),
                ("uFlags", wt.UINT), ("uCallbackMessage", wt.UINT), ("hIcon", wt.HICON),
                ("szTip", wt.WCHAR * 128), ("dwState", wt.DWORD), ("dwStateMask", wt.DWORD),
                ("szInfo", wt.WCHAR * 256), ("uVersion", wt.UINT),
                ("szInfoTitle", wt.WCHAR * 64), ("dwInfoFlags", wt.DWORD),
                ("guidItem", GUID), ("hBalloonIcon", wt.HICON)]


NIF_MESSAGE, NIF_ICON, NIF_TIP = 1, 2, 4
MF_STRING, MF_CHECKED, MF_SEPARATOR, MF_GRAYED = 0, 8, 0x800, 1
TPM_RETURNCMD, TPM_RIGHTBUTTON = 0x100, 0x02
WM_COMMAND, WM_DESTROY = 0x0111, 0x0002
WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wt.HWND, ctypes.c_uint, wt.WPARAM, wt.LPARAM)


class WNDCLASS(ctypes.Structure):
    _fields_ = [("style", ctypes.c_uint), ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int), ("hInstance", wt.HINSTANCE), ("hIcon", wt.HICON),
                ("hCursor", wt.HANDLE), ("hbrBackground", wt.HBRUSH), ("lpszMenuName", wt.LPCWSTR),
                ("lpszClassName", wt.LPCWSTR)]


# (command id, i18n key) -- a `None` key draws a separator.
MENU_ITEMS = [
    (1, "menu_settings"),
    (2, None),
    (20, "menu_pause"),
    (21, "menu_autostart"),
    (4, None),
    (30, "menu_quit"),
]


class Tray:
    def __init__(self, daemon):
        self.d = daemon
        self.hwnd = None
        self.data = None
        self._proc = WNDPROC(self._wndproc)
        self._menu = None

    def create(self):
        inst = k32.GetModuleHandleW(None)
        wc = WNDCLASS()
        wc.lpfnWndProc = self._proc
        wc.hInstance = inst
        wc.lpszClassName = "GlassTitlebarTray"
        u32.RegisterClassW(ctypes.byref(wc))
        self.hwnd = u32.CreateWindowExW(0, "GlassTitlebarTray", "Edge Win7 Glass", 0,
                                        0, 0, 0, 0, None, None, inst, None)
        if not self.hwnd:
            raise ctypes.WinError(ctypes.GetLastError())
        nid = NOTIFYICONDATAW()
        nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        nid.hWnd = self.hwnd
        nid.uID = 1
        nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
        nid.uCallbackMessage = WM_TRAY
        nid.hIcon = u32.LoadIconW(None, 32512)          # IDI_APPLICATION
        nid.szTip = "Edge Win7 Glass"
        shell32.Shell_NotifyIconW(0, ctypes.byref(nid))  # NIM_ADD
        self.data = nid
        return self.hwnd

    def set_tip(self, text):
        if not self.data:
            return
        self.data.szTip = text[:127]
        self.data.uFlags = NIF_TIP
        shell32.Shell_NotifyIconW(1, ctypes.byref(self.data))   # NIM_MODIFY

    def destroy(self):
        if self.data:
            shell32.Shell_NotifyIconW(2, ctypes.byref(self.data))   # NIM_DELETE
            self.data = None

    def _show_menu(self):
        m = u32.CreatePopupMenu()
        self._menu = m
        paused = self.d.paused
        autostart = autostart_state()
        for mid, key in MENU_ITEMS:
            if key is None:
                u32.AppendMenuW(m, MF_SEPARATOR, 0, None)
                continue
            flags = MF_STRING
            text = i18n.t(self.d.lang, key)
            if mid == 20:
                text = i18n.t(self.d.lang, "menu_resume" if paused else "menu_pause")
                flags |= MF_CHECKED if paused else 0
            if mid == 21 and autostart:
                flags |= MF_CHECKED
            u32.AppendMenuW(m, flags, mid, text)
        p = gt.POINT()
        u32.GetCursorPos(ctypes.byref(p))
        u32.SetForegroundWindow(self.hwnd)
        cmd = u32.TrackPopupMenu(m, TPM_RETURNCMD | TPM_RIGHTBUTTON, p.x, p.y, 0, self.hwnd, None)
        u32.DestroyMenu(m)
        self._menu = None
        if cmd:
            self.d.command(cmd)

    def _wndproc(self, h, msg, wp, lp):
        if msg == WM_TRAY:
            ev = lp & 0xFFFF
            if ev in (0x0205, 0x0204):        # WM_RBUTTONUP / WM_RBUTTONDOWN
                self._show_menu()
            elif ev == 0x0202:                # WM_LBUTTONUP
                self.d.open_settings()
        elif msg == WM_COMMAND:
            self.d.command(wp & 0xFFFF)
        elif msg == WM_DESTROY:
            u32.PostQuitMessage(0)
        return u32.DefWindowProcW(h, msg, wp, lp)

    def pump(self):
        msg = wt.MSG()
        while u32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            u32.TranslateMessage(ctypes.byref(msg))
            u32.DispatchMessageW(ctypes.byref(msg))


# ------------------------------------------------------------------ daemon
class Attach:
    __slots__ = ("hwnd", "stop", "thread", "title")

    def __init__(self, hwnd, stop, thread, title):
        self.hwnd, self.stop, self.thread, self.title = hwnd, stop, thread, title


class Daemon:
    def __init__(self):
        self.cfg = gt.Settings()
        self.lang_setting = self.cfg.lang            # "auto" / "zh" / "en"
        self.lang = i18n.resolve(self.lang_setting)  # effective language
        self.attached = {}
        self.failed = {}
        self.paused = False
        self.stopping = False
        self.lock = threading.Lock()
        self.tray = None
        self.httpd = None
        self.http_port = 0

    # ---------------- attach management
    def attach(self, hwnd):
        if self.stopping:
            return
        title = window_title(hwnd)
        stop = threading.Event()
        scale = (u32.GetDpiForWindow(hwnd) or 96) / 96.0

        def run():
            try:
                gt.attach_loop(hwnd, self.cfg, scale, stop_event=stop,
                               log=lambda m: log(f"[{hwnd:x}] {m}"))
            except Exception as e:
                self.failed[hwnd] = time.time()
                log(f"attach crashed {hwnd:x}: {e!r}")

        th = threading.Thread(target=run, name=f"attach-{hwnd}", daemon=True)
        th.start()
        with self.lock:
            self.attached[hwnd] = Attach(hwnd, stop, th, title)
        log(f"attach {hwnd:x} {title[:50]!r}")

    def detach(self, hwnd):
        with self.lock:
            a = self.attached.pop(hwnd, None)
        if a:
            a.stop.set()
            a.thread.join(timeout=3)
            log(f"detach {hwnd:x}")
        if u32.IsWindow(hwnd):
            u32.SetWindowRgn(hwnd, None, True)
            u32.RedrawWindow(hwnd, None, None, 0x0001 | 0x0080 | 0x0100)

    def detach_all(self):
        for h in list(self.attached.keys()):
            self.detach(h)

    def scan(self):
        if self.paused or self.stopping:
            return
        live = browser_windows()
        only = os.environ.get("GT_ONLY_HWND")        # test hook: manage just one window
        if only:
            live = [h for h in live if h == int(only, 0)]
        with self.lock:
            known = set(self.attached.keys())
            dead = [h for h, a in self.attached.items() if not u32.IsWindow(h) or not a.thread.is_alive()]
        for h in dead:
            self.detach(h)
        for h in live:
            if h not in known:
                if time.time() - self.failed.get(h, 0) < 30:
                    continue
                try:
                    self.attach(h)
                except Exception as e:
                    self.failed[h] = time.time()
                    log(f"attach failed {h:x}: {e!r}")
        self.refresh_tip()

    def refresh_tip(self):
        if self.tray:
            if self.paused:
                state = i18n.t(self.lang, "tip_paused")
            else:
                state = i18n.t(self.lang, "tip_windows", n=len(self.attached))
            self.tray.set_tip(f"Edge Win7 Glass · {state}")

    # ---------------- settings / actions
    def apply_settings(self, new):
        path = self.cfg.path
        data = dict(self.cfg.data)
        for k, v in new.items():
            if k in gt.Settings.DEFAULTS:
                data[k] = v
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        if "autostart" in new:
            set_autostart(bool(new["autostart"]))
        if "lang" in new:
            self.lang_setting = new["lang"] if new["lang"] in i18n.LANGS else "auto"
            self.lang = i18n.resolve(self.lang_setting)
        self.cfg.data.update(data)
        log(f"settings saved: {new}")
        # Hot-reconnect (detach + re-attach) leaves stale overlay/region state behind, so
        # applying settings now does a clean restart: close the browsers (saving their
        # session), relaunch the daemon, and reopen the browsers with their tabs restored.
        # Delayed so the HTTP "ok" response reaches the settings page before os._exit kills us.
        threading.Timer(0.5, self.restart_everything).start()

    def restart_everything(self):
        """Clean restart: close browsers (saving session), relaunch daemon, reopen browsers.

        Replaces the old detach+re-attach, which left the touch overlay / window region in a
        stale state (clicks landing on a dead overlay, a hole that stayed cut). A full process
        restart starts from a clean slate.
        """
        self.stopping = True            # the watcher must not re-attach while we tear down
        # Collect the browsers we manage (before detach_all clears `attached`), so GT_ONLY_HWND
        # restarts only that window's browser and never touches unrelated browser windows.
        paths = []
        seen = set()
        for h in list(self.attached.keys()):
            p = process_path(h)
            if not p or p in seen:
                continue
            seen.add(p)
            paths.append([p, process_user_data_dir(h)])
        self.detach_all()
        restore = os.path.join(APP_DATA, "restore.json")
        try:
            with open(restore, "w", encoding="utf-8") as f:
                json.dump(paths, f)
        except OSError:
            pass
        log(f"closing {len(paths)} browser(s) for restart")
        exes = {p[0] for p in paths}
        # Graceful close (WM_CLOSE) so Chromium saves the session; --restore-last-session
        # needs the session file written on exit. Close every window of the target browsers.
        for h in browser_windows():
            if process_path(h) in exes:
                u32.PostMessageW(h, 0x0010, 0, 0)      # WM_CLOSE
        for _ in range(40):                            # wait for the windows to close
            if not any(process_path(h) in exes for h in browser_windows()):
                break
            time.sleep(0.1)
        time.sleep(2.0)                                # let the process finish writing its session
        self.relaunch_daemon()

    def relaunch_daemon(self):
        exe = sys.executable.replace("python.exe", "pythonw.exe")
        cmd = f'"{exe}" "{os.path.abspath(__file__)}"'
        subprocess.Popen(cmd, shell=True)
        log("daemon relaunched; exiting")
        os._exit(0)

    def restore_browsers(self):
        """Reopen the browsers we closed, restoring their last session (tabs)."""
        restore = os.path.join(APP_DATA, "restore.json")
        if not os.path.exists(restore):
            return
        try:
            with open(restore, encoding="utf-8") as f:
                paths = json.load(f)
            os.remove(restore)
        except (OSError, ValueError):
            return
        for item in paths:
            exe = item[0] if isinstance(item, (list, tuple)) else item
            udd = item[1] if isinstance(item, (list, tuple)) and len(item) > 1 else None
            cmd = [exe]
            if udd:
                cmd.append(f"--user-data-dir={udd}")
            cmd.append("--restore-last-session")
            try:
                subprocess.Popen(cmd, creationflags=0x08000000)
                log(f"restored browser {exe}" + (f" (profile {udd})" if udd else ""))
            except Exception as e:
                log(f"restore browser failed {exe}: {e!r}")

    def command(self, cid):
        if cid == 1:
            self.open_settings()
        elif cid == 20:
            self.paused = not self.paused
            if self.paused:
                self.detach_all()
            log(f"paused={self.paused}")
            self.scan()
        elif cid == 21:
            self.apply_settings({"autostart": not autostart_state()})
        elif cid == 30:
            self.quit()
        self.refresh_tip()

    def open_settings(self):
        url = f"http://127.0.0.1:{self.http_port}/"
        log(f"open settings {url}")
        try:
            os.startfile(url)
        except OSError:
            subprocess.Popen(["cmd", "/c", "start", "", url], creationflags=0x08000000)

    def status(self):
        with self.lock:
            wins = [{"hwnd": f"{h:x}", "title": a.title,
                     "alive": a.thread.is_alive()} for h, a in self.attached.items()]
        return {"port": self.http_port, "paused": self.paused,
                "autostart": autostart_state(), "windows": wins,
                "lang": self.lang, "auto_lang": i18n.system_lang(),
                "settings": self.cfg.data}

    # ---------------- http
    def start_http(self):
        if self.httpd:
            try:
                self.httpd.shutdown()
                self.httpd.server_close()
            except Exception:
                pass
        port = int(self.cfg.port)
        try:
            self.httpd = ThreadingHTTPServer(("127.0.0.1", port), make_handler(self))
        except OSError as e:
            log(f"settings port {port} busy: {e!r}; trying {port + 1}")
            port += 1
            self.httpd = ThreadingHTTPServer(("127.0.0.1", port), make_handler(self))
        self.http_port = port
        threading.Thread(target=self.httpd.serve_forever, name="http", daemon=True).start()
        log(f"settings page on http://127.0.0.1:{port}/")

    # ---------------- lifecycle
    def run(self):
        mutex = k32.CreateMutexW(None, False, MUTEX)
        if k32.GetLastError() == 183:              # ERROR_ALREADY_EXISTS
            log("already running; opening settings page")
            try:
                url = f"http://127.0.0.1:{int(self.cfg.port)}/"
                os.startfile(url)
            except Exception:
                pass
            return 0
        self._mutex = mutex
        set_autostart(bool(self.cfg.autostart))
        self.restore_browsers()         # reopen browsers closed by a settings restart
        self.start_http()
        threading.Thread(target=self._watcher, name="watcher", daemon=True).start()
        self.tray = Tray(self)
        self.tray.create()
        self.refresh_tip()
        log("daemon started")
        try:
            self.tray.pump()
        finally:
            self.quit()
        return 0

    def _watcher(self):
        while True:
            try:
                self.scan()
            except Exception as e:
                log(f"scan error {e!r}")
            time.sleep(1.0)

    def quit(self):
        log("quit")
        self.stopping = True           # the watcher must not re-attach while we tear down
        self.detach_all()
        if self.tray:
            self.tray.destroy()
        if self.httpd:
            try:
                self.httpd.shutdown()
            except Exception:
                pass
        u32.PostQuitMessage(0)
        # make sure region holes never outlive us
        os._exit(0)


# ------------------------------------------------------------------ settings page
PAGE = r"""<!doctype html><html lang="__HTML_LANG__" class="pending"><meta charset="utf-8">
<title>Edge Win7 Glass · Settings</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
 html.pending body{opacity:0}
 :root{color-scheme:light dark;
   --fg:#1b2530; --sub:#5f7284; --h2:#5a6d80; --ul:#3d4f61; --muted:#5b6b7c;
   --bg:linear-gradient(160deg,#f6f9fc,#e8eef6 60%);
   --card:rgba(255,255,255,.75); --card-bd:rgba(20,40,60,.12);
   --row-bd:rgba(20,40,60,.09);
   --input-bg:#fff; --input-fg:#1b2530; --input-bd:rgba(20,40,60,.22);
   --ghost-bg:rgba(20,40,60,.07); --ghost-fg:#2b3d4e;
   --toast-bg:#e4f7ec; --toast-bd:#8fd8b1; --toast-fg:#186b42;
 }
 @media (prefers-color-scheme:dark){
  :root{--fg:#e6edf5; --sub:#8fa3b8; --h2:#9fb4c9; --ul:#b9c9d8; --muted:#7f93a8;
   --bg:linear-gradient(160deg,#1b2530,#0f151c 60%);
   --card:rgba(255,255,255,.06); --card-bd:rgba(255,255,255,.10);
   --row-bd:rgba(255,255,255,.06);
   --input-bg:rgba(0,0,0,.35); --input-fg:#e6edf5; --input-bd:rgba(255,255,255,.14);
   --ghost-bg:rgba(255,255,255,.10); --ghost-fg:#dce8f4;
   --toast-bg:#1d3b2a; --toast-bd:#2f6b4a; --toast-fg:#b9f5d0;
  }
 }
 *{box-sizing:border-box}
 body{margin:0;font:14px/1.5 "Segoe UI","Microsoft YaHei",sans-serif;
      background:var(--bg);color:var(--fg);min-height:100vh;padding:32px}
 .wrap{max-width:760px;margin:0 auto}
 h1{font-size:20px;font-weight:600;margin:0 0 4px}
 .sub{color:var(--sub);margin-bottom:24px}
 .card{background:var(--card);border:1px solid var(--card-bd);
       border-radius:12px;padding:18px 20px;margin-bottom:16px;backdrop-filter:blur(8px)}
 .card h2{font-size:13px;letter-spacing:.08em;text-transform:uppercase;color:var(--h2);margin:0 0 14px}
 .row{display:flex;align-items:center;justify-content:space-between;gap:16px;padding:9px 0;
      border-bottom:1px solid var(--row-bd)}
 .row:last-child{border-bottom:0}
 .row label{flex:1}
 .hint{color:var(--muted);font-size:12px}
 input[type=number]{width:90px}
 input[type=number],select{background:var(--input-bg);color:var(--input-fg);border:1px solid var(--input-bd);
      border-radius:8px;padding:6px 8px}
 input[type=range]{width:220px}
 input[type=checkbox]{width:18px;height:18px;accent-color:#4aa3ff}
 .btns{display:flex;gap:10px;margin-top:18px}
 button{border:0;border-radius:9px;padding:9px 16px;font-size:14px;cursor:pointer;
        background:#2b6cb0;color:#fff}
 button.ghost{background:var(--ghost-bg);color:var(--ghost-fg)}
 button.danger{background:#8c2b2b}
 button:hover{filter:brightness(1.12)}
 .pill{display:inline-block;padding:2px 9px;border-radius:999px;font-size:12px;
       background:rgba(90,200,140,.18);color:#2f8f5f;margin-left:8px}
 .pill.off{background:var(--ghost-bg);color:var(--sub)}
 ul{margin:8px 0 0;padding-left:18px;color:var(--ul)}
 .card.off{opacity:.55}
 #toast{position:fixed;left:50%;bottom:26px;transform:translateX(-50%);background:var(--toast-bg);
        border:1px solid var(--toast-bd);color:var(--toast-fg);padding:9px 16px;border-radius:10px;opacity:0;
        transition:opacity .25s;pointer-events:none}
 #toast.show{opacity:1}
 @media (max-width:760px){
   body{padding:16px}
   .card{padding:14px}
   .row{flex-direction:column;align-items:flex-start;gap:6px}
   input[type=range]{width:100%}
 }
</style>
<div class="wrap">
 <h1>Edge Win7 Glass <span class="pill" id="state" data-i18n="loading">读取中…</span></h1>
 <div class="sub"><span data-i18n="subtitle"></span> <code>%APPDATA%\edge-win7-glass\settings.json</code></div>

 <div class="card">
  <h2 data-i18n="sec_appearance">外观</h2>
  <div class="row"><label><span data-i18n="frame_px"></span> <span class="hint" data-i18n="frame_px_hint"></span></label>
   <input type="number" id="frame_px" min="1" max="16" step="1"></div>
  <div class="row"><label><span data-i18n="corner_px"></span> <span class="hint" data-i18n="corner_px_hint"></span></label>
   <input type="number" id="corner_px" min="0" max="24" step="1"></div>
  <div class="row"><label><span data-i18n="gl_buttons"></span><div class="hint" data-i18n="gl_buttons_hint"></div></label>
   <input type="checkbox" id="gl_buttons"></div>
  <div class="row"><label><span data-i18n="btn_pad_right_px"></span> <span class="hint" data-i18n="btn_pad_right_px_hint"></span></label>
   <input type="number" id="btn_pad_right_px" min="0" max="30" step="1"></div>
  <div class="row"><label><span data-i18n="btn_min_px"></span> <span class="hint" data-i18n="btn_min_px_hint"></span></label>
   <input type="number" id="btn_min_px" min="10" max="80" step="1"></div>
  <div class="row"><label><span data-i18n="btn_close_px"></span> <span class="hint" data-i18n="btn_close_px_hint"></span></label>
   <input type="number" id="btn_close_px" min="10" max="120" step="1"></div>
  <div class="row"><label><span data-i18n="btn_top_px"></span> <span class="hint" data-i18n="btn_top_px_hint"></span></label>
   <input type="number" id="btn_top_px" min="0" max="40" step="1"></div>
  <div class="row"><label><span data-i18n="btn_h_px"></span> <span class="hint" data-i18n="btn_h_px_hint"></span></label>
   <input type="number" id="btn_h_px" min="0" max="120" step="1"></div>
  <div class="row"><label><span data-i18n="btn_h_fix_px"></span> <span class="hint" data-i18n="btn_h_fix_px_hint"></span></label>
   <input type="number" id="btn_h_fix_px" min="-40" max="40" step="1"></div>
 </div>

 <div class="card">
  <h2 data-i18n="sec_language">语言</h2>
  <div class="row"><label><span data-i18n="lang"></span> <span class="hint" data-i18n="lang_hint"></span></label>
   <select id="lang">
    <option value="auto" data-i18n="lang_auto"></option>
    <option value="zh" data-i18n="lang_zh"></option>
    <option value="en" data-i18n="lang_en"></option>
   </select></div>
 </div>

 <div class="card">
  <h2 data-i18n="sec_daemon">守护</h2>
  <div class="row"><label><span data-i18n="autostart"></span><div class="hint" data-i18n="autostart_hint"></div></label>
   <input type="checkbox" id="autostart"></div>
  <div class="row"><label><span data-i18n="port"></span></label><input type="number" id="port" min="1024" max="65535"></div>
 </div>

 <div class="card">
  <h2 data-i18n="sec_windows">当前接管的窗口</h2>
  <ul id="windows"><li>—</li></ul>
  <div class="btns">
   <button id="save" data-i18n="btn_save">保存并应用</button>
   <button class="ghost" id="refresh" data-i18n="btn_refresh">刷新</button>
   <button class="danger" id="quit" data-i18n="btn_quit">退出守护进程</button>
  </div>
 </div>
</div>
<div id="toast"></div>
<script>
const I18N=__I18N__;
const F=['frame_px','corner_px','gl_buttons','btn_pad_right_px','btn_min_px','btn_close_px','btn_top_px','btn_h_px','btn_h_fix_px','lang','autostart','port'];
let setting='__LANG_SETTING__', sysLang='__LANG__', lang='__LANG__', last=null, touched=false;
function T(k){const d=I18N[lang]||I18N.en;return d[k]!==undefined?d[k]:(I18N.en[k]!==undefined?I18N.en[k]:k);}
function FMT(k,a){return T(k).replace(/\{(\w+)\}/g,(m,g)=>a[g]!==undefined?a[g]:m);}
function esc(s){return String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));}
function applyI18n(){
  document.querySelectorAll('[data-i18n]').forEach(el=>{el.textContent=T(el.dataset.i18n);});
  document.title=T('page_title');
  document.documentElement.lang = lang==='zh'?'zh-CN':'en';
  const sel=document.getElementById('lang'); if(sel) sel.value=setting;
  paintStatus();
}
function paintStatus(){
  const st=document.getElementById('state'); const ul=document.getElementById('windows');
  if(!last){st.textContent=T('loading');st.className='pill off';return;}
  st.textContent = last.paused? T('state_paused') : FMT('state_windows',{n:last.windows.length});
  st.className='pill'+((last.paused||!last.windows.length)?' off':'');
  ul.innerHTML = last.windows.length
    ? last.windows.map(w=>`<li>${esc(w.title||T('no_title'))} <span class="hint">hwnd ${esc(w.hwnd)}</span></li>`).join('')
    : '<li>—</li>';
}
function toast(t){const e=document.getElementById('toast');e.textContent=t;e.classList.add('show');
  setTimeout(()=>e.classList.remove('show'),1600);}
async function load(fill=true){
  const r=await fetch('/api/status'); const j=await r.json(); last=j;
  const s=j.settings||{}; sysLang=j.auto_lang||'en';
  if(!touched){setting=s.lang||'auto';}
  lang = setting==='auto'? sysLang : setting;
  if(fill && !touched) for(const k of F){const el=document.getElementById(k);if(!el)continue;
    if(el.type==='checkbox')el.checked=!!s[k];else el.value=s[k];}
  applyI18n();
}
document.getElementById('lang').onchange=e=>{
  touched=true; setting=e.target.value; lang = setting==='auto'? sysLang : setting; applyI18n();
};
document.getElementById('save').onclick=async()=>{
  const out={};
  for(const k of F){const el=document.getElementById(k);
    out[k]= el.type==='checkbox'?el.checked:(el.type==='number'?Number(el.value):el.value);}
  const r=await fetch('/api/settings',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(out)});
  if(r.ok){touched=false;toast(T('toast_saved'));setTimeout(()=>load(true),1200);}else toast(T('toast_fail'));
};
document.getElementById('refresh').onclick=()=>load(true);
document.getElementById('quit').onclick=async()=>{
  if(!confirm(T('confirm_quit')))return;
  await fetch('/api/quit',{method:'POST'});
  document.body.innerHTML='<p style="padding:40px">'+esc(T('quit_done'))+'</p>';
};
applyI18n();
document.documentElement.classList.remove('pending');
load(true);setInterval(()=>load(false),4000);
</script></html>
"""


def page_html(lang, setting):
    """Settings page for the effective `lang`; carries both tables so the picker can preview."""
    return (PAGE.replace("__HTML_LANG__", "zh-CN" if lang == "zh" else "en")
                .replace("__LANG_SETTING__", setting if setting in i18n.LANGS else "auto")
                .replace("__LANG__", lang)
                .replace("__I18N__", json.dumps(i18n.STRINGS, ensure_ascii=False)))


def make_handler(daemon):
    class Handler(BaseHTTPRequestHandler):
        def _send(self, code, body, ctype="application/json; charset=utf-8"):
            if isinstance(body, str):
                body = body.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path in ("/", "/index.html"):
                self._send(200, page_html(daemon.lang, daemon.lang_setting),
                           "text/html; charset=utf-8")
            elif self.path.startswith("/api/status"):
                self._send(200, json.dumps(daemon.status(), ensure_ascii=False))
            else:
                self._send(404, "{}")

        def do_POST(self):
            n = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(n) if n else b"{}"
            try:
                payload = json.loads(raw or b"{}")
            except ValueError:
                payload = {}
            if self.path.startswith("/api/settings"):
                try:
                    daemon.apply_settings(payload)
                    self._send(200, json.dumps({"ok": True}))
                except Exception as e:
                    log(f"apply settings failed {e!r}")
                    self._send(500, json.dumps({"ok": False, "error": str(e)}))
            elif self.path.startswith("/api/quit"):
                self._send(200, json.dumps({"ok": True}))
                threading.Thread(target=daemon.quit, daemon=True).start()
            elif self.path.startswith("/api/pause"):
                daemon.command(20)
                self._send(200, json.dumps({"ok": True}))
            else:
                self._send(404, "{}")

        def log_message(self, format, *args):
            pass

    return Handler


def main():
    _setup_win32()
    argv = sys.argv[1:]
    if "--quit" in argv:
        try:
            import urllib.request
            cfg = gt.Settings()
            urllib.request.urlopen(f"http://127.0.0.1:{cfg.port}/api/quit", data=b"{}", timeout=2)
            print("asked the daemon to quit")
        except Exception as e:
            print(f"daemon not reachable: {e}")
        return 0
    try:
        return Daemon().run()
    except Exception:
        log("FATAL\n" + traceback.format_exc())
        raise


if __name__ == "__main__":
    sys.exit(main())
