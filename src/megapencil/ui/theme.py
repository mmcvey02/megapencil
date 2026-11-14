"""Dark and light themes."""
from __future__ import annotations

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

THEMES = {
    "dark": dict(window="#323232", base="#262626", text="#e6e6e6", button="#444444", highlight="#2f80ed",
                 disabled="#7a7a7a", pasteboard="#535353", icon="#e0e0e0", border="#1e1e1e", alt="#2c2c2c"),
    "light": dict(window="#ececec", base="#ffffff", text="#1a1a1a", button="#e0e0e0", highlight="#2f80ed",
                  disabled="#9a9a9a", pasteboard="#c8c8c8", icon="#333333", border="#b4b4b4", alt="#f4f4f4"),
}
_current = "dark"


def current() -> dict:
    return THEMES[_current]


def current_name() -> str:
    return _current


def apply_theme(app: QApplication, name: str) -> None:
    global _current
    _current = name if name in THEMES else "dark"
    t = THEMES[_current]
    app.setStyle("Fusion")
    p = QPalette()
    for role, key in ((QPalette.Window, "window"), (QPalette.Base, "base"), (QPalette.AlternateBase, "alt"),
                      (QPalette.Button, "button"), (QPalette.ToolTipBase, "base"), (QPalette.Highlight, "highlight")):
        p.setColor(role, QColor(t[key]))
    for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText, QPalette.ToolTipText):
        p.setColor(role, QColor(t["text"]))
        p.setColor(QPalette.Disabled, role, QColor(t["disabled"]))
    p.setColor(QPalette.HighlightedText, QColor("#ffffff"))
    p.setColor(QPalette.PlaceholderText, QColor(t["disabled"]))
    p.setColor(QPalette.Link, QColor(t["highlight"]))
    app.setPalette(p)
    app.setStyleSheet(f"""
        QToolTip {{ color: {t['text']}; background: {t['base']}; border: 1px solid {t['border']}; }}
        QDockWidget::title {{ background: {t['alt']}; padding: 4px; }}
        QToolButton {{ border: 1px solid transparent; border-radius: 3px; padding: 2px; }}
        QToolButton:hover {{ border-color: {t['disabled']}; }}
        QToolButton:checked {{ background: {t['highlight']}; }}
        QTabBar::tab {{ padding: 5px 12px; }}
        QStatusBar::item {{ border: none; }}
    """)
