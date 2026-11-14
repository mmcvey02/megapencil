"""Tool registry (toolbox order)."""
from .direct import AddAnchorTool, ConvertAnchorTool, DeleteAnchorTool, DirectSelectTool
from .nav import HandTool, ZoomTool
from .pen import PenTool
from .select import SelectTool
from .shapes import EllipseTool, LineTool, RectTool

TOOL_CLASSES = [SelectTool, DirectSelectTool, PenTool, AddAnchorTool, DeleteAnchorTool, ConvertAnchorTool,
                RectTool, EllipseTool, LineTool, HandTool, ZoomTool]
