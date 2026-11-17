"""
launch_scratch.py - start an isolated Edge profile window and leave it running.

  python launch_scratch.py [tag] [exe]

Prints "<pid> <hwnd>" of the browser window it created, then exits (browser stays).
"""
import ctypes, ctypes.wintypes as wt, os, shutil, subprocess, sys, time

u32 = ctypes.windll.user32
u32.SetProcessDPIAware()
CB = ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
SCRATCH = r"C:\Users\oscar\AppData\Local\hermes\cache\scratch"
DEFAULT_EXE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"


def windows_for(pids):
    out = []

    def cb(h, l):
        if not u32.IsWindowVisible(h):
            return True
        b = ctypes.create_unicode_buffer(256)
        u32.GetClassNameW(h, b, 256)
        if not b.value.startswith("Chrome_WidgetWin_"):
            return True
        r = wt.RECT(); u32.GetWindowRect(h, ctypes.byref(r))
        if r.right - r.left < 300:
            return True
        t = ctypes.create_unicode_buffer(512)
        u32.GetWindowTextW(h, t, 512)
        pid = wt.DWORD()
        u32.GetWindowThreadProcessId(h, ctypes.byref(pid))
        if pid.value in pids:
            out.append((pid.value, h, t.value, (r.left, r.top, r.right, r.bottom)))
        return True

    u32.EnumWindows(CB(cb), 0)
    return out


def child_pids(root):
    r = subprocess.run(["powershell", "-NoProfile", "-Command",
                        f"(Get-CimInstance Win32_Process | Where-Object {{$_.ParentProcessId -eq {root}}}).ProcessId"],
                       capture_output=True, text=True).stdout.split()
    return {root} | {int(x) for x in r if x.isdigit()}


def main():
    tag = sys.argv[1] if len(sys.argv) > 1 else "probe"
    exe = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_EXE
    prof = os.path.join(SCRATCH, f"prof_{tag}")
    shutil.rmtree(prof, ignore_errors=True)
    args = [exe, f"--user-data-dir={prof}", "--no-first-run", "--no-default-browser-check",
            "--disable-sync", "--window-size=1500,900", "--window-position=120,120", "about:blank"]
    DETACHED = 0x00000008
    p = subprocess.Popen(args, creationflags=DETACHED, close_fds=True)
    print(f"launched {os.path.basename(exe)} root pid={p.pid} profile={prof}", flush=True)
    for _ in range(40):
        time.sleep(0.5)
        hits = windows_for(child_pids(p.pid))
        if hits:
            pid, h, title, rect = hits[0]
            print(f"WINDOW pid={pid} hwnd={h} rect={rect} title={title[:60]!r}", flush=True)
            return 0
    print("no window appeared", flush=True)
    return 1


if __name__ == "__main__":
    sys.exit(main())
