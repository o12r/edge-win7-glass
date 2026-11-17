# settings.json

`glass_titlebar.py` reads `%APPDATA%\edge-win7-glass\settings.json` (CLI flags override it).

当前形态：**Chromium 原生标签条 + 四边窄玻璃边框**，右上角交给 OpenGlass 画 Win7 按钮。
自绘标签那套（宽度/圆角/悬停/favicon/滚轮/双色渐变）已从代码里删除。

```json
{
  "frame_px": 4,
  "gl_buttons": true,
  "theme": "light",

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
| `btn_pad_right_px` | DIP | 胶囊组右缘到窗口右缘的距离（Win7 是 7）。OpenGlass `CaptionButtons=2` 用这套指标 |
| `btn_min_px` | DIP | `−` 和 `□` 每个胶囊的宽度（Win7 30） |
| `btn_close_px` | DIP | `✕` 胶囊宽度（Win7 50） |
| `btn_top_px` | DIP | 胶囊顶部相对窗口顶部的偏移，默认 0 |
| `btn_h_px` | DIP | 胶囊高度，0 = 用整条标签带的高度 |
| `btn_h_fix_px` | DIP | 挖孔高度修正，负值减小；挖孔底部侵入窗口内容区时设为负（如 −3），默认 0 |
| `port` | int | 设置页端口，默认 8721（占用时自动 +1） |
| `autostart` | bool | 开机自启（写 `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`） |

## `theme`（唯一保留的自绘遗留项）

`light` / `dark`，只驱动托盘菜单里的勾选标记；实际配色（玻璃、标题按钮）由 OpenGlass 管。

## 热应用

守护进程（`gt_daemon.py`）的设置页改完点「保存并应用」即可生效（实现上是断开所有窗口再
重新接管，会闪一下）。命令行单窗口模式需要重启进程。

命令行覆盖（仅 `glass_titlebar.py` 单窗口模式）：

```bash
--theme dark
--settings <path>      # 换一个配置文件
```
