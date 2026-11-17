# Edge/Chrome "Windows 7 Aero titlebar" 复刻项目

目标：让现代 Edge（157.x）的标题栏呈现 Windows 7 Aero Glass 外观，效果参照
`captures/` 中的参考图：玻璃标题栏 + Win7 玻璃胶囊按钮 + 标签页直接绘制在玻璃上。

现状定位（2026-11-16）：**未完成**。已确认根因，路线已改为「真机 Win7 取资源 → 移植回 Win11」。

## 目录
- `FINDINGS.md` —— 已做的实验、观察到的事实、根因分析（必读）
- `PLAN.md` —— Win7 取资源 + 移植方案、检查清单
- `docs/openglass-config-reference.md` —— OpenGlass 官方配置说明（wiki 快照）
- `tools/native/` —— 生产链路：`glass_titlebar.py`（挖洞 + 原生标签 + 输入钩子）、`gt_daemon.py`（常驻/托盘/设置页）、
  `launch_scratch.py`（临时 profile）、`launch.bat`；`ogprobe.cpp` + `build.bat` 是进程内探针源码（本轮不用）
- `tools/capmain.ps1` / `tools/shot2.ps1` —— 取证截图（PowerShell，Windows）

## 关键结论（一句话）
现代 Chromium 不再有 Aero 玻璃边框视图（`GlassBrowserFrameView` 被 `IsAeroGlassEnabled()==false` 关死），
它自己画的标签栏是**不透明**的，OpenGlass 只能给 DWM 的**非客户区**上玻璃 ——
所以要么改 Chromium 侧（Windhawk 注入 / 改 Edge 资源），要么接受"系统玻璃标题栏 + 独立标签栏"两层。
