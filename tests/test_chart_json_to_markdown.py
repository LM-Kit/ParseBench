"""Tests for chart2json -> markdown-table normalization used by the chart dimension."""

from parse_bench.evaluation.metrics.parse.chart_json_to_markdown import (
    chart_json_to_markdown,
    contains_chart_json,
    extract_json,
    normalize_markdown_with_chart_json,
)


def _has_row(md: str, *cells: str) -> bool:
    """True if some markdown table row contains all given cell strings."""
    for line in md.splitlines():
        if line.strip().startswith("|") and all(c in line for c in cells):
            return True
    return False


def test_single_chart_values_shape():
    chart = {"title": "Merger notifications", "values": {"OECD": {"2015": 7200, "2016": 7500}}}
    md = chart_json_to_markdown(chart)
    assert "Merger notifications" in md and md.lstrip().startswith("#")  # title as a heading
    assert "OECD" in md
    assert _has_row(md, "2015", "7200")  # x-key as row label, value in a cell


def test_multi_panel_shape():
    chart = {
        "title": "None",
        "panels": {
            "Online Service Index": {
                "series": {"193 UN Member States": {"IF": 0.8079, "CP": 0.44}},
            }
        },
    }
    md = chart_json_to_markdown(chart)
    assert "## Online Service Index" in md          # panel title as heading (caption)
    assert "193 UN Member States" in md              # series -> column header
    assert _has_row(md, "IF", "0.8079")              # (series, x) value in a cell


def test_list_of_xy_points():
    chart = {"values": {"GDP": [{"x": 0, "y": -0.2}, {"x": 1, "y": -0.3}]}}
    md = chart_json_to_markdown(chart)
    assert _has_row(md, "0", "-0.2")
    assert _has_row(md, "1", "-0.3")


def test_extract_json_from_fenced_and_prefixed_text():
    text = 'DESCRIPTION: a bar chart.\n\nJSON:\n```json\n{"title":"T","values":{"A":{"x1":1}}}\n```'
    obj = extract_json(text)
    assert obj == {"title": "T", "values": {"A": {"x1": 1}}}
    assert contains_chart_json(text)


def test_normalize_appends_tables_and_preserves_original():
    text = 'JSON:\n```json\n{"values":{"A":{"2020":5}}}\n```'
    out = normalize_markdown_with_chart_json(text)
    assert "JSON:" in out                 # original preserved
    assert _has_row(out, "2020", "5")     # table appended


def test_normalize_noop_when_no_chart_json():
    text = "# Some heading\n\nJust prose, no chart data."
    assert normalize_markdown_with_chart_json(text) == text


def test_non_chart_or_empty_is_safe():
    assert chart_json_to_markdown({}) == ""
    assert extract_json("N/A") is None
    assert not contains_chart_json("no json here")
