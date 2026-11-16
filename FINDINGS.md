# FINDINGS — 已做的实验与结论

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
