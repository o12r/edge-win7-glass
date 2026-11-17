# settings.json

`glass_titlebar.py` reads `%APPDATA%\edge-win7-glass\settings.json` (CLI flags override it).

当前形态：**Chromium 原生标签条 + 四边窄玻璃边框**，右上角交给 OpenGlass 画 Win7 按钮。
自绘标签那套（宽度/圆角/悬停/favicon/滚轮/双色渐变）已从代码里删除。

```json
{
  "frame_px": 5,
  "corner_px": 10,
  "gl_buttons": true,
  "btn_pad_right_px": 7,
  "btn_min_px": 30,
  "btn_close_px": 50,
  "btn_top_px": 0,
  "btn_h_px": 20,
  "btn_h_fix_px": -1,

  "port": 8721,
  "autostart": false,
  "lang": "zh"
}
```

以上同时是 `glass_titlebar.Settings.DEFAULTS` 的当前值（删掉 settings.json 就回到这套）。

## 生效项

| key | 单位 | 说明 |
|---|---|---|
| `frame_px` | CSS px | 四边各切多宽露出玻璃（按 DPI 缩放；默认 5 → 200% 屏上 10 物理像素） |
| `corner_px` | CSS px | 上面两个角（以及右上角挖口）的圆角半径，0 = 直角，默认 10 |
| `gl_buttons` | bool | `true` 挖掉右上角按钮区，由 OpenGlass 画 Win7 胶囊按钮；`false` 保留 Chromium 原生按钮 |
| `btn_pad_right_px` | DIP | 胶囊组右缘到窗口右缘的距离（Win7 是 7）。OpenGlass `CaptionButtons=2` 用这套指标 |
| `btn_min_px` | DIP | `−` 和 `□` 每个胶囊的宽度（Win7 30） |
| `btn_close_px` | DIP | `✕` 胶囊宽度（Win7 50） |
| `btn_top_px` | DIP | 胶囊顶部相对窗口顶部的偏移，默认 0 |
| `btn_h_px` | DIP | 胶囊高度，0 = 用整条标签带的高度，默认 20 |
| `btn_h_fix_px` | DIP | 挖孔高度修正，负值减小；挖孔底部侵入窗口内容区时设为负（如 −3），默认 -1 |
| `port` | int | 设置页端口，默认 8721（占用时自动 +1） |
| `autostart` | bool | 开机自启（写 `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`） |
| `lang` | str | 界面语言：`"zh"`（当前默认）/ `"auto"`（跟随 Windows 显示语言：中文 → zh，其它 → en）/ `"en"`。影响托盘菜单、托盘提示和设置页；设置页底部“语言”卡片可直接改 |

## 热应用

守护进程（`gt_daemon.py`）的设置页改完点「保存并应用」即刻生效，**不重启浏览器、不动标签**：
每个窗口的接管线程每轮都重新读一遍设置，数值一变就在下一轮把窗口 region 重算一次（约 0.3 s），
`gl_buttons` 关掉时只是把覆盖窗清空并收回右上角挖孔；语言即时生效（托盘菜单每次弹出时重建）。
唯一需要重新绑定的是 `port`（改了会就地重启内置 HTTP 服务，不影响浏览器）。

命令行单窗口模式（`glass_titlebar.py --hwnd`）仍然需要重启进程才会读到新值。

命令行覆盖（仅 `glass_titlebar.py` 单窗口模式）：

```bash
--settings <path>      # 换一个配置文件
```
