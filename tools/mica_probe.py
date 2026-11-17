"""
mica_probe.py - does Edge still have a *mica / translucent* title strip behind a feature flag?

Launches a throw-away Edge profile with the candidate features, maximizes it, screenshots,
and prints the RGB of the caption / tabstrip / toolbar bands so translucency is measurable
(a translucent strip varies with the desktop behind it; an opaque one is a flat colour).

usage: python mica_probe.py <tag> [feature flags...]
"""
import ctypes, ctypes.wintypes as wt, sys, time, subprocess, os, shutil

u32 = ctypes.windll.user32
u32.SetProcessDPIAware()
GWL_EXSTYLE = -20
CB = ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
SCRATCH = r"C:\Users\oscar\AppData\Local\hermes\cache\scratch"
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"


class RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


def th32(h):
    pid = wt.DWORD()
    u32.GetWindowThreadProcessId(h, ctypes.byref(pid))
    return pid.value


def window_for_pid(pid_set):
    hits = []

    def cb(h, l):
        if not u32.IsWindowVisible(h):
            return True
        b = ctypes.create_unicode_buffer(256)
        u32.GetClassNameW(h, b, 256)
        if b.value != "Chrome_WidgetWin_1":
            return True
        if u32.GetWindowLongW(h, GWL_EXSTYLE) & 0x80:
            return True
        if th32(h) in pid_set:
            r = RECT(); u32.GetWindowRect(h, ctypes.byref(r))
            hits.append((h, (r.right - r.left) * (r.bottom - r.top), (r.left, r.top, r.right, r.bottom)))
        return True

    u32.EnumWindows(CB(cb), 0)
    hits.sort(key=lambda x: -x[1])
    return hits


def child_pids(root):
    out = subprocess.run(["powershell", "-NoProfile", "-Command",
                          f"Get-CimInstance Win32_Process | Where-Object {{$_.ParentProcessId -eq {root}}} | "
                          f"Select-Object -ExpandProperty ProcessId"],
                         capture_output=True, text=True).stdout.split()
    return {root} | {int(x) for x in out if x.isdigit()}


def main():
    tag = sys.argv[1] if len(sys.argv) > 1 else "mica"
    feats = sys.argv[2:]
    prof = os.path.join(SCRATCH, f"edgeprof_{tag}")
    shutil.rmtree(prof, ignore_errors=True)
    args = [EDGE, f"--user-data-dir={prof}", "--no-first-run", "--no-default-browser-check",
            "--disable-sync", "--window-size=1400,900"]
    if feats:
        args.append("--enable-features=" + ",".join(feats))
    args.append("about:blank")
    p = subprocess.Popen(args)
    print("launched pid", p.pid, "features", feats, flush=True)

    hits = []
    for _ in range(40):
        time.sleep(0.5)
        hits = window_for_pid(child_pids(p.pid))
        if hits:
            break
    if not hits:
        print("no window appeared")
        p.kill()
        return 1
    h, area, rect = hits[0]
    print("window", h, rect, flush=True)
    u32.ShowWindow(h, 3)  # maximize
    u32.SetForegroundWindow(h)
    time.sleep(2.0)
    r = RECT(); u32.GetWindowRect(h, ctypes.byref(r))
    out = rf"{SCRATCH}\mica_{tag}.png"
    subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                    r"C:\Users\oscar\Projects\edge-win7-glass\tools\shotfull.ps1", out],
                   capture_output=True)
    print("saved", out, flush=True)

    from PIL import Image
    im = Image.open(out).convert("RGB")
    print("img", im.size)
    # vertical scan down the middle-right of the window: shows the bands
    for y in range(r.top + 2, min(r.top + 240, r.bottom), 12):
        row = [im.getpixel((x, y)) for x in (r.left + 300, r.left + 900, r.left + 1500, r.right - 300)]
        print(f"y={y - r.top:4d} {row}", flush=True)
    p.kill()
    return 0


if __name__ == "__main__":
    sys.exit(main())
