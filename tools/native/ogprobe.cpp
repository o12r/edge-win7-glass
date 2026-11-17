// ogprobe.dll - in-process probe for the "transparent Chromium tabstrip" project.
//
// Loaded into msedge.exe / chrome.exe by a remote-thread injector (the original
// ogprobe_inject.py was pruned; see git history a343f9f for it). It:
//   1. finds the browser's top-level Chrome_WidgetWin_* windows,
//   2. logs style / exstyle / window rect / client origin to ogprobe.log,
//   3. applies the recipe picked in ogprobe.ini:
//        mode=0  log only
//        mode=1  DwmExtendFrameIntoClientArea(top = top)
//        mode=2  mode 1 + DwmEnableBlurBehindWindow(whole client)
//        mode=3  mode 2 + subclass: WM_NCCALCSIZE/WM_NCPAINT go to DefWindowProc,
//                and log the NCCALCSIZE parameters (tells us where Chromium's NC ends)
//   4. logs WM_DWMCOMPOSITIONCHANGED / WM_SIZE / WM_SETTINGCHANGE for the window.
//
// Config file: <dir of ogprobe.log>\ogprobe.ini, key=value lines, e.g.
//   mode=1
//   top=118
//   delay=1500        (ms to wait after DllMain before touching windows)

#include <windows.h>
#include <dwmapi.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#pragma comment(lib, "dwmapi.lib")

static const wchar_t* kLogPath = L"C:\\Users\\oscar\\AppData\\Local\\hermes\\cache\\scratch\\ogprobe.log";
static const wchar_t* kIniPath = L"C:\\Users\\oscar\\AppData\\Local\\hermes\\cache\\scratch\\ogprobe.ini";

static int  g_mode = 0;
static int  g_top = 118;
static int  g_delay = 1200;
static CRITICAL_SECTION g_lock;

static void ensure_lock() {
    static LONG once = 0;
    if (InterlockedCompareExchange(&once, 1, 0) == 0) InitializeCriticalSection(&g_lock);
}

static void logf_(const char* fmt, ...) {
    ensure_lock();
    EnterCriticalSection(&g_lock);
    FILE* f = nullptr;
    if (_wfopen_s(&f, kLogPath, L"a") == 0 && f) {
        SYSTEMTIME st; GetLocalTime(&st);
        fprintf(f, "[%02d:%02d:%02d.%03d] ", st.wHour, st.wMinute, st.wSecond, st.wMilliseconds);
        va_list ap; va_start(ap, fmt);
        vfprintf(f, fmt, ap);
        va_end(ap);
        fputc('\n', f);
        fclose(f);
    }
    LeaveCriticalSection(&g_lock);
}

static void read_ini() {
    FILE* f = nullptr;
    if (_wfopen_s(&f, kIniPath, L"r") != 0 || !f) return;
    char line[256];
    while (fgets(line, sizeof line, f)) {
        char* eq = strchr(line, '=');
        if (!eq) continue;
        *eq = 0;
        int v = atoi(eq + 1);
        if (!strcmp(line, "mode")) g_mode = v;
        else if (!strcmp(line, "top")) g_top = v;
        else if (!strcmp(line, "delay")) g_delay = v;
    }
    fclose(f);
}

static void dump_window(HWND h, const char* when) {
    wchar_t cls[256] = {}, title[256] = {};
    GetClassNameW(h, cls, 256);
    GetWindowTextW(h, title, 256);
    RECT wr{}; GetWindowRect(h, &wr);
    RECT cr{}; GetClientRect(h, &cr);
    POINT c0{ 0, 0 }; ClientToScreen(h, &c0);
    LONG_PTR style = GetWindowLongPtrW(h, GWL_STYLE);
    LONG_PTR ex = GetWindowLongPtrW(h, GWL_EXSTYLE);
    char cls8[256] = {}, tit8[256] = {};
    WideCharToMultiByte(CP_UTF8, 0, cls, -1, cls8, 256, nullptr, nullptr);
    WideCharToMultiByte(CP_UTF8, 0, title, -1, tit8, 256, nullptr, nullptr);
    logf_("%s hwnd=%p cls=%s title=\"%s\" style=0x%08llX ex=0x%08llX "
          "win=(%ld,%ld)-(%ld,%ld) client=%ldx%ld clientOrigin=(%ld,%ld) nc_top=%ld",
          when, h, cls8, tit8, (unsigned long long)style, (unsigned long long)ex,
          wr.left, wr.top, wr.right, wr.bottom, cr.right, cr.bottom,
          c0.x, c0.y, c0.y - wr.top);
}

static LRESULT WINAPI Sub(HWND h, UINT msg, WPARAM wp, LPARAM lp, DWORD_PTR) {
    switch (msg) {
    case WM_NCCALCSIZE: {
        NCCALCSIZE_PARAMS* p = (NCCALCSIZE_PARAMS*)lp;
        if (wp && p) {
            RECT r = p->rgrc[0];
            logf_("WM_NCCALCSIZE wparam=1 proposed=(%ld,%ld)-(%ld,%ld)", r.left, r.top, r.right, r.bottom);
        } else {
            logf_("WM_NCCALCSIZE wparam=0");
        }
        // mode 3: let the default handler shrink to a system frame so DWM paints the caption
        if (g_mode >= 3) return DefWindowProcW(h, msg, wp, lp);
        break;
    }
    case WM_NCPAINT:
        logf_("WM_NCPAINT hrgn=%p", (HANDLE)wp);
        if (g_mode >= 3) return DefWindowProcW(h, msg, wp, lp);
        break;
    case WM_DWMCOMPOSITIONCHANGED:
        logf_("WM_DWMCOMPOSITIONCHANGED");
        break;
    case WM_SIZE:
        logf_("WM_SIZE %ldx%ld", (long)(short)LOWORD(lp), (long)(short)HIWORD(lp));
        break;
    case WM_ACTIVATE:
        logf_("WM_ACTIVATE %d", (int)LOWORD(wp));
        break;
    }
    return DefSubclassProc(h, msg, wp, lp);
}

static void apply(HWND h) {
    dump_window(h, "found");

    if (g_mode >= 1) {
        MARGINS m{ 0, 0, g_top, 0 };
        HRESULT hr = DwmExtendFrameIntoClientArea(h, &m);
        logf_("DwmExtendFrameIntoClientArea(top=%d) -> 0x%08lX", g_top, (unsigned long)hr);
        SetWindowPos(h, nullptr, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_FRAMECHANGED);
    }
    if (g_mode >= 2) {
        HRGN rgn = CreateRectRgn(0, 0, 20000, 20000);
        DWM_BLURBEHIND bb{ DWM_BB_ENABLE | DWM_BB_BLURREGION, TRUE, rgn, FALSE };
        HRESULT hr = DwmEnableBlurBehindWindow(h, &bb);
        logf_("DwmEnableBlurBehindWindow -> 0x%08lX", (unsigned long)hr);
    }
    if (SetWindowSubclass(h, (SUBCLASSPROC)Sub, 1, 0))
        logf_("subclassed");
    dump_window(h, "after");
}

static DWORD WINAPI Thread(LPVOID) {
    ensure_lock();
    read_ini();
    logf_("=== ogprobe attached pid=%lu mode=%d top=%d delay=%d", GetCurrentProcessId(), g_mode, g_top, g_delay);
    Sleep(g_delay);

    struct Ctx { int found; } ctx{ 0 };
    EnumWindows([](HWND h, LPARAM lp) -> BOOL {
        DWORD pid = 0; GetWindowThreadProcessId(h, &pid);
        if (pid != GetCurrentProcessId()) return TRUE;
        wchar_t cls[256] = {};
        GetClassNameW(h, cls, 256);
        if (wcsncmp(cls, L"Chrome_WidgetWin_", 17) != 0) return TRUE;
        if (!IsWindowVisible(h)) return TRUE;
        RECT wr{}; GetWindowRect(h, &wr);
        if ((wr.right - wr.left) < 300) return TRUE;      // skip tiny helper windows
        ((Ctx*)lp)->found++;
        apply(h);
        return TRUE;
    }, (LPARAM)&ctx);

    logf_("applied to %d window(s)", ctx.found);
    return 0;
}

BOOL WINAPI DllMain(HINSTANCE, DWORD reason, LPVOID) {
    if (reason == DLL_PROCESS_ATTACH) {
        DisableThreadLibraryCalls(nullptr);
        HANDLE t = CreateThread(nullptr, 0, Thread, nullptr, 0, nullptr);
        if (t) CloseHandle(t);
    }
    return TRUE;
}
