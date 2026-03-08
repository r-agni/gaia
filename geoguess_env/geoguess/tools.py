"""
Tool dispatch layer for GeoGuessr env.

Centralizes routing from action tool_name → provider.resolve().
All providers share the same interface: async def resolve(location, params) -> str
"""
from __future__ import annotations

from .models import GeoLocation, ToolResult, AVAILABLE_TOOLS
from .tool_providers import (
    weather,
    terrain,
    street_view,
    sun_angle,
    building_style,
    language_detection,
)


async def resolve_tool(
    tool_name: str,
    location: GeoLocation,
    params: dict,
    step: int,
) -> ToolResult:
    """
    Dispatch a tool call and return a ToolResult.
    Raises ValueError for unknown tool names.
    """
    if tool_name not in AVAILABLE_TOOLS:
        raise ValueError(
            f"Unknown tool {tool_name!r}. Available: {AVAILABLE_TOOLS}"
        )

    match tool_name:
        case "weather":
            text = await weather.resolve(location, params)
        case "terrain_analysis":
            text = await terrain.resolve_terrain(location, params)
        case "globe_view":
            text = await terrain.resolve_globe_view(location, params)
        case "street_view":
            text = await street_view.resolve(location, params)
        case "sun_angle":
            text = await sun_angle.resolve(location, params)
        case "building_style":
            text = await building_style.resolve(location, params)
        case "language_detection":
            text = await language_detection.resolve(location, params)
        case _:
            text = f"Tool {tool_name!r} not implemented."

    return ToolResult(
        tool_name=tool_name,
        invoked_at_step=step,
        result_text=text,
    )
