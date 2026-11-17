"""gt_i18n.py - tiny translation table for the daemon (tray menu + settings page).

Language is picked in this order:
  * the `lang` setting in settings.json  ("zh" / "en" pin the language, "auto" = system)
  * Windows' user UI language (GetUserDefaultUILanguage), Chinese -> zh, anything else -> en
  * LANG / LCREATE env as a last resort outside Windows

The same STRINGS dict is what the settings page embeds, so the page and the tray
menu can never drift apart.
"""
from __future__ import annotations

import ctypes
import os

LANGS = ("auto", "zh", "en")          # values accepted by the `lang` setting

STRINGS = {
    "zh": {
        # tray
        "menu_settings": "打开设置页",
        "menu_pause": "暂停接管",
        "menu_resume": "恢复接管",
        "menu_autostart": "开机自启",
        "menu_quit": "退出",
        "tip_paused": "已暂停",
        "tip_windows": "{n} 个窗口",
        # page
        "page_title": "Edge Win7 Glass · 设置",
        "loading": "读取中…",
        "state_paused": "已暂停",
        "state_windows": "{n} 个窗口",
        "subtitle": "原生标签 + 四边窄玻璃边框 · 设置保存在",
        "sec_appearance": "外观",
        "sec_daemon": "守护",
        "sec_language": "语言",
        "sec_windows": "当前接管的窗口",
        "frame_px": "玻璃边框宽度",
        "frame_px_hint": "CSS px，四边各切这么宽露玻璃",
        "corner_px": "顶角圆角",
        "corner_px_hint": "CSS px，左右上角；0 = 直角",
        "gl_buttons": "右上角用 OpenGlass 按钮",
        "gl_buttons_hint": "挖掉 Chromium 按钮区，让 OpenGlass 画 Win7 胶囊按钮（本体点击会被转发）",
        "btn_pad_right_px": "胶囊右缘留白",
        "btn_pad_right_px_hint": "DIP，OpenGlass 画的是 Win7 指标（默认 7）",
        "btn_min_px": "−/□ 胶囊宽度",
        "btn_min_px_hint": "DIP（默认 30）",
        "btn_close_px": "✕ 胶囊宽度",
        "btn_close_px_hint": "DIP（默认 50）",
        "btn_top_px": "胶囊顶部偏移",
        "btn_top_px_hint": "DIP，相对窗口顶部（默认 0）",
        "btn_h_px": "胶囊高度",
        "btn_h_px_hint": "DIP，0 = 整条标签带",
        "btn_h_fix_px": "挖孔高度修正",
        "btn_h_fix_px_hint": "DIP，负值减小（挖孔底部侵入窗口内容区时设为负，如 -3）",
        "autostart": "开机自启",
        "autostart_hint": "写入 HKCU\\...\\Run",
        "port": "设置页端口",
        "lang": "界面语言",
        "lang_hint": "自动 = 跟随系统语言",
        "lang_auto": "自动（跟随系统）",
        "lang_zh": "中文",
        "lang_en": "English",
        "btn_save": "保存并应用",
        "btn_refresh": "刷新",
        "btn_quit": "退出守护进程",
        "no_title": "(无标题)",
        "toast_saved": "已保存，正在重新接管窗口",
        "toast_fail": "保存失败",
        "confirm_quit": "退出守护进程？所有窗口的玻璃标题栏会恢复成原生样式。",
        "quit_done": "守护进程已退出。",
    },
    "en": {
        # tray
        "menu_settings": "Open settings",
        "menu_pause": "Pause attaching",
        "menu_resume": "Resume attaching",
        "menu_autostart": "Start with Windows",
        "menu_quit": "Quit",
        "tip_paused": "paused",
        "tip_windows": "{n} windows",
        # page
        "page_title": "Edge Win7 Glass · Settings",
        "loading": "Loading…",
        "state_paused": "Paused",
        "state_windows": "{n} windows",
        "subtitle": "Native tabs + thin glass frame · settings saved to",
        "sec_appearance": "Appearance",
        "sec_daemon": "Daemon",
        "sec_language": "Language",
        "sec_windows": "Managed windows",
        "frame_px": "Glass frame width",
        "frame_px_hint": "CSS px cut from every edge to reveal the glass",
        "corner_px": "Top corner radius",
        "corner_px_hint": "CSS px on the two top corners; 0 = square",
        "gl_buttons": "OpenGlass buttons in the top-right",
        "gl_buttons_hint": "Cut out Chromium's button area so OpenGlass paints Win7 capsules (clicks are forwarded)",
        "btn_pad_right_px": "Capsule right margin",
        "btn_pad_right_px_hint": "DIP; OpenGlass draws Win7 metrics (default 7)",
        "btn_min_px": "−/□ capsule width",
        "btn_min_px_hint": "DIP (default 30)",
        "btn_close_px": "✕ capsule width",
        "btn_close_px_hint": "DIP (default 50)",
        "btn_top_px": "Capsule top offset",
        "btn_top_px_hint": "DIP from the window top (default 0)",
        "btn_h_px": "Capsule height",
        "btn_h_px_hint": "DIP; 0 = the whole tab band",
        "btn_h_fix_px": "Hole height correction",
        "btn_h_fix_px_hint": "DIP; negative shrinks it (e.g. -3 when the hole eats into the page)",
        "autostart": "Start with Windows",
        "autostart_hint": "written to HKCU\\...\\Run",
        "port": "Settings page port",
        "lang": "Language",
        "lang_hint": "Auto = follow the system language",
        "lang_auto": "Auto (follow system)",
        "lang_zh": "中文",
        "lang_en": "English",
        "btn_save": "Save & apply",
        "btn_refresh": "Refresh",
        "btn_quit": "Quit daemon",
        "no_title": "(untitled)",
        "toast_saved": "Saved — re-attaching windows",
        "toast_fail": "Save failed",
        "confirm_quit": "Quit the daemon? Every window returns to its native title bar.",
        "quit_done": "The daemon has exited.",
    },
}


def system_lang():
    """Language Windows talks to the user in: 'zh' when the UI language is Chinese."""
    try:
        lid = ctypes.windll.kernel32.GetUserDefaultUILanguage()
        if not lid:
            lid = ctypes.windll.kernel32.GetSystemDefaultUILanguage()
        primary = lid & 0x3FF                    # LANG_CHINESE == 0x04
        return "zh" if primary == 0x04 else "en"
    except Exception:
        pass
    for var in ("LC_ALL", "LC_MESSAGES", "LANG"):
        v = (os.environ.get(var) or "").lower()
        if v:
            return "zh" if v.startswith("zh") else "en"
    return "en"


def resolve(setting):
    """Effective language for a `lang` setting value ('auto' -> system)."""
    return setting if setting in ("zh", "en") else system_lang()


def t(lang, key, **kw):
    table = STRINGS.get(lang) or STRINGS["en"]
    s = table.get(key) or STRINGS["en"].get(key) or key
    return s.format(**kw) if kw else s
