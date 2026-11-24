Edge Win7 Glass 1.1.0
=====================

给 Windows 11 上的 Chromium 系浏览器（Edge / Chrome / Brave / Vivaldi / Chromium /
Opera / Yandex / Thorium）换上 Windows 7 Aero 玻璃标题栏：
四边各切一条窄边露出玻璃，右上角整块挖掉交给 OpenGlass 画 Win7 胶囊按钮
（− □ ✕），标签条保持 Chromium 原生。

前置条件
--------
1. Windows 11（需要 DWM 的系统玻璃）。
2. OpenGlass（Windhawk mod）已安装，并建议配置
     CaptionButtons = 2        （画 Win7 指标的三颗胶囊按钮）
     CornerRadius  = 与设置里的 corner_px 一致（默认 10）
   参考 docs/openglass-config-reference.md。

启动 / 使用
-----------
* 安装后从开始菜单启动 "Edge Win7 Glass"（或桌面快捷方式）。
  启动后常驻托盘，所有 Chromium 浏览器窗口自动接管，新建窗口约 1 秒内接管。
* 托盘图标：左键 = 打开设置页；右键 = 设置页 / 暂停接管 / 开机自启 / 退出。
* 设置页： http://127.0.0.1:8721/   （端口可在设置里改，占用时自动 +1）
  改完点"保存并应用"即时生效，不用重启浏览器。
* 退出（托盘 → 退出）会还原所有窗口形状；用任务管理器强杀会残留挖孔，
  重新启动一次或运行 "EdgeWin7Glass.exe --reset" 即可清掉。

配置文件
--------
%APPDATA%\edge-win7-glass\settings.json     设置（字段说明见同目录 settings.md）
%APPDATA%\edge-win7-glass\daemon.log        运行日志

命令行
------
  EdgeWin7Glass.exe              启动（已有实例时会打开设置页）
  EdgeWin7Glass.exe --quit       让正在运行的实例优雅退出

卸载
----
设置 → 应用 → 已安装的应用 → Edge Win7 Glass → 卸载。
卸载时会先优雅退出守护进程（还原窗口形状），可选择是否删除设置和日志。

已知限制
--------
* 边框会吃掉一点窗口内容边缘，frame_px 默认 5 CSS px。
* 四边 resize 仍靠 Windows 原生边框区域，暂未接管。
* 多显示器 / 混合 DPI 场景未充分测试。
