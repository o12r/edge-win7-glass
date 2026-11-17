# settings.json

`glass_titlebar.py` reads `%APPDATA%\edge-win7-glass\settings.json` (CLI flags override it).

当前形态：**Chromium 原生标签条 + 四边窄玻璃边框**，右上角交给 OpenGlass 画 Win7 按钮。
自绘标签那一套（主题/宽度/圆角/悬停/favicon/滚轮）已停用，参数保留只为对照。

```json
{
  "frame_px": 4,
  "gl_buttons": true,

  "theme": "light",
  "tab_max_width": 220,
  "tab_min_width": 70,
  "tab_radius": 6,
  "hover": true,
  "favicons": true,
  "wheel_tabs": true,

  "port": 8721,
  "autostart": false
}
```

## 生效项

| key | 单位 | 说明 |
|---|---|---|
| `frame_px` | CSS px | 四边各切多宽露出玻璃（按 DPI 缩放；默认 4 → 200% 屏上 8 物理像素） |
| `corner_px` | CSS px | 上面两个角（以及右上角挖口）的圆角半径，0 = 直角，默认 6 |
| `gl_buttons` | bool | `true` 挖掉右上角按钮区，由 OpenGlass 画 Win7 胶囊按钮；`false` 保留 Chromium 原生按钮 |
| `port` | int | 设置页端口，默认 8721（占用时自动 +1） |
| `autostart` | bool | 开机自启（写 `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`） |

## 已停用（自绘标签模式，保留对照）

| key | 说明 |
|---|---|
| `theme` | `light` / `dark`，活动标签明暗 |
| `tab_max_width` / `tab_min_width` | 自绘标签宽度上下限（CSS px） |
| `tab_radius` | 自绘标签顶部圆角 |
| `hover` | 自绘悬停高亮 |
| `favicons` | 抓原生条像素画图标（兼容性差，正是停用原因） |
| `wheel_tabs` | 标题栏滚轮 = Ctrl+Tab（原生模式里 Chromium 自己就支持） |

## 热应用

守护进程（`gt_daemon.py`）的设置页改完点「保存并应用」即可生效（实现上是断开所有窗口再
重新接管，会闪一下）。命令行单窗口模式需要重启进程。

命令行覆盖（仅 `glass_titlebar.py` 单窗口模式）：

```bash
--theme dark
--tab-max-width 180
--no-hover
--no-favicons
--settings <path>      # 换一个配置文件
```
