"""Application entry point."""
from __future__ import annotations

import os
import sys

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from . import APP_NAME, __version__


def icon_path() -> str:
    return os.path.join(os.path.dirname(__file__), "resources", "megapencil.svg")


def create_app(argv=None) -> QApplication:
    app = QApplication.instance() or QApplication(argv if argv is not None else sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setApplicationVersion(__version__)
    app.setOrganizationName(APP_NAME)
    app.setDesktopFileName("megapencil")
    app.setWindowIcon(QIcon(icon_path()))
    return app


def main(argv=None) -> int:
    argv = list(sys.argv if argv is None else argv)
    if "--version" in argv:
        print(f"{APP_NAME} {__version__}")
        return 0
    app = create_app(argv)
    from .ui.mainwindow import MainWindow

    win = MainWindow()
    win.show()
    files = [a for a in argv[1:] if not a.startswith("-")]
    win.startup(files)
    return app.exec()
