"""
ogprobe_inject.py - inject ogprobe.dll into a Chromium browser process.

  python ogprobe_inject.py <title-substring|pid>
  python ogprobe_inject.py --list

Writes ogprobe.ini before injecting (mode/top/delay from the CLI or the existing file).
"""
import ctypes, ctypes.wintypes as wt, os, sys, time

u32 = ctypes.windll.user32
k32 = ctypes.windll.kernel32
u32.SetProcessDPIAware()

GWL_EXSTYLE = -20
CB = ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
DLL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ogprobe.dll")
SCRATCH = r"C:\Users\oscar\AppData\Local\hermes\cache\scratch"

PROCESS_ALL = 0x1F0FFF
MEM_COMMIT_RESERVE = 0x3000
PAGE_RW = 0x04
MEM_RELEASE = 0x8000

u32.GetWindowLongW.restype = ctypes.c_long
k32.OpenProcess.restype = wt.HANDLE
k32.VirtualAllocEx.restype = ctypes.c_void_p
k32.GetModuleHandleW.restype = ctypes.c_void_p
k32.GetProcAddress.restype = ctypes.c_void_p
k32.CreateRemoteThread.restype = wt.HANDLE


def windows():
    out = []

    def cb(h, l):
        if not u32.IsWindowVisible(h):
            return True
        if u32.GetWindowLongW(h, GWL_EXSTYLE) & 0x80:
            return True
        b = ctypes.create_unicode_buffer(256)
        u32.GetClassNameW(h, b, 256)
        if not b.value.startswith("Chrome_WidgetWin_"):
            return True
        t = ctypes.create_unicode_buffer(512)
        u32.GetWindowTextW(h, t, 512)
        pid = wt.DWORD()
        u32.GetWindowThreadProcessId(h, ctypes.byref(pid))
        r = wt.RECT(); u32.GetWindowRect(h, ctypes.byref(r))
        out.append((h, t.value, pid.value, r.left, r.top, r.right - r.left, r.bottom - r.top))
        return True

    u32.EnumWindows(CB(cb), 0)
    return out


def kernel32_base(pid):
    TH32CS_SNAPMODULE = 0x8 | 0x10

    class MODULEENTRY32(ctypes.Structure):
        _fields_ = [("dwSize", wt.DWORD), ("th32ModuleID", wt.DWORD), ("th32ProcessID", wt.DWORD),
                    ("GlblcntUsage", wt.DWORD), ("ProccntUsage", wt.DWORD),
                    ("modBaseAddr", ctypes.c_void_p), ("modBaseSize", wt.DWORD),
                    ("hModule", wt.HMODULE), ("szModule", ctypes.c_char * 256),
                    ("szExePath", ctypes.c_char * 260)]

    snap = k32.CreateToolhelp32Snapshot(TH32CS_SNAPMODULE, pid)
    if snap in (0, -1, 0xFFFFFFFF):
        return None
    me = MODULEENTRY32()
    me.dwSize = ctypes.sizeof(me)
    base = None
    if k32.Module32First(snap, ctypes.byref(me)):
        while True:
            if me.szModule.lower() == b"kernel32.dll":
                base = me.modBaseAddr
                break
            if not k32.Module32Next(snap, ctypes.byref(me)):
                break
    k32.CloseHandle(snap)
    return base


def inject(pid):
    if not os.path.exists(DLL):
        print("missing", DLL, "- build it first")
        return 1
    h = k32.OpenProcess(PROCESS_ALL, False, pid)
    if not h:
        print(f"OpenProcess({pid}) failed err={k32.GetLastError()} (need same-user, non-elevated target?)")
        return 1
    local_k32 = k32.GetModuleHandleW("kernel32.dll")
    load_lib = k32.GetProcAddress(ctypes.c_void_p(local_k32), b"LoadLibraryW")
    remote_k32 = kernel32_base(pid)
    if not remote_k32:
        print("could not find kernel32 in target")
        return 1
    remote_load = ctypes.c_void_p(remote_k32 + (load_lib - local_k32))
    path = DLL.encode("utf-16-le") + b"\x00\x00"
    mem = k32.VirtualAllocEx(h, None, len(path), MEM_COMMIT_RESERVE, PAGE_RW)
    if not mem:
        print("VirtualAllocEx failed", k32.GetLastError())
        return 1
    written = ctypes.c_size_t()
    k32.WriteProcessMemory(h, ctypes.c_void_p(mem), path, len(path), ctypes.byref(written))
    th = k32.CreateRemoteThread(h, None, 0, remote_load, ctypes.c_void_p(mem), 0, None)
    if not th:
        print("CreateRemoteThread failed", k32.GetLastError())
        return 1
    k32.WaitForSingleObject(th, 8000)
    code = wt.DWORD()
    k32.GetExitCodeThread(th, ctypes.byref(code))
    print(f"LoadLibraryW in pid {pid} -> HMODULE 0x{code.value:X} "
          f"({'ok' if code.value else 'failed'})")
    k32.CloseHandle(th)
    k32.CloseHandle(h)
    return 0


def main():
    ws = windows()
    if "--list" in sys.argv or len(sys.argv) < 2:
        for h, t, pid, x, y, w, hh in ws:
            print(f"hwnd={h} pid={pid} {w}x{hh}@{x},{y} {t[:70]!r}")
        return 0

    # optional --mode/--top/--delay
    ini = {}
    for i, a in enumerate(sys.argv):
        if a.startswith("--") and i + 1 < len(sys.argv):
            ini[a[2:]] = sys.argv[i + 1]
    if ini:
        os.makedirs(os.path.dirname(os.path.join(SCRATCH, "x")), exist_ok=True)
        with open(os.path.join(SCRATCH, "ogprobe.ini"), "w") as f:
            for k, v in ini.items():
                f.write(f"{k}={v}\n")
        print("ini:", ini)

    key = sys.argv[1]
    if key.isdigit():
        pid = int(key)
    else:
        cand = [w for w in ws if key.lower() in w[1].lower()]
        if not cand:
            print("no window matching", key)
            for h, t, pid, x, y, w, hh in ws:
                print(f"  hwnd={h} pid={pid} {t[:70]!r}")
            return 1
        pid = cand[0][2]
        print(f"matched hwnd={cand[0][0]} pid={pid} {cand[0][1][:70]!r}")
    return inject(pid)


if __name__ == "__main__":
    sys.exit(main())
