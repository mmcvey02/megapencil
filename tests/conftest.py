import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest


@pytest.fixture(scope="session")
def qapp():
    from megapencil.app import create_app

    return create_app(["test"])


@pytest.fixture
def window(qapp, tmp_path, monkeypatch):
    """A MainWindow with isolated settings / data directories and one document."""
    from PySide6.QtCore import QSettings

    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    QSettings.setPath(QSettings.NativeFormat, QSettings.UserScope, str(tmp_path / "config"))
    from megapencil.ui.mainwindow import MainWindow

    win = MainWindow(interactive=False)
    win.resize(1400, 900)
    win.show()
    win.new_document(800, 600)
    qapp.processEvents()
    yield win
    win.close()
    win.deleteLater()
    qapp.processEvents()
