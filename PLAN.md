# PLAN — 从真机 Win7 取资源，移植到现代 Edge

## 阶段 0：基线（已完成）
- 已确认系统侧玻璃正常（OpenGlass 已是 Win7 预设）。
- 已确认 Chromium 侧无玻璃边框代码路径。见 `FINDINGS.md`。

## 阶段 1：Win7 真机/虚拟机取样

**环境**：Win7 SP1 x64 虚拟机（VMware/VirtualBox/Hyper-V 均可），开启 Aero 主题，
分辨率 1920×1080、100% 缩放（避免 DPI 干扰），关闭 ClearType 干扰项可选。

1. 装 **Edge 109.0.x**（最后一个支持 Win7 的版本，离线 msi）或 **Chrome 109**，二者玻璃表现一致。
2. 打开 2~3 个标签页，截图（PNG，勿缩放后截），标注：
   - 标签栏总高度、玻璃 caption 高度、窗口最小宽度下的按钮组宽度；
   - 活动/非活动标签的玻璃透出程度、标签分隔线；
   - `+`、tab-search 按钮位置；最小化/最大化/关闭按钮的边界与间距。
3. 用工具量：
   - `DwmGetWindowAttribute(hwnd, DWMWA_EXTENDED_FRAME_BOUNDS)` 与 `GetWindowRect` 差值 → 边框厚度；
   - `Spy++`/`GetWindowLong(GWL_STYLE)`：确认是 `WS_CAPTION|WS_THICKFRAME`（非客户区）；
   - `GetSystemMetrics(SM_CYCAPTION/CXSIZE/CYSIZE)` 记录 aero 下的值。
   - 抓一份 `aero.msstyles` 的 metric 表（见下）。
4. **取资源文件**（这是本次核心产物）：
   - `C:\Windows\Resources\Themes\Aero\aero.msstyles` + `aero.msstyles.mui`
   - `C:\Windows\Resources\Themes\Aero\aero.dll`（标题发光/玻璃反射着色）
   - `C:\Windows\System32\themeui.dll`（可选，玻璃颜色化逻辑）
   - 用 Windows Style Builder / `msstyles` 解析脚本导出：
     - `CAPTIONHEIGHT`、`CAPTIONWIDTH`、`SMALL_CAPTIONHEIGHT`
     - 按钮尺寸 `BUTTONWIDTH/BUTTONHEIGHT`，四态贴图（normal/hot/pressed/disabled）
     - 玻璃边距（glass margin / non-client 尺寸）、`SQUEEGEREFLECTIONMAP` 反射位图
     - 标题文字发光色与描边（OpenGlass 的 `TextGlowMode` 对应项）
   - 把导出的 PNG/度量存进 `assets/win7-aero/`（新建目录），源文件放 `assets/win7-aero/raw/`。

> 同时把 **Chromium 109** 的 `glass_browser_frame_view.cc`（tag `109.0.5414.x`）
> 与 `browser_frame_view_layout_*` 里的常量抄进 `docs/chromium109-glass-frame.md`：
> 标签栏高度、玻璃 view 如何 `DwmExtendFrameIntoClientArea`、按钮如何用 `NonClientHitTest`。
> 这份源码是"标签页画在玻璃上"的权威度量，比肉眼截图准。

## 阶段 2：移植方案（按可行性排序）

### 方案 A（推荐先做）：系统级 Win7 主题 + Edge 系统标题栏
- 用 UltraUXThemePatcher 解锁 msstyles，装移植版 Win7 Aero 主题（配合已装 OpenGlass）。
- Edge：`edge://settings/appearance` → 使用系统标题栏和边框。
- 效果：真 Win7 玻璃 caption + aero 胶囊按钮（与参考图按钮 100% 一致），
  标签栏在其下方。**代价**：标签栏不在玻璃上，达不到参考图的一行式。
- 验收：截图对比按钮、玻璃边框、文字发光。

### 方案 B（最贴近参考图）：Windhawk mod 把标签栏"玻璃化"
- 注入 `msedge.exe`，做两件事：
  1. `DwmExtendFrameIntoClientArea(hwnd, {margins = 标签栏高度})`，让顶部成为扩展框 → OpenGlass/DWM 出玻璃；
  2. 让 TabStrip/Toolbar 的顶部只画标签与按钮、背景透明（hook Views `OnPaintBackground` 或该控件的背景画笔）。
- 风险：OpenGlass 会在扩展框上补一条自己的 caption（标题文字+按钮），
  可能需要 `CaptionButtons`/`CenterCaption` 调小、或按进程排除，避免双按钮。
- 收益：真正一行式的 Win7 玻璃标题栏，可复用阶段 1 的 aero 度量与贴图。

### 方案 C（最彻底）：自建 Chromium 分支
- fork Chromium，强制 `ShouldUseGlassBrowserFrame()` 复用 109 的 `GlassBrowserFrameView`
  并把 `IsAeroGlassEnabled()` 在 Win11 打桩为 true，编译出 `msedge` 替代品。
- 收益：与参考图逐像素一致；代价：几十 GB 编译链、无 Edge 特性（登录/同步/更新）。

### 方案 D（保底）：只做"观感接近"
- Edge 保持自绘边框（单层），用深色/浅色主题 + 圆角 + 顶部 1px 高光模拟；
  或在 OpenGlass 里给 Edge 单独做排除，避免双层标题栏。

## 阶段 3：验证
- 统一用 `tools/capmain.ps1`（按 `msedge.exe` 主窗口抓图）与 `tools/shot2.ps1`（全屏）取证，
  截图存 `captures/exp-<日期>-<方案>.png`。
- 判定标准：①只有一层标题栏；②按钮为 aero 胶囊四态；③标签栏透出桌面模糊；④非活动窗口玻璃变淡、文字去发光。

## 待办清单
- [ ] Win7 SP1 虚拟机 + Aero + Edge/Chrome 109
- [ ] 采样截图与窗口度量（脚本 + Spy++）
- [ ] 导出 aero.msstyles 度量/贴图到 `assets/win7-aero/`
- [ ] 抄录 Chromium 109 GlassBrowserFrameView 关键常量
- [ ] 按方案 A 先做一次可交付效果并截图
- [ ] 评估方案 B 的 hook 点（扩展框 + 标签栏背景透明）
- [ ] 若走 B/C：解决 OpenGlass 双 caption 冲突
