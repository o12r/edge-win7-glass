# 现状交接（新会话从这里开始）

> 上次更新时间点：**方向已改为「原生标签 + 四边窄玻璃边框」**，右上角按钮交给 OpenGlass。
> 自绘标签那套（`layout_tabs`/`render`/`Overlay`/`Favicons`/`Theme`）已**整段删除**，不再保留开关。

## 一句话现状

Windows 上所有 Chromium 系浏览器窗口被守护进程接管：四边各切 `frame_px`（默认 4 CSS px）
露出 OpenGlass 玻璃，右上角（`+` 右侧到窗口右缘、标签带高度）整块挖掉，由 OpenGlass 画
Win7 胶囊按钮 `− □ ✕`；那个角落上盖一个**隐形分层窗口（`TouchOverlay`）**，由它自己的
WndProc 直接收鼠标：点胶囊转成 `WM_SYSCOMMAND` 发回窗口，空白处拖动/双击最大化。
**命中表按 Win7 胶囊指标算（`win7_caption_buttons()`），覆盖窗 rect = 挖洞 rect**——洞、
覆盖窗、命中三者同一源，点画出来的 `−` 不会落到原生 `□` 上（FINDINGS §11.13 / §12）。
**标签条完全是 Chromium 原生的**：图标、文字、关闭按钮、命中、拖拽重排都不用我们操心。
洞里的任何点击都会把窗口拉到前台。四边 resize 本轮不做（以后单独补覆盖窗）。**全屏
（F11）不接管**：只清一次 region 就撒手，否则 Chromium 全屏下自动显隐的标签条会让洞闪。

## 怎么跑

### 常驻模式（推荐）

```bash
cd /c/Users/oscar/Projects/edge-win7-glass

.venv/Scripts/python.exe tools/native/gt_daemon.py --console   # 前台看日志
.venv/Scripts/pythonw.exe tools/native/gt_daemon.py            # 无控制台常驻
.venv/Scripts/python.exe tools/native/gt_daemon.py --quit      # 让实例退出
```

- 自动接管**所有** Chromium 系浏览器窗口（msedge/chrome/brave/vivaldi/chromium/opera/
  yandex/thorium），新建窗口 1 秒内接管。
- 设置页：<http://127.0.0.1:8721/>（托盘左键也能打开）；保存后自动重新接管。
- 托盘右键：打开设置页 / 浅色 / 深色 / 暂停接管 / 开机自启 / 退出。
- 退出一定还原所有窗口 region（`GetWindowRgn` 返回 0 验证过）。
- 测试只想接管一个窗口时：`GT_ONLY_HWND=<hwnd> python gt_daemon.py --console`。

### 单窗口模式（调试用）

```bash
cd /c/Users/oscar/Projects/edge-win7-glass

# 挂到某个 Edge 窗口（PID 或 hwnd 二选一）
.venv/Scripts/python.exe tools/native/glass_titlebar.py --pid <msedge pid>
.venv/Scripts/python.exe tools/native/glass_titlebar.py --hwnd 0x... --theme dark|light

# 常用开关
--settings <path>        # 换配置文件，默认 %APPDATA%\edge-win7-glass\settings.json

# 只还原窗口形状（进程被 kill 后洞会残留，用这个清）
.venv/Scripts/python.exe tools/native/glass_titlebar.py --hwnd <hwnd> --reset

# 调试日志（GLASS_TITLEBAR_DEBUG=1 时写 %LOCALAPPDATA%\edge-win7-glass\tool-debug.log）
```

临时 profile 用来试验，不动用户的 Edge：
`.venv/Scripts/python.exe tools/native/launch_scratch.py <name>`（输出 hwnd）。

配置项说明见 `docs/settings.md`。

## 已验证的行为

| 操作 | 结果 |
|---|---|
| 点标签 | 切换标签 + 把窗口切前台 |
| 点标签 `×` | 关闭该标签 |
| 点 `+` | 新建标签（Ctrl+T） |
| 点左侧箭头 | 标签搜索（Ctrl+Shift+A） |
| 悬停标签 / `×` / `+` / 箭头 | 高亮（40 ms 节流） |
| 拖空白处 | 移动窗口 |
| 双击空白处 | 最大化 / 还原 |
| 原生 `− □ ✕`（OpenGlass 胶囊） | 由覆盖窗转 `WM_SYSCOMMAND`（§12 改，待真实点击复验） |
| 全屏 (F11) | band 消失 → 立即清洞，按钮恢复可用 |
| 窗口移动/最大化 | 洞与覆盖层跟随（UIA 每 0.2s 采样） |
| 1 / 4 / 12 个标签 | 宽度 440 / 440 / 168 px，全部落在 `+` 左侧，点击精度不变 |
| favicon | 真实图标（GitHub 猫、Wiki W、HN 橙块、地球…），浅色/深色主题各自染色 |

压力测试（上一轮）：10 次/秒 50 连点 → 50/50 命中；60 次 @13/s → 60/60；
45/s 时约 1/4 被系统合并丢弃（LL 钩子固有上限）。本轮把钩子里的阻塞动作
（UIA、`SetForegroundWindow`、`keybd_event`）全部移到工作线程，延迟/穿透应更少。

## 代码结构

- `tools/native/gt_daemon.py`（约 700 行）— 常驻：单实例互斥体、窗口扫描/attach 线程池、
  ctypes 托盘、本地设置页 HTTP、开机自启。
- `tools/native/glass_titlebar.py`（约 1500 行）— 模块内部：
  - `Settings` — `%APPDATA%\edge-win7-glass\settings.json`；CLI 覆盖文件。
  - `UiaWorker` — 独立线程 + 独立 COM STA，每 0.2s 采一次 tabs（名字/矩形/选中态）、
    `Minimize/Maximize/Close/New Tab/Search tabs` 矩形；3s 没新样本就丢线程重启。
    原生模式下 tabs 只用来算标签带高度，按钮矩形只用来决定挖孔左边界。
  - `frame_region()` / `round_corner_cut()` — 四边内缩圆角矩形减去右上角挖口。
  - `win7_caption_buttons()` — OpenGlass 在洞里画的 Win7 胶囊指标（挖孔与命中同一源）。
  - `TouchOverlay` — 隐形分层窗口（alpha=1），盖在挖洞 rect 上，自己的消息循环收鼠标：
    胶囊点击 → `WM_SYSCOMMAND`、空白拖动/双击最大化、洞内点击 → 前台；`SetCapture` 保证
    拖动不丢（FINDINGS §12）。四边 resize 不做。
  - `attach_loop()` — 单窗口主循环：快照 → 校验（全屏/陈旧矩形就清洞）→ 设 region →
    驱动 `TouchOverlay.set_area`。CLI（`main()`）和守护进程共用。

## 已知限制 / 下一步可做

1. **OpenGlass 按钮没有悬停/按压反馈**：现在只有点击转发（`WM_SYSCOMMAND`）。想要
   Win7 那种发光效果得往 OpenGlass 发 `WM_NCMOUSEMOVE`（带 `HTCLOSE`/`HTMAXBUTTON` …），
   没验证过，属于锦上添花。
2. **四边窄边会吃掉内容**：`frame_px` 越大露玻璃越多，但页面/标签条边缘被切掉的越多，
   4 CSS px 是目前观感和可用性的折中。
3. **热应用靠重连**：保存设置会断开所有窗口再接管（有明显一瞬），以后可以做成
   「原地重设 region」。
4. **多显示器 / 混合 DPI**：`scale` 取自目标窗口 DPI，跨屏拖动时的行为没测过。
5. **进程被 kill 会残留洞**：托盘退出和 API 退出都会还原，但 `taskkill` 不会；
   重新启动或 `--reset` 兜底。
6. **Chromium 最小宽度 500 DIP**（200% 屏 = 1000 物理像素）：比这更窄的缩放会被系统拒绝，
   不是我们的 bug（实测直接 `SetWindowPos` 也一样）。
7. **边框优先于 caption**：顶部 8 px 边框和 caption 带重叠，必须先判边框，否则顶边永远
   变成"拖窗口"。
8. **`GetAsyncKeyState` 对注入的鼠标事件返回 0**：不要用它判断按键是否还按着，只信钩子事件流。
9. **守护进程必须单实例**：两个同时跑会互相吃掉 `LBUTTONUP`，残留的 `moving/resizing` 用旧矩形
   反复 `SetWindowPos`，表现就是窗口"高频率强制复位"。单实例检查用 `k32.GetLastError()`
   （`ctypes.GetLastError()` 对 `windll` 永远是 0）。

## 相关文件

- `tools/native/glass_titlebar.py` — 当前主工具（`frame_region` + 原生标签 + `TouchOverlay`；
  自绘标签代码已删除）
- `tools/native/gt_daemon.py` — 守护进程 + 托盘 + 设置页
- `tools/native/launch.bat` — 无控制台启动守护进程
- `tools/native/launch_scratch.py` — 临时 profile 启动器
- `tools/native/ogprobe.cpp` / `build.bat` — 进程内 DWM/样式探针源码（本轮未用；`build.bat` 重新编出 dll）
- `tools/capmain.ps1` / `tools/shot2.ps1` — 按 msedge 主窗口 / 全屏截图取证
- `docs/settings.md` — settings.json 各字段说明（含哪些已停用）
- `FINDINGS.md` — §8 挖洞路线、§9 自绘观感、§10 守护进程、§11 原生标签 + 窄边（最新）

## 环境

- Windows 11，DPI 200%（band 高 82px，`--scale` 自动 2.0）
- `.venv` 已装 `uiautomation`、`comtypes`、`pillow`
- 用户明确要求：**不要动他们正在用的 Edge 窗口**，实验只用临时 profile
