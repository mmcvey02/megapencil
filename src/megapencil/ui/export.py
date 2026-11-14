"""PNG and PDF export of the artboard."""
from __future__ import annotations

from PySide6.QtCore import QMarginsF, QRectF, QSizeF, Qt
from PySide6.QtGui import QImage, QPageLayout, QPageSize, QPainter, QPdfWriter

from ..model.items import Document
from .scene import DocumentScene


class _ExportScene(DocumentScene):
    def drawBackground(self, painter, rect) -> None:  # no pasteboard / page
        pass


def _scene(doc: Document) -> _ExportScene:
    return _ExportScene(doc)


def _release(doc: Document, scene: DocumentScene) -> None:
    doc.listeners.remove(scene._on_doc_change)
    scene.clear()


def render_image(doc: Document, scale: float = 1.0, transparent: bool = True) -> QImage:
    w, h = max(1, int(round(doc.width * scale))), max(1, int(round(doc.height * scale)))
    img = QImage(w, h, QImage.Format_ARGB32_Premultiplied)
    img.fill(Qt.transparent if transparent else Qt.white)
    scene = _scene(doc)
    p = QPainter(img)
    p.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
    scene.render(p, QRectF(0, 0, w, h), QRectF(0, 0, doc.width, doc.height))
    p.end()
    _release(doc, scene)
    return img


def export_png(doc: Document, path: str, scale: float = 1.0, transparent: bool = True) -> bool:
    return render_image(doc, scale, transparent).save(path, "PNG")


def export_pdf(doc: Document, path: str, scale: float = 1.0) -> bool:
    """Vector PDF; 1 px = 0.75 pt at scale 1."""
    writer = QPdfWriter(path)
    writer.setCreator("MegaPencil")
    size = QSizeF(doc.width * 0.75 * scale, doc.height * 0.75 * scale)
    writer.setPageLayout(QPageLayout(QPageSize(size, QPageSize.Point), QPageLayout.Portrait, QMarginsF(0, 0, 0, 0)))
    writer.setResolution(300)
    scene = _scene(doc)
    p = QPainter(writer)
    if not p.isActive():
        _release(doc, scene)
        return False
    p.setRenderHint(QPainter.Antialiasing)
    scene.render(p, QRectF(0, 0, writer.width(), writer.height()), QRectF(0, 0, doc.width, doc.height))
    p.end()
    _release(doc, scene)
    return True
