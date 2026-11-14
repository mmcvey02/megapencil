"""Tool registry (toolbox order)."""
from .nav import HandTool, ZoomTool
from .select import SelectTool
from .shapes import EllipseTool, LineTool, RectTool

TOOL_CLASSES = [SelectTool, RectTool, EllipseTool, LineTool, HandTool, ZoomTool]
