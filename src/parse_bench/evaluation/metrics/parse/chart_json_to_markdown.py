"""Normalize structured chart JSON into markdown tables for chart scoring.

The chart dimension's ``ChartDataPointRule`` (rules_chart.py) scores a data point
only if its value appears in a markdown/HTML **table** cell with the rule's labels in
the same row/column (or in a heading/caption before the table). Parsers that emit a
figure's data as *structured JSON* (chart2json-style) therefore score 0 even when the
data is correct, because the value never lands in a table cell.

This module converts such chart JSON into equivalent markdown tables so the existing,
unchanged chart rules can find the points: x-axis keys become row labels, series names
become column headers, values fill the cells, and the chart/panel title becomes a
``##`` heading above the table. It is parser-agnostic — any pipeline whose output
markdown contains a chart2json JSON object can be normalized before the rules run.

Accepted JSON shapes (either as the whole output or inside a ```json fenced block):
  - single chart:   {"title": ..., "values": {series: {x: y}}}
  - multi-panel:    {"title": ..., "panels": {panel: {"series": {series: {x: y}}, ...}}}
Series values may be {x: y} dicts, lists of {"x":..,"y":..}, lists of scalars, or (for
box-whisker) a {stat_name: value} dict — all are rendered as table rows/cells.
"""

from __future__ import annotations

import json
import re
from typing import Any


def contains_chart_json(text: str) -> bool:
    """Cheap check: does the text contain a chart2json object (a JSON object with a
    top-level 'values' or 'panels' key)? Used to decide whether to normalize."""
    obj = extract_json(text)
    return isinstance(obj, dict) and ("values" in obj or "panels" in obj)


def extract_json(text: str) -> dict | None:
    """Extract the first balanced JSON object from text, tolerating ```json fences
    and surrounding prose (e.g. a leading caption line). Returns None if none parses."""
    if not text or not text.strip():
        return None
    t = text.strip()
    m = re.search(r"```(?:json)?\s*(\{)", t, re.DOTALL)
    start = m.start(1) if m else t.find("{")
    if start == -1:
        return None
    depth = 0
    for i in range(start, len(t)):
        if t[i] == "{":
            depth += 1
        elif t[i] == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(t[start : i + 1])
                except json.JSONDecodeError:
                    return None
    return None


def _fmt(v: Any) -> str:
    """Render a cell value; drop the trailing .0 on integral floats, pass strings through."""
    if isinstance(v, bool):
        return str(v)
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


def _series_points(series_val: Any) -> dict[str, Any]:
    """Coerce a series value into {x_label: y} for any shape a model emits:
    {x: y} dict, [{"x":..,"y":..}] list, [scalars], or a box-stat {name: value} dict."""
    if isinstance(series_val, dict):
        return {str(k): v for k, v in series_val.items()}
    if isinstance(series_val, list):
        pts: dict[str, Any] = {}
        for i, p in enumerate(series_val):
            if isinstance(p, dict) and "y" in p:
                pts[str(p.get("x", i))] = p["y"]
            elif isinstance(p, (int, float, str)):
                pts[str(i)] = p
        return pts
    return {}


def _panel_to_table(title: str, series: dict[str, Any]) -> str:
    """Render one panel's series dict as a markdown table.

    First column = x-axis label; one column per series; cells = values. The union of
    x-keys across series (first-seen order) forms the rows, so every (series, x) value
    sits in a cell with the series name as its column header and the x-label as its row
    header — exactly what ChartDataPointRule matches labels against.
    """
    norm: dict[str, dict[str, Any]] = {}
    for sname, sval in series.items():
        pts = _series_points(sval)
        if pts:
            norm[str(sname)] = pts
    if not norm:
        return ""

    xkeys: list[str] = []
    seen: set[str] = set()
    for pts in norm.values():
        for x in pts:
            if x not in seen:
                seen.add(x)
                xkeys.append(x)

    series_names = list(norm.keys())
    header = "| " + " | ".join(["x"] + series_names) + " |"
    sep = "| " + " | ".join(["---"] * (len(series_names) + 1)) + " |"
    rows = [header, sep]
    for x in xkeys:
        cells = [x] + [_fmt(norm[s].get(x, "")) for s in series_names]
        rows.append("| " + " | ".join(cells) + " |")

    out: list[str] = []
    if title and title.lower() != "none":
        out.append(f"## {title}")
    out.append("\n".join(rows))
    return "\n\n".join(out)


def chart_json_to_markdown(chart: dict) -> str:
    """Convert a chart2json object into markdown tables (one heading + table per panel).

    Handles the rich schema (``panels: {name: {series, chart_type, ...}}``) and the flat
    schema (``values: {panel: {series: {x:y}}}`` or ``{series: {x:y}}``).
    """
    if not isinstance(chart, dict):
        return ""
    figure_title = str(chart.get("title") or "").strip()
    parts: list[str] = []
    if figure_title and figure_title.lower() != "none":
        parts.append(f"# {figure_title}")

    panels = chart.get("panels")
    if isinstance(panels, dict) and panels:
        for pname, pval in panels.items():
            series = pval.get("series") if isinstance(pval, dict) else None
            if isinstance(series, dict) and series:
                tbl = _panel_to_table(str(pname), series)
                if tbl:
                    parts.append(tbl)
        return "\n\n".join(parts)

    values = chart.get("values")
    if isinstance(values, dict) and values:
        def _is_panel(v: Any) -> bool:
            return isinstance(v, dict) and bool(v) and all(isinstance(x, (dict, list)) for x in v.values())

        if all(_is_panel(v) for v in values.values()):
            for pname, series in values.items():
                tbl = _panel_to_table(str(pname), series)
                if tbl:
                    parts.append(tbl)
        else:
            tbl = _panel_to_table(figure_title, values)
            if tbl:
                parts = [tbl]
        return "\n\n".join(parts)

    return "\n\n".join(parts)


def normalize_markdown_with_chart_json(markdown: str) -> str:
    """If ``markdown`` contains a chart2json object, append the equivalent markdown
    tables so the chart rules can score it; otherwise return it unchanged. Non-invasive:
    the original text is preserved and the derived tables are appended after it.
    """
    obj = extract_json(markdown)
    if not (isinstance(obj, dict) and ("values" in obj or "panels" in obj)):
        return markdown
    tables = chart_json_to_markdown(obj)
    if not tables:
        return markdown
    return f"{markdown}\n\n{tables}" if markdown.strip() else tables
