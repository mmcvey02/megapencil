"""Dock panel registry: (title, object name, class)."""
from .align import AlignPanel
from .color import ColorPanel
from .layers import LayersPanel
from .properties import PropertiesPanel
from .stroke import StrokePanel

PANELS = [
    ("Properties", "panel_properties", PropertiesPanel),
    ("Align", "panel_align", AlignPanel),
    ("Color", "panel_color", ColorPanel),
    ("Stroke", "panel_stroke", StrokePanel),
    ("Layers", "panel_layers", LayersPanel),
]
