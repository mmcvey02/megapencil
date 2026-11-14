"""Tool registry (toolbox order)."""
from .nav import HandTool, ZoomTool
from .shapes import EllipseTool, LineTool, RectTool

TOOL_CLASSES = [RectTool, EllipseTool, LineTool, HandTool, ZoomTool]
