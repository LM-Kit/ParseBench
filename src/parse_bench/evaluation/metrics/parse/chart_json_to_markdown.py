"""Render chart2json data as Markdown/HTML tables for the existing chart rules."""

from __future__ import annotations

import json
import math
import re
from html import escape
from typing import Any


def _json_objects(text: str) -> list[dict]:
    """Decode fenced or prefixed JSON, skipping malformed blocks as a whole."""
    if not isinstance(text, str) or not text.strip():
        return []
    blocks = re.findall(r"```(?:json)?[ \t]*\r?\n(.*?)```", text, re.DOTALL | re.IGNORECASE)
    objects: list[dict] = []
    if blocks:
        for block in blocks:
            try:
                obj = json.loads(block)
            except (ValueError, RecursionError):
                continue
            if isinstance(obj, dict):
                objects.append(obj)
        return objects

    start = text.find("{")
    if start < 0:
        return []
    try:
        obj, _ = json.JSONDecoder().raw_decode(text, start)
    except (ValueError, RecursionError):
        return []
    return [obj] if isinstance(obj, dict) else []


def extract_json(text: str) -> dict | None:
    """Extract the first complete JSON object, if present."""
    return next(iter(_json_objects(text)), None)


def contains_chart_json(text: str) -> bool:
    return any("values" in obj or "panels" in obj for obj in _json_objects(text))


def _is_value(value: Any) -> bool:
    return (
        isinstance(value, (str, int, float))
        and not isinstance(value, bool)
        and (not isinstance(value, float) or math.isfinite(value))
    )


def _fmt(value: Any) -> str:
    if not _is_value(value):
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _title(value: Any) -> str:
    if not isinstance(value, str) or value.strip().lower() in {"", "none", "null", "n/a"}:
        return ""
    return value.strip()


def _series_points(series: Any) -> dict[str, Any]:
    if isinstance(series, dict):
        return {str(key): value for key, value in series.items() if _is_value(value) or value is None}
    if isinstance(series, list):
        points: dict[str, Any] = {}
        for point in series:
            if not isinstance(point, dict) or not _is_value(point.get("x")) or not _is_value(point.get("y")):
                continue
            label = _fmt(point["x"])
            if label in points:
                # A table cell cannot represent two different points with the
                # same coordinate. Do not silently replace either observation.
                return {}
            points[label] = point["y"]
        return points
    return {}


def _render_table(headers: list[str], rows: list[list[str]], titles: list[str]) -> str:
    if not rows:
        return ""
    cells = [*titles, *headers, *(cell for row in rows for cell in row)]
    # The upstream Markdown parser splits literally on pipes and newlines;
    # backslash-escaping a pipe therefore cannot preserve a label.
    if not any(headers) or any(re.search(r"[|<>&\r\n]", cell) for cell in cells):
        caption_text = " / ".join(title for title in titles if title)
        caption = f"<caption>{escape(caption_text)}</caption>" if caption_text else ""
        head = "".join(f"<th>{escape(cell)}</th>" for cell in headers)
        body = "".join("<tr>" + "".join(f"<td>{escape(cell)}</td>" for cell in row) + "</tr>" for row in rows)
        # Encode pipes so the Markdown parser does not also interpret these
        # HTML rows as a second, malformed table.
        return f"<table>{caption}<thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>".replace("|", "&#124;")
    headings = [f"{'#' * (index + 1)} {title}" for index, title in enumerate(titles) if title]
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    lines.extend("| " + " | ".join(row) + " |" for row in rows)
    return "\n\n".join([*headings, "\n".join(lines)])


def _panel_to_table(titles: list[str], values: dict[str, Any]) -> str:
    if not values:
        return ""
    if all(_is_value(value) or value is None for value in values.values()):
        return _render_table(["", ""], [[str(key), _fmt(value)] for key, value in values.items()], titles)

    series = {str(name): points for name, values in values.items() if (points := _series_points(values))}
    if not series:
        return ""
    categories = list(dict.fromkeys(category for points in series.values() for category in points))
    rows = [[category, *(_fmt(points.get(category)) for points in series.values())] for category in categories]
    return _render_table(["", *series], rows, titles)


def chart_json_to_markdown(chart: dict) -> str:
    """Render each panel separately, preserving its title, series and categories."""
    if not isinstance(chart, dict):
        return ""
    figure_title = _title(chart.get("title"))
    tables: list[str] = []
    panels = chart.get("panels")
    if isinstance(panels, dict) and panels:
        for name, panel in panels.items():
            if not isinstance(panel, dict):
                continue
            values = panel.get("values") or panel.get("series")
            if isinstance(values, dict):
                # Repeat the figure title for each panel: chart rules only
                # consider the context immediately surrounding that table.
                tables.append(_panel_to_table([figure_title, _title(name)], values))
    else:
        values = chart.get("values")
        if isinstance(values, dict) and values:
            nested_panels = all(
                isinstance(panel, dict) and panel and all(isinstance(series, (dict, list)) for series in panel.values())
                for panel in values.values()
            )
            if nested_panels:
                for name, panel in values.items():
                    tables.append(_panel_to_table([figure_title, _title(name)], panel))
            else:
                tables.append(_panel_to_table([figure_title], values))
    return "\n\n".join(table for table in tables if table)


def chart_description_to_markdown(description: str) -> str:
    """Convert all complete chart JSON blocks in one figure description."""
    tables = [chart_json_to_markdown(obj) for obj in _json_objects(description)]
    return "\n\n".join(table for table in tables if table)


def normalize_markdown_with_chart_json(markdown: str) -> str:
    """Append derived chart tables while preserving the original output."""
    tables = chart_description_to_markdown(markdown)
    return f"{markdown}\n\n{tables}" if tables and markdown.strip() else tables or markdown
