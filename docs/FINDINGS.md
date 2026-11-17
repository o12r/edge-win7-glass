# FINDINGS — 已做的实验与结论

> 注：本文是开发期的实验记录，保留原貌以便追溯结论是怎么得出的。
> 仓库里现在只有生产链路（`tools/native/glass_titlebar.py`、`gt_daemon.py`、`gt_i18n.py`、`launch.bat`）。
> 下文提到的探针/取证/截图脚本（`ogprobe.cpp`、`probe_*.py`、`launch_scratch.py`、`capmain.ps1` 等）
> 已从仓库移除，需要复现请从 git 历史取。

## 1. 环境盘点（实测）

| 项 | 值 |
|---|---|
| OS | Windows 11（用户目录 `C:\Users\oscar`） |
| Edge | 157.0.4341.60（`C:\Program Files (x86)\Microsoft\Edge\Application\157.0.4341.60\`） |
| Chrome | 已安装（`C:\Program Files\Google\Chrome\Application\`），用于对照 |
| OpenGlass | 已安装：`C:\Program Files\OpenGlass\`（`OpenGlass.dll` / `OpenGlassGUI.exe` / `OpenGlassHost.exe`），`OpenGlassHost.exe` 常驻服务进程，数据目录 `%ProgramData%\OpenGlass\` |
| Windhawk | 1.7.3，已装 mod：`translucent-windows`、`dark-menus`、`explorer-details-better-file-sizes`、`restore-button-pulse-anim`、`edge-window-tab-manager-block`、`remove-fullscreen-popup-chrome` |

OpenGlass 当前 DWM 配置（`HKLM\SOFTWARE\Microsoft\Windows\DWM`，读出来就是 Win7 风格预设）：

```
GlassOpacity                  = 15      (0xF)
RoundRectRadius               = 6       (Win7；Win8=0)
DisableModernBorders          = 1
CaptionButtons                = 1
CenterCaption                 = 2
TextGlowMode                  = 0       (Win7 标题发光 -> 未开)
BlurOptimization              = 2
ColorizationColorBalanceOverride = 62
```

结论：**系统侧的玻璃已经调成 Win7 味了**，问题完全在 Chromium 自己画的那条 titlebar 上。

## 2. Edge 侧状态

- profile 偏好里**没有** `browser.custom_chrome_frame`（= 默认 true → Edge 用自绘边框，非系统标题栏）。
- `Local State` 里启用过实验 flag `edge-visual-rejuv-mica@1`（Edge 的 Mica 标题栏实验）。
- `msedge.dll` 字符串扫描：**不存在** `custom_chrome_frame`、`use_system_title_bar`、
  `Windows10CustomTitlebar`、`Windows11MicaTitlebar`、`GlassBrowserFrame`、`AeroGlass` 等特性名；
  只有 UI 颜色常量（`--color-edge-window-background-mica` 等）。→ 156/157 已把这些开关从二进制里删掉，
  想靠 edge://flags 或命令行特性打开旧玻璃边框，**此路不通**。

## 3. 实测实验

实验 A：直接把 `browser.custom_chrome_frame` 写成 `false`（= 用系统标题栏），
清掉 mica flag，杀进程重启 Edge，然后截窗口图。

结果：**上下两层标题栏同时存在** —— 顶上一条是 OpenGlass 渲染的玻璃 caption（窗口标题 +
Win7 玻璃胶囊按钮），下面仍是 Edge 自绘的标签栏，且标签栏右侧还带一套自己的 − □ ✕。
标签栏底色是不透明深色（mica 实验关掉后变黑），玻璃透不过来。

实验 B：用 Chrome 打开 about:blank 对照截图。

结果：**Chrome 出现一模一样的双层结构**（顶部 OpenGlass 玻璃 caption + Chrome 自己的标签栏和按钮），
说明这不是 Edge/mica flag 的问题，而是「Chromium 自绘边框 + OpenGlass 渲染非客户区」的普遍冲突。

## 4. 根因

1. Chromium 的 Aero 玻璃边框视图 `GlassBrowserFrameView`（`chrome/browser/ui/views/frame/glass_browser_frame_view.cc`）
   只在 Win Vista/7 生效，闸门是 `IsAeroGlassEnabled()`；Win10/11 恒为 false → 代码路径死了。
   参考图那种「标签页直接画在玻璃上、按钮贴在玻璃右端」正是这个视图在 Win7 上的产物
   （等价于 Edge ≤109 / Chrome 在 Win7 的表现）。
2. 现代 Chromium 自绘边框：标签栏与工具栏是**不透明**skia 层，不会给 DWM 玻璃留洞。
3. OpenGlass 只改 DWM 的框（非客户区）与扩展框区域的合成；它不去改应用的客户区绘制内容。
   它还会在窗口顶部按 aero 尺寸补一条 caption（含标题文字、按钮），
   于是出现「系统 caption + Chromium 标签栏」两条并存的画面。
4. Windhawk 现有 mod 库里没有「Chromium 玻璃标题栏」这类 mod（用户已全试过），
   即没有现成的「让标签栏半透明并融合进玻璃」的手段。

## 5. 参考图的判定

参考图 = Win7 上 Chromium（Edge 109 或同期 Chrome）跑 Aero Glass：
一行 = 玻璃 caption 高度 ≈ 标签栏高度，标签页与 `+`、tab-search 按钮都画在玻璃上，
右侧是 aero.msstyles 定义的玻璃胶囊按钮（关闭红色发光）。要在 Win11 复刻它，必须
**把 Chromium 的标签栏改成透明并延伸到扩展框区域**，也就是复制 Win7 时代那份视图的资源与度量。

## 6. 现状复原

实验把 Edge 偏好改成过系统标题栏 + 清 flag，已复原为：
`browser.custom_chrome_frame = true`、`Local State: enabled_labs_experiments = ["edge-visual-rejuv-mica@1"]`。
（写入后需重启 Edge 才生效。）两层标题栏是实验前就存在的状态，与本次改动无关。

## 7. 第二轮实验（2026-11-16 下午，"变透明 + 覆盖层"路线）

工具：`tools/layered_test.py`、`tools/dwm_caption_test.py`、`tools/glass_hole_test.py`、
`tools/striped_backdrop_test.py`、`tools/native/`（ogprobe.dll + 注入器 + holes_demo.py）。

### 7.1 进程外"把黑色变透明"的手段逐项证伪

| 手段 | 结果 |
|---|---|
| 跨进程 `WS_EX_LAYERED` + `LWA_ALPHA` | 生效：整窗半透明。**但全窗一起淡，不能只淡标题栏** |
| 跨进程 `LWA_COLORKEY`（`#000000` 和实测底色 `#20201F` 各一次） | **0 像素变化**。色键对 Chromium 的 DirectComposition 内容无效 |
| 跨进程 `DwmExtendFrameIntoClientArea(top)` | 调用返回 S_OK，标签栏区域绘制方改变（洞的颜色 `#62686E` → `#040D17`），但 Chromium 自己画的内容不动 |
| `--enable-features=Windows11MicaTitlebar`（全新 profile） | 像素级完全一致，flag 已成死代码 |
| `DWMWA_SYSTEMBACKDROP_TYPE=2/3`（活窗口，跨进程） | 2 无变化；3 打完后窗口句柄立刻 `ERROR_INVALID_HANDLE`（窗口被搞死） |

### 7.2 关键发现：玻璃早就在标签栏那一条里，只是被盖住了

条纹底版 + `SetWindowRgn` 挖洞受控实验（`glass_in_hole.py`、`holes_demo.py`）：

- 洞里的条纹是**模糊的**（sharpness 0.58，且扩展框后变 0.24、颜色更饱和 `(114,18,139)`），
  窗外条纹锐利。→ OpenGlass 已经在 Chromium 的扩展框区域渲染玻璃。
- 换句话说：标签栏背景不是"不透明黑"，而是"玻璃 + 上面盖了一层不透明像素"。
  把像素挖掉，玻璃就露出来，**不需要注入**。
- 洞只开在背景处时，标签本体、Chromium 自己的 − □ ✕ 都完好（`hd_after.png`）。

### 7.3 注入路径的可行性边界

- `ogprobe.dll` 注入 msedge.exe 成功（`LoadProcess`/`LoadLibraryW` 远程线程），可枚举窗口、
  读 `style/client/nc_top`（实测 `nc_top=58`），并能在进程内调 DWM 接口。
- 但即使进程内调用，**Chromium 的窗口表面是否带 alpha 仍未知**：`DwmEnableBlurBehindWindow`
  的区域模糊在洞外无任何视觉变化；要真正让 Chromium 自绘像素变透明，必须让它用
  alpha 合成（swapchain `DXGI_ALPHA_MODE_PREMULTIPLIED` + 不画标签栏背景），
  这需要 hook Chromium 的 cc/views 绘制路径，随 Edge 版本维护。
- 结论：注入只能解决"标签本体也透明"，成本远高于挖洞；挖洞已经能交付"一行式玻璃"的观感。

### 7.4 代价（挖洞路线必须接受）

1. 洞内点击穿透到桌面 → 标签栏空白处的拖动、双击最大化失效，需要覆盖层兜底转发；
2. 洞是矩形，标签圆角处会出现缺口，需按标签实际矩形逐帧更新 region；
3. 标签本体仍是 Chromium 的不透明深色（没法外改），只有缝隙和空白是玻璃。


## 8. 全挖 + 自绘标签栏（glass_titlebar.py，已跑通）

路线：把整条 titlebar（tab 条，从窗口顶到 tab 底边）一次性挖掉，露出 OpenGlass 的玻璃，
再用一个分层覆盖窗把标签、`+` 重新画上去；窗口按钮不重画，交给浏览器原生那组。

工具：`tools/native/glass_titlebar.py`（`.venv` 里有 uiautomation/comtypes/Pillow）

```bash
.venv/Scripts/python.exe tools/native/glass_titlebar.py --hwnd <hwnd>      # 跑
.venv/Scripts/python.exe tools/native/glass_titlebar.py --hwnd <hwnd> --reset  # 只还原
```

### 8.1 五个坑（都踩过，改代码时别踩回去）

1. **分层窗口 alpha≈0 的地方点不动**：`UpdateLayeredWindow` 的透明区域由 DWM 按像素
   alpha 命中测试，背景 alpha=1 也收不到 `WM_LBUTTONDOWN`（`WindowFromPoint` 返回 dwm 的
   `Ghost`）。所以输入必须走 `WH_MOUSE_LL` 钩子：吞掉整条 bar 的点击，再按自绘命中表分发。
2. **钩子里不能做 UIA 调用**：回调超过 `LowLevelHooksTimeout`(默认 300ms) 会被系统
   **静默卸载**（之后所有点击都失效，日志里也没有任何痕迹）。动作必须丢进队列，由
   普通线程执行（`InputHook._drain`）。
3. **`SetWindowPos(overlay, target, ...)` 是把覆盖窗插到 target 下面**（`hWndInsertAfter`
   是"插在谁之后"）。放错边以后覆盖窗像素会被 OpenGlass 当背景模糊掉，屏幕上只剩一团虚影。
   正确做法：`GetWindow(target, GW_HWNDPREV)` 取 target 上面那个窗，插到它后面。
4. **原生窗口按钮不受 region 影响**：`− □ ✕` 画在 Chromium 的 `Intermediate D3D Window`
   子窗里，父窗挖洞切不掉它们。所以不要重画（否则重影），保留原生视觉，但点击仍要自己
   转发（洞里的点击到不了浏览器）→ `WM_SYSCOMMAND` 的 `SC_MINIMIZE/SC_MAXIMIZE/SC_RESTORE/SC_CLOSE`。
5. **region 不会随进程死亡还原**：`kill` 掉进程时 `finally` 不执行，窗口会一直带着洞。
   启动时先 `SetWindowRgn(hwnd, None, True)` 清一遍，并提供 `--reset`。

补充：`SetCursorPos` 产生的移动事件不进 LL 钩子，拖动要在独立线程里轮询 `GetCursorPos`
（`InputHook._drag_loop`）；点击要先用 `AttachThreadInput` + `SetForegroundWindow` 才能把
后台窗口激活（`force_foreground`）。

### 8.2 已验证（临时 profile 窗口）

- 整条挖洞后是**真玻璃**，标签文字/图标/`+`/窗口按钮位置全部来自 UIA，跟随窗口与标签变化；
- 拖拽空白区移动窗口 ✅、双击空白区最大化/还原 ✅、点 `+` 新建标签 ✅、
  点标签切换 ✅（并会把窗口切到前台）、点标签 `×` 关闭 ✅、最小化/最大化/关闭 ✅；
- 全屏或 UIA 拿不到新鲜数据时立即清洞（`glass_strip.py` 的同款防护），不会再把洞开到页面；
- 现有观感：标签是 Win7 风格的浅色活动页 + 半透明非活动页，原生 `− □ ✕` 保持原样。

### 8.3 不稳定 / 鼠标穿透标题栏（已修）

症状：偶尔点标题栏没反应，点击漏到桌面。根因是低层钩子（`WH_MOUSE_LL`）的回调
**必须在几十毫秒内返回**，超时 Windows 就直接跳过这次事件（表现为"穿透"），
反复超时还会把钩子静默丢掉（进程还在，但再也收不到事件）。原本每 0.12s 全量重绘
一次（标签标题里带 `NNN MB` 内存数字，签名一直在变 → 一直在重绘），把钩子线程饿死了。

修法（按贡献大小排序）：

1. **别每帧重绘**：`_stable()` 把标题里的 "NNN MB" 抹掉再算签名，重绘节流到 ≥0.25s；
   实测 7 秒内重绘从几十次降到 9 次。
2. **渲染去 Python 循环**：渐变条 + 圆角遮罩按 (尺寸, 颜色) 缓存，`vgrad` 只做一次
   `resize`+`paste`（原来每行一次 `draw.line`，1400×82 就是 82 次 Python 调用）。
3. **钩子回调里不碰磁盘、不调 UIA、不调 `SetForegroundWindow`**：日志改异步队列写，
   UIA/激活全部丢给工作线程（`_drain`）。
4. **鼠标移动零成本**：`WM_MOUSEMOVE` 在拖动时才处理，其余直接 `CallNextHookEx`。
5. **命中区用实时几何**：`in_band()` 每次 `GetWindowRect` + 缓存的 band 偏移，
   不再用 0.1s 前的主循环缓存（窗口一移动就过期，洞外点击全部漏出去）。
6. **看门狗**：光标在动但 1.2s 内没收到任何事件 → 判定钩子被系统丢弃，
   `PostThreadMessage(WM_APP+1)` 让钩子线程重新 `SetWindowsHookEx`。
7. 钩子线程 `THREAD_PRIORITY_HIGHEST` + `sys.setswitchinterval(0.001)`。

实测（临时 profile）：10 次/秒连点 50 次 → 50/50 命中；60 次 @13/s → 60/60；
灌到 45 次/秒时约 1/4 被系统合并丢弃（这是 LL 钩子的固有上限，真人点击达不到）。

如仍偶发穿透，可把系统的钩子超时调大（默认 300 ms）：

```bash
.venv/Scripts/python.exe tools/native/glass_titlebar.py --hwnd <hwnd> --fix-timeout
# 写 HKCU\Control Panel\Desktop\LowLevelHooksTimeout = 1000 (DWORD)，对新装的钩子生效
```

另：标签文字用 `fit_text()` 手动截断加省略号——Pillow 的 `length=` 参数在给了
`anchor=` 时会被忽略，会导致文字溢出到相邻标签上。

## 9. 观感升级：Win7 布局 / favicon / 悬停（2026-11-16 晚）

### 9.1 标签宽度用自己算的布局，不再信 UIA 的矩形

Chromium 让最后一个标签吃掉剩余宽度（单标签窗口里能到 512px），Win7 不是这样。
`layout_tabs()`：等宽、上限 `tab_max_width`（默认 220 CSS px）、下限 `tab_min_width`，
从左侧搜索箭头右边起**左对齐**排开。UIA 矩形只用来做「图标在哪里 / 是哪个标签」，
绘制与命中表都用算出来的矩形（两者必须同源，否则点击会落空）。

实测：单标签 → 440px（2x DPI）；4 标签 → 440px；12 标签 → 168px，全部塞进 `+` 左边。
narrow 到 168px 时点第 5/9/2 个标签仍然精确命中。

### 9.2 favicon：`PrintWindow` 会被 region 裁掉，用「冻结帧」掩盖

- **`PrintWindow(child, PW_RENDERFULLCONTENT)` 能拿到 Chromium 的 D3D 内容**，
  但窗口区域挖掉的那一条会返回**纯黑**（region 影响合成结果）——所以抓图前必须先
  `SetWindowRgn(hwnd, None, True)`，抓完再按原来的 hole 重建 region。
- 代价：一次 `清 region + PrintWindow(2564×1617) + 回填` ≈ **81 ms**，也就是屏幕上会
  有 4~5 帧露出原生深色标签条。
- 消掉闪烁的办法（已实现，`Overlay.freeze`）：清 region 之前先用 `BitBlt` 把**当前屏幕上的
  band 抓下来**（这一帧里已经有我们自己的半透明标签条 + 玻璃），当作**完全不透明**的一帧
  `UpdateLayeredWindow` 贴上去。此时原生条虽然回来了，但被这张不透明帧盖住，用户看不到任何
  变化；抓完再正常重绘。
- 抓到的图标用「与四角背景色的距离」做 alpha 键控（`key_icon`），去掉深色底；
  低饱和的白色字形（Chromium 深色标签上是白图标）在浅色标签上不可见，所以按主题
  把它们重新染成深/浅文字色。彩色站点图标原样保留。
- 缓存键是 `_stable(title)`（已抹掉 `NNN MB`），同一个标题只抓一次；抓不到的标题
  20 秒内不重试。

### 9.3 悬停高亮

- 悬停判断放在 `WH_MOUSE_LL` 里，但**只记录**目标（`overlay.pending_hover`）：
  遍历几十个矩形是纯 Python 操作，几微秒；绘制交给主循环。
- 主循环发现 `pending_hover != hover` 就重绘（节流 40 ms）。连续扫过整条 bar 实测
  ≈12% 单核（空闲时 0%），可以接受；标签数量少时更低。
- `+`、左侧搜索箭头、标签 `×` 都有独立的悬停态；窗口按钮保持原生，不做悬停。

### 9.4 点击延迟：钩子里现在真的只做纯粹的记录

之前 `WM_LBUTTONDOWN` 分支里直接调 `_select_tab()`（UIA COM 调用）和 `_send_key()`
（`SetForegroundWindow` + `keybd_event` + `sleep(0.02)`）。这些都是几十毫秒级、
偶尔几百毫秒的阻塞，正是「偶尔点击延迟/穿透」的来源。现在**所有动作一律 `q.put(action)`**
交给 `_drain` 线程，钩子回调只剩「算命中 + 入队」。

### 9.5 踩到的小坑

- `u32.PrintWindow` / `EnumChildWindows` 必须显式设 `argtypes`，否则 64 位句柄会被当
  `c_int` 传来 `int too long to convert`（`gdi.CreateDIBSection` 同理，被模块里已有的
  argtypes 影响时会突然要求 `LP_BITMAPINFO`）。
- UIA 的 tab 名会随页面加载变化（`GitHub · …` → 末尾追加 `- Memory usage - 137 MB`），
  比对标签身份一定要过 `_stable()`，否则同一个标签会被当成新标签反复抓图标。
- 自己写测试脚本点 `×` 时要注意：命中表用的是**计算出来的**矩形，不是 UIA 的原始矩形，
  用 UIA 矩形算 `x = right - 30` 会点到标签本体上。

## 10. 后台守护进程 + 设置页（gt_daemon.py）

```bash
.venv/Scripts/pythonw.exe tools/native/gt_daemon.py     # 常驻（无控制台）
.venv/Scripts/python.exe  tools/native/gt_daemon.py --console
.venv/Scripts/python.exe  tools/native/gt_daemon.py --quit
```

- 单实例用命名互斥体 `Local\edge-win7-glass-daemon`；第二个实例直接打开设置页退出。
- 每秒扫一次 `Chrome_WidgetWin_1` 窗口，**按 exe 名过滤**（msedge/chrome/brave/vivaldi/
  chromium/opera/yandex/thorium）。必须按 exe 过滤：Hermes 桌面端（Electron）的窗口
  类名同样是 `Chrome_WidgetWin_1`，只看类名会把它也接管。
- 每个窗口一个线程跑 `glass_titlebar.attach_loop(hwnd, cfg, scale, stop_event, log)`
  （从原 `main()` 里抽出来的循环，CLI 和守护进程共用）。
- 托盘用 `Shell_NotifyIconW` 直接做（不引入 pystray），隐藏窗口收 `WM_TRAY` 回调，
  右键 `TrackPopupMenu`：打开设置页 / 浅色 / 深色 / 暂停接管 / 开机自启 / 退出。
- 设置页：`ThreadingHTTPServer` 绑 `127.0.0.1:8721`（占用则 +1），`GET /` 是页面，
  `GET /api/status`、`POST /api/settings`、`POST /api/quit`。保存后写回 settings.json，
  然后 **断开所有窗口再重新接管**（最简单的热应用方式）。
- 开机自启：`HKCU\...\CurrentVersion\Run` 写 `EdgeWin7Glass`，指向 `pythonw.exe gt_daemon.py`。

### 10.1 踩过的坑

1. **ctypes argtypes 在两个模块之间打架**：守护进程给 `GetWindowRect`/`GetCursorPos`/
   `RegisterClassW`/`CreateDIBSection` 设的 argtypes 用的是 `wintypes.RECT/POINT/WNDCLASS`，
   而 `glass_titlebar` 传的是它自己定义的同名 `Structure` 类，ctypes 会报
   `expected LP_RECT instance instead of pointer to RECT`。**结论：给这类函数设 argtypes 时
   必须用 `glass_titlebar` 里的类型，或者干脆不设。**（`PrintWindow`/`EnumChildWindows` 这种
   只吃句柄/整数的可以放心设。）
2. **退出竞态会留下洞**：`quit()` 里 `detach_all()` 之后、`os._exit()` 之前，看门狗线程
   还在跑 `scan()`，会把刚断开的窗口重新 attach，然后进程死掉 → 洞永久残留。
   加 `self.stopping` 标志，`scan()`/`attach()` 都先检查它。
   验证方法：`GetWindowRgn(hwnd, rgn)` 返回 0 = 没有 region（已还原），2/3 = 还有洞。
3. **调试日志别用 `%TEMP%`**：从 MSYS bash 启动时 `TEMP=/tmp`，原生 Python 会写到 `C:\tmp\`，
   找不到文件还以为没日志。现在固定写 `%LOCALAPPDATA%\edge-win7-glass\tool-debug.log`。
4. **滚轮切标签**：`WH_MOUSE_LL` 能收到 `WM_MOUSEWHEEL`，delta 在 `mouseData >> 16`，
   动作同样丢队列发 Ctrl+Tab / Ctrl+Shift+Tab（`_send_key` 现在支持多个修饰键）。
   实测一次滚轮 = 切一格。
5. 测试时可以用 `GT_ONLY_HWND=<hwnd>` 让守护进程只接管一个窗口，避免动到用户正在用的浏览器。

## 11. 「两层标签」根因 + 改用原生标签条（2026-11-16 深夜 ~ 17 日）

### 11.1 现象与实测（A/B/C 三态）

症状：Chrome 上每个标签的文字、图标、`×` 都出现两份，横向错开 ~30px 叠在一起。

同一窗口取三种状态各截一次图（`spike_three_states.py`，无覆盖层）：

| 状态 | 标签带像素均值 | 结论 |
|---|---|---|
| A 不打洞 | `42, 95, 100` | 原生条 |
| B 只挖父窗 | `81, 81, 84` | 原生条**没了**，露出背景 |
| C 父窗 + D3D 子窗 | `81, 81, 84`（与 B `diff 0.0`） | 子窗不需要单独挖 |

**结论：父窗的 `SetWindowRgn` 确实会裁剪 D3D 子窗的内容**（子窗是普通子窗口，被父窗
region 连带裁掉）。所以：

- 「整条挖洞 + 保留原生标签」在字面上**做不到**——洞会把原生标签一起切掉；
- 之前那条「父窗 region 切不掉子窗」的判断是错的，作废；
- 双层文字的真实来源是**被停用的自绘覆盖层**：`Overlay.freeze()` 会把当前屏幕带（里面
  已经含原生标签条 + 我们的标签）烤成不透明帧，抓 favicon 又要临时清 region，于是原生
  标签像素被烤进覆盖层，再叠上自绘标签 = 两份。属于自绘路线的固有缺陷，随该路线一起停用。

### 11.2 现在的产品形态：原生标签 + comb 挖洞

`comb_region(win, band, keep)`：把**标签条背景**挖掉，但把每个 tab 矩形、`+`、
搜索按钮、`− □ ✕` 的矩形从洞里减掉（`RGN_DIFF`，左右各留 1px 余量）。

实测（`spike_comb.py`，12 标签）：

```
A 原生     缝隙 34,83,87    tab0 本体 49,137,146
B comb     缝隙 85,87,92    tab0 本体 49,137,146   ← 本体逐像素不变
```

好处：favicon、关闭按钮、命中测试、**拖拽重排全部是 Chromium 原生的**，不再需要抓图、
不再有 DPI/站点兼容问题。

实现要点：

- 原生模式下不建覆盖层、不装鼠标钩子（滚轮切标签、双击最大化本来就是 Chromium 的行为）。
- region 的 key 里带 tab 矩形，并按 2px 对齐：UIA 会抖 1px，无谓的 `SetWindowRgn`
  会让标签条闪。
- **后续清理**：自绘那套（`layout_tabs`/`render`/`Overlay`/`Favicons`/`Theme`/`comb_region`/
  `clip_region`/`child_cut_region`）已连同 `NATIVE_TABS` 开关和对应设置项整段删除，
  只留原生路径；`theme` 仍保留但只驱动托盘菜单勾选。
### 11.3 最终形态：四边窄边 + 右上角交给 OpenGlass

用户方向调整：**保留 Chromium 原生标签条**（自绘 favicon 兼容性差），玻璃只做边框。

- **四边各切 `frame_px`（默认 4 CSS px，按 DPI 缩放）**，露出 OpenGlass 的背景玻璃。
- **右上角整块挖掉**（从 `+` 右缘到窗口右缘、高度=标签带），OpenGlass 会在那里画
  Win7 胶囊按钮 `− □ ✕`（实测可见）。
- 标签本体一个像素都不动：图标、文字、`×`、命中、**拖拽重排全部原生**。

关键坑：**挖掉的那块是"洞"，点击会穿到桌面**，OpenGlass 画出来的按钮点不动
（实测 `iconic after False`）。所以加了 `CaptionHook`：一个只有 60 行职责的
`WH_MOUSE_LL` 钩子，命中角里的按钮就 `PostMessage(target, WM_SYSCOMMAND, …)`
（`SC_MINIMIZE 0xF020` / `SC_MAXIMIZE 0xF030` / `SC_RESTORE 0xF120` / `SC_CLOSE 0xF060`），
角里的空白处也一并吃掉，避免误点桌面。实测：点最小化 `iconic=True`，点最大化 `zoomed=True`，
日志 `caption click -> min/max`。

`comb_region()`（只挖标签条背景、保留 tab 矩形）当年作为中间方案留在代码里，现已删除。

设置页已改：`frame_px`、`gl_buttons` 等是生效项；自绘专用的标签宽度/圆角/悬停/favicon/滚轮
输入框已从页面和 `F` 列表里去掉。

### 11.4 交互补齐：全屏、挖洞处的选中与缩放

三个真 bug 和对应修法：

1. **切全屏时洞在闪**。全屏下 Chromium 会随光标靠近顶部**动态显示/隐藏标签条**，UIA 一抖
   我们就 region 一改一清 → 闪。
   - 加 `is_fullscreen(hwnd, win)`：窗口矩形盖满 `rcMonitor` **且**不是最大化（最大化时
     窗口比 monitor 还大，所以不会误判）→ 直接 `restore_regions()` 后彻底不管，只记一条
     `fullscreen -> region cleared`。
   - 另外所有 region 变更加了**稳定 3 次采样**的迟滞（窗口整体移动/缩放不受影响，仍立即
     跟随）。实测：进出全屏 + 光标在顶部来回扫，日志只有 2 条（进/出各一条）。
2. **挖洞的地方点不中窗口**。洞里的点击直接落到桌面上。`CaptionHook` 现在对洞里的
   **任意**点击先 `SetForegroundWindow(target)`；实测从 Progman 点洞 → `fg` 变成目标窗口。
3. **不能缩放窗口**。四边 8px 的洞把 Chromium 自己的 resize 边框切掉了。改为手写缩放：
   在 `CaptionHook` 里记录按下时的边，`WM_MOUSEMOVE` 时 `SetWindowPos` 改矩形（最小
   480×320，最大化时忽略）。实测右边缘拖拽 `dW=203`、下边缘 `dH=123`。

坑：测试拖拽**不能用 `SetCursorPos`**——那样产生的移动不会进 LL 钩子；要用
`mouse_event(MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE)` 才会经过钩子链。

### 11.5 钩子里的阻塞调用（又一次）+ 角上的小圆角

- **`SetForegroundWindow` / `AttachThreadInput` 绝对不能跑在 LL 钩子线程里**。它们可能阻塞
  几百毫秒，而系统对超时的低层钩子是**静默卸载**（不是报错），表现就是"时好时坏"：
  前几次点击能选窗口，后面突然全失效。修法：钩子里只 `q.put(("fg", None))`，真正的
  `force_foreground()` 在 `caption-worker` 线程里跑；再配一个 `caption-watch` 看门狗
  （光标在动但钩子 1.2s 没事件 → `PostThreadMessage(WM_APP+1)` → 重装钩子）。
- **右上角挖出来的那块加了左下小圆角**：`round_corner_cut()` 把切口拆成"主体矩形 + r 行
  1px 弧"，弧的 inset 从 0 递增到 r（`r = 6 CSS px * scale`）。注意行序别写反——第一版写成
  从 r 递减，结果圆角长在了上面。实测 r=12 的 inset 序列：`0,0,0,1,1,1,2,3,4,5,6,9`。

### 11.6 验证环境的坑（重要）

这台机器上会话会突然换显示配置：某次 `GetSystemMetrics(0)` 从 `2560×1600` 变成
`1280×800`，同时 `SetCursorPos`/`mouse_event` **不再移动光标**、最小 30 行的
`WH_MOUSE_LL` 探针**一个事件都收不到**（钩子句柄有效、无错误码）。这种情况下任何
"点击/拖拽"验证都是假的——先跑 `probe_raw.py` 那种最小探针确认能收到事件，再判断功能。

另外：**最大化窗口的顶部 8px 在屏幕外**（窗口 top = -13），所以"从顶部拖拽缩放"在最大化
状态下本来就没有可抓的边；要测顶部必须先还原窗口。

### 11.7 圆角 + 窗口拖动

- **边框改成"内缩圆角矩形"**：`frame_region(win, cuts, inset, radius)` 现在用
  `CreateRoundRectRgn(inset, inset, W-inset+1, H-inset+1, 2r, 2r)` 再与一个下移 r 的矩形
  求并，只圆**上面两个角**、下面保持直角；然后减掉 OpenGlass 角。实测 800×600、inset=8、
  r=12 的区域数据：第一行 `(19,8,650,9)` → 依次 `15,14,12,11,10,9,8`，是标准四分圆弧。
- **右上角能拖窗口了**：以前那块只吃点击。现在按 Win7 caption 的行为：点在按钮上 → 按钮；
  点空白 → 拖动窗口（`SWP_NOSIZE`）；在同一处**双击 → 最大化/还原**。
- 设置项新增 `corner_px`（默认 6 CSS px，0 = 直角），设置页可调。

### 11.8 「拖动时高频率复位」的两个真凶

1. **同时跑着两个守护进程**。单实例检查写成 `ctypes.GetLastError()`，而 `windll.kernel32` 不是
   用 `use_last_error=True` 加载的，这个值永远是 0，于是 `ERROR_ALREADY_EXISTS` 判断从不成立 →
   两个进程各装一套 `WH_MOUSE_LL`。钩子链里返回 1 会截断后续钩子，所以 A 的 `LBUTTONUP` 被 B
   吃掉，A 的 `moving/resizing` 永远挂着，之后每个鼠标移动都用**旧矩形**再 `SetWindowPos` 一次
   —— 表现就是窗口"高频率强制复位"。改法：`k32.GetLastError()`；状态自愈（新的按下或超过
   20 s 就丢弃 latch）；`LBUTTONUP` 无论走哪条分支都清状态。
2. **`GetAsyncKeyState(VK_LBUTTON)` 对 `mouse_event` 注入的事件返回 0**（实测按下拖动期间一直是
   `0x00000000`）。用它当"按键是否还按着"的守卫会把每次拖拽立刻掐断。不要用异步键状态做守卫，
   只信事件流。

### 11.9 顶部不能 resize 的真凶

`_edge()` 和 caption 区域的命中判断顺序写反了：顶部 8 px 边框和 caption 带（band 高度 ~82 px）
重叠，caption 分支在前，于是点顶边永远走"拖动窗口"。实测日志 `down 1149,203 inside=True`。
改法：**先判边框**，边框优先于 caption。修好后四边实测：左 `L+80` 右边不动、右 `W-80`、
上 `T+70` 下边不动、下 `H-70`，全部精确。

### 11.10 Chromium 的最小窗口宽度
窗口在 200% 缩放下宽度 1026 px 时，`SetWindowPos` 缩到 926 px **无效**（位置生效、尺寸被拒），
从别的进程直接调也一样 → 不是我们的 bug：Chromium 限制最小 500 DIP（= 1000 物理像素）。
所以手写缩放的钳位改成 `max(480, 500*scale) × max(320, 200*scale)`。

### 11.11 「拖动时洞消失 + 一直复位」= 快照过期

用户手拖时窗口每几毫秒就动一下，而 UIA 快照里的 `win` 是**上一次采样**的矩形。attach loop 原来的
判断是 `if not snap or not snap.band or snap.win != win:` → 直接 `restore_regions()`（把洞清掉）
再 `continue`，每 0.15 s 重复一次。用户看到的就是：一按下去洞没了，窗口重画成原生框，感觉在"复位"。

修法（三条，缺一不可）：

1. **拖动期间完全不动 region**：`CaptionHook.busy`（`moving or resizing`）为真时 loop 只 sleep。
   region 是**窗口坐标**，窗口自己移，洞自然跟着走。
2. **纯移动用位移补偿**：`clip_snapshot`/`clone_snapshot(last_snap, win)` 把上一帧快照里所有矩形
   按 `(dx,dy)` 平移到新位置，只在**尺寸没变**且快照 10 s 内有效时用；尺寸变了才清。
3. **key 改成窗口相对坐标**：`((w,h), n, cr, rel_cuts)`。以前 key 里带绝对坐标，窗口一移动 key 就变
   → 每个鼠标事件都 `SetWindowRgn(TRUE)` 一次，纯闪烁。

实测（`test_hole.py`，48 步手速拖拽，每 8 步采一次 `GetWindowRgn`）：region 类型始终 3、bound 始终
`(8,8,1493,893)`（窗口坐标不变），窗口左上角从 `(300,200)` 平滑到 `(156,296)`，**0 次 region 丢失**；
外部 `SetWindowPos` 移动 12 次同样 0 次丢失，daemon 日志只在最后打了一条 `frame`。

### 11.12 右上角按钮"错位触发"的根因：两套几何

OpenGlass 的 `CaptionButtons=2` 是 **Windows 7 指标**：min/max 各 30 DIP 宽、close 50 DIP 宽、
整组右缘离窗口右边 7 DIP。Chromium 自己的按钮是 **46 DIP 宽**、整组更宽、偏移也不同。
以前转发点击用的是 UIA 里 Chromium 的矩形，两者错位约 60 物理像素（200% 屏）——于是点 OpenGlass
画的「−」会落到原生「□」上，看起来就是"原生按钮还是被触发"。

实测（截图像素列分析，y=80 行，2x 图，裁剪起点 = 窗口右边-480）：

| 边界 | 2x 列 | 真实 px（相对窗口右边） |
|---|---|---|
| 内容/洞分界 | 360 | -300 |
| 胶囊左缘 | 500 | -230 |
| min/max 分隔 | 618 | -172 |
| max/close 分隔 | 734 | -114 |
| 胶囊右缘 | 940 | -14 |

修法：`attach_loop` 里按 Win7 指标自己算三个按钮矩形并同时用于**挖洞**和**转发命中**，
不再用 UIA 的按钮矩形（UIA 那份只在自绘模式用）。修好后点"画出来的"中心：
min → `iconic=True`、max → `zoomed=True`，日志 `hit=max / caption click -> max`。



### 11.13 洞向左扩到 `+` 右侧后，命中表要跟着回到 Win7 指标

洞的左缘从"按钮组左边 − 6 px"改成"原生 `+` 右缘 + 2 DIP"（中间那段是 Chromium 的空标签条
背景，交给 OpenGlass 画玻璃不影响任何功能，`+` 自己留在洞外仍是原生命中）。改完立刻出现
"点画出来的胶囊，触发的是 Edge 原生那一套" —— 因为挖洞跟着 `+` 走，而**转发命中**又退回用了
UIA 里 Chromium 的按钮矩形（46 DIP 宽、右缘距窗口 6 DIP），和 OpenGlass 画的 Win7 胶囊
（30/30/50 DIP、右缘 7 DIP）在 200% 屏上横向差 4~60 px，`−` 会落到原生 `□` 上。

现在两套几何各司其职，都在 `attach_loop` 里算：

- 洞：`x = min(胶囊左缘 − 2 DIP, 原生 + 右缘 + 2 DIP)`，再夹到 `win.left + frame`。
- 命中：`win7_caption_buttons()` 按 DIP 指标算 `close/max/min` 三个矩形，同时喂给
  `CaptionHook.set_area`（`− □ ✕` → `SC_MINIMIZE / SC_MAXIMIZE|SC_RESTORE / SC_CLOSE`，
  胶囊之间的空白仍是"拖动窗口 / 双击最大化"）。
- 5 个新设置项（设置页可调，DIP）：`btn_pad_right_px=7`、`btn_min_px=30`、
  `btn_close_px=50`、`btn_top_px=0`、`btn_h_px=0`（0 = 用整条标签带高度）。
- 每次接管往日志写一行 `buttons hole=(...) close=(...) max=(...) min=(...)`，实测最大化
  窗口（`win.right=2573`）：`close 2459-2559 / max 2399-2459 / min 2339-2399`，即右缘 −14 px、
  三个胶囊 100/60/60 px，和 §11.12 的截图像素列一致。

命中兜底（"原生按钮绝不触发"）三层：

1. **洞盖住原生按钮**：左缘除了 `+` 右缘、胶囊左缘之外，再取 `min(..., 原生 min_r[0] − 2 DIP)`
   —— Chromium 的按钮组和 OpenGlass 画的胶囊横向量出来差 9~53 px（实测原生
   `2286/2376/2468/2560`，胶囊 `2339/2399/2459/2559`），光靠胶囊矩形会让原生按钮露出一截。
2. **钩子兜底**：`area` 里的左键走胶囊表；不在 `area` 但落在原生按钮矩形里的左键
   （接管第一帧、band 还没稳定、region 被清过）也不给应用，按同 x 对应的胶囊转发
   `WM_SYSCOMMAND`，日志 `native button blocked (x,y) -> min|max|close`。
3. **右/中键与滚轮在洞里一律吞掉**（`return 1`），不再漏给桌面或下层窗口。

## 12. 输入接管从 `WH_MOUSE_LL` 钩子改为隐形覆盖窗（TouchOverlay）

方向调整：**不再用 Edge 原生 / OpenGlass 的 caption button 触控，也不再用全局低层鼠标钩子**，
而是在挖洞的 rect 上盖一个**隐形分层窗口**，由它自己的 WndProc 直接收鼠标消息，接管
顶部的拖拽与 caption button。四边 resize 本轮不做，以后单独补。

### 12.1 关键前提：alpha=1 的层窗口是可点击的（推翻 §8.1 的旧结论）

`alpha_probe.py` 实测 `WindowFromPoint`：

| 层窗口像素 alpha | 中心点命中 | 结论 |
|---|---|---|
| alpha = 1 | **overlay=True**（命中覆盖窗） | 可点击 |
| alpha = 0 | overlay=False（穿透到下层） | 穿透 |

→ §8.1「alpha=1 也收不到 `WM_LBUTTONDOWN`」是当年那个 `Overlay` 的 `_wndproc` 返回了
`HTTRANSPARENT` 造成的，不是 alpha=1 本身的问题。DWM 的命中测试只看「alpha 是否为 0」：
只要非 0 就命中。所以隐形覆盖窗用 **alpha=1 的位图 + 不返回 `HTTRANSPARENT`** 即可
「看得见摸不着」的相反面——「看不见但摸得着」。

### 12.2 TouchOverlay 设计（`glass_titlebar.py`）

- 独立线程跑消息循环（`GetMessageW`）；`WS_EX_LAYERED | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE`，
  `UpdateLayeredWindow` 贴全 alpha=1 位图；`WM_MOUSEACTIVATE` 返回 `MA_NOACTIVATE`（不抢焦点）。
- **覆盖 rect = 挖洞 rect**（同一个 `corner`），按钮命中表 = `win7_caption_buttons()`（与
  OpenGlass 画的 Win7 胶囊对齐）。洞、覆盖窗、命中三者同一源，§11.12/11.13 的「两套几何错位」
  整类 bug 从结构上消失。
- 行为照搬 CaptionHook 的验证逻辑：按钮 → `WM_SYSCOMMAND`；空白按下 → 拖窗（最大化时
  restore-drag）；空白双击 → 最大化/还原；洞内任意点击 → `force_foreground`。
- **`SetCapture` 保证拖动不丢**：`WM_LBUTTONDOWN` 时捕获，鼠标移出 overlay 仍收
  `WM_MOUSEMOVE`/`WM_LBUTTONUP`，不再需要 `GetAsyncKeyState` 守卫（§11.8 坑2 直接不存在）。
- 阻塞调用（`SetForegroundWindow`/`AttachThreadInput`）照旧丢 `touch-worker` 线程。
- 消息循环的 `stop()` 竞态：`run()` 里窗口创建后先查 `stop_flag`，已置位就立刻销毁返回，
  避免 `GetMessage` 空等。

### 12.3 为什么换掉钩子

`WH_MOUSE_LL` 那套的坑（§8.3/§11.5/§11.8）——回调超时被系统**静默卸载**、需要看门狗重装、
双守护进程互相吃掉 `LBUTTONUP`、`GetAsyncKeyState` 对注入事件返回 0——在「覆盖窗收自己
消息」模型下**全部消失**：窗口消息不走全局钩子链，没有超时卸载，没有多实例竞争，事件流
（down/move/up）由系统保证送达。

### 12.4 已验证（临时 profile 冒烟）

- `attach_loop` 挖洞正常（`frame ... native=True cuts=13`），`region reset` 干净退出；
- `touch overlay created hwnd=2f044c` —— 覆盖窗创建成功；
- 按钮几何 `hole=(...) close=... max=... min=...` 与 §11.12 像素列一致。
- 待用户真实点击验证：点胶囊 → `touch click -> min|max|close`；拖空白 → 窗口移动；
  双击空白 → 最大化/还原（日志在 `%LOCALAPPDATA%\\edge-win7-glass\\tool-debug.log`）。



## 13. 多窗口触控识别混乱：覆盖窗 Z 序不跟随前台切换（2026-11-17）

症状：多个浏览器窗口同时被接管时，点当前窗口右上角的胶囊/空白，触发的是**别的窗口**的动作
（或点击漏到桌面）。

根因：`TouchOverlay._raise_above()` 只在**挖洞几何变化**（`set_area` → `_reposition`）时执行一次，
把覆盖窗插到 target 正上方。但前台切换只移动浏览器窗口在 Z 序里的位置，**覆盖窗不动**——于是
后台窗口的覆盖窗会留在前台窗口上面，把前台窗口的 caption 点击吃掉，转发成那个后台窗口的
`WM_SYSCOMMAND`。

修法（`glass_titlebar.py`）：

1. `TouchOverlay.refresh_zorder(foreground)`：前台 → `SetWindowPos(HWND_TOP)` 顶到最上，盖过任何
   陈旧的兄弟覆盖窗；后台 → `_raise_above()` 收回到自己 target 正上方（低于前台窗口），仍能接住
   「可见 caption 角」的点击把窗口带到前台，又不抢前台窗口的点击。
2. `attach_loop` 每轮对比 `GetForegroundWindow()`，**前台状态变化时**调用 `refresh_zorder`（每窗口
   各自维护，A 变前台时 A 顶、B 收，反之亦然）。
3. 顺带修两处潜伏 bug：
   - `GetForegroundWindow` 没设 restype，默认 `c_int` 把 64 位句柄截断成 32 位；已设 `restype=wt.HWND`。
   - 句柄判等无效：ctypes 简单类型（`c_void_p`）按**身份**比较、不按值（实测
     `c_void_p(0x20FC4)==c_void_p(0x20FC4)` → `False`）。新增 `hwnd_int()` 统一转 int 再比，
     `force_foreground` / `_raise_above` 的判等一并修正。
   - 实测枚举窗口 / `GetForegroundWindow` 回传的句柄其实是**纯 Python int**（不是 `c_void_p` 实例），
     所以 `f"{hwnd:x}"` 这类格式化一直没问题；`hwnd_int` 对 int / c_void_p / None 三态都安全。

验证点（用户实测）：开两个浏览器窗口，反复 Alt-Tab / 点击切换前台，然后点当前窗口右上角胶囊，
应始终命中当前窗口；`tool-debug.log` 每次切换应出现一行 `zorder fg=True|False hwnd=...`。

## 14. 「保存并应用」不再重启浏览器：设置就地热更新（2026-11-17）

旧实现走过两版，都不该留：

1. `self.cfg = gt.Settings()` + `detach_all()` + `scan()` —— 边拆边建，覆盖窗/挖孔留下陈旧状态
   （点在了死覆盖窗上、洞没收回）。
2. 改成「关掉所有浏览器（靠 `--restore-last-session` 还原标签）→ 重启守护进程」—— 干净了，
   但用户丢会话、丢窗口位置、丢全屏状态，代价太大。

正解：**根本不用拆**。`attach_loop` 每轮（100 ms）都重新读 `cfg` 的每个值，而窗口 region 的
`key` 里已经包含 `(窗口尺寸, n=frame_px, cr=corner_px, cuts)`，所以只要把新值写进
`self.cfg.data`，下一轮 3 个稳定采样（≈0.3 s）后 region 就用新参数重画，全程不碰浏览器进程和标签。

为此补的两处：

- `gl_buttons` 原来是「attach 时决定要不要建覆盖窗」，现在**总是建**（隐藏状态：`clear()` →
  `set_area(None)` → `ShowWindow(SW_HIDE)`），每轮按 `cfg.gl_buttons` 决定是否 `set_area` +
  `refresh_zorder`。关掉时清空 = 隐藏窗口，点不再被吃掉；挖孔那一刀也不再进 `cuts`。
- 删掉 `restart_everything` / `relaunch_daemon` 与已无用的 `process_path` / `process_user_data_dir`。
  只有 `port` 变了才就地 `start_http()` 重绑（不影响浏览器）。
