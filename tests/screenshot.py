"""Headless smoke test: start the app, grab the main window.

    QT_QPA_PLATFORM=offscreen python tests/screenshot.py out.png [theme]
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from megapencil.app import create_app  # noqa: E402
from megapencil.ui.mainwindow import MainWindow  # noqa: E402

app = create_app(sys.argv[:1])
win = MainWindow(interactive=False)
if len(sys.argv) > 2:
    win.set_theme(sys.argv[2])
win.resize(1400, 900)
win.show()
win.new_document(800, 600)
for _ in range(5):
    app.processEvents()
out = sys.argv[1] if len(sys.argv) > 1 else "megapencil.png"
ok = win.grab().save(out)
print("saved" if ok else "failed", out)
win.close()
