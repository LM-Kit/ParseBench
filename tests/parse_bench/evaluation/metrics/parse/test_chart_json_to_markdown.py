"""Tests for chart JSON normalization used by the chart dimension."""

import json

import pytest

from parse_bench.evaluation.metrics.parse.chart_json_to_markdown import (
    chart_description_to_markdown,
    chart_json_to_markdown,
    contains_chart_json,
    extract_json,
    normalize_markdown_with_chart_json,
)
from parse_bench.evaluation.metrics.parse.rules_chart import ChartDataPointRule, parse_chart_tables


def _has_row(md: str, *cells: str) -> bool:
    """Check the scorer's parsed cells, including HTML-escaped labels."""
    return any(all(cell in row for cell in cells) for table in parse_chart_tables(md) for row in table.data)


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
    assert "## Online Service Index" in md  # panel title as heading (caption)
    assert "193 UN Member States" in md  # series -> column header
    assert _has_row(md, "IF", "0.8079")  # (series, x) value in a cell


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
    assert "JSON:" in out  # original preserved
    assert _has_row(out, "2020", "5")  # table appended


def test_normalize_noop_when_no_chart_json():
    text = "# Some heading\n\nJust prose, no chart data."
    assert normalize_markdown_with_chart_json(text) == text


def test_non_chart_or_empty_is_safe():
    assert chart_json_to_markdown({}) == ""
    assert extract_json("N/A") is None
    assert not contains_chart_json("no json here")


def test_flat_single_series_shape():
    # Prompt allows a flat {category: value} for a single-series bar/pie.
    chart = {"title": "Market share", "values": {"North": 40, "South": 60}}
    md = chart_json_to_markdown(chart)
    assert _has_row(md, "North", "40")
    assert _has_row(md, "South", "60")


def test_panels_use_values_key():
    # Current prompt: multi-panel figures put chart data under "values" (not "series").
    chart = {
        "title": "None",
        "panels": {
            "Standardized Approach": {
                "chart_type": "stacked_bar",
                "values": {"Minimum requirement": {"CET1 ratio": 4.5, "Total capital ratio": 8.0}},
                "series_meta": {},
                "x_range": ["CET1 ratio", "Total capital ratio"],
                "additional_info": "Source: Fed",
            }
        },
    }
    md = chart_json_to_markdown(chart)
    assert "## Standardized Approach" in md
    assert "Minimum requirement" in md
    assert _has_row(md, "CET1 ratio", "4.5")


def test_panels_series_key_still_supported():
    # Backward-compat: older outputs put panel data under "series".
    chart = {"panels": {"P": {"series": {"S": {"2020": 1}}}}}
    md = chart_json_to_markdown(chart)
    assert _has_row(md, "2020", "1")


def _passes(markdown: str, value: str, labels: list[str]) -> bool:
    return ChartDataPointRule(
        {"type": "chart_data_point", "value": value, "labels": labels, "relative_tolerance": 0}
    ).run(markdown)[0]


def test_flat_values_inside_panels_are_scored():
    chart = {"panels": {"Organizational framework": {"values": {"Government structure": 95, "CIO": 81}}}}
    md = chart_json_to_markdown(chart)
    assert _passes(md, "81", ["Organizational framework", "CIO"])
    assert not _passes(md, "95", ["CIO"])


def test_quoted_braces_and_escaped_quotes_are_decoded():
    chart = {"title": 'Cost {excluding "tax"}', "values": {"A": {"2024": 7}}}
    description = "DESCRIPTION: A chart.\n\nJSON:\n```json\n" + json.dumps(chart) + "\n```"
    assert extract_json(description) == chart
    assert _passes(chart_description_to_markdown(description), "7", [chart["title"], "A", "2024"])


def test_all_fenced_charts_are_converted_even_after_non_chart_json():
    objects = [{"metadata": "not a chart"}, {"values": {"A": {"2024": 7}}}, {"values": {"B": {"2025": 9}}}]
    description = "\n\n".join("```json\n" + json.dumps(obj) + "\n```" for obj in objects)
    md = chart_description_to_markdown(description)
    assert _passes(md, "7", ["A", "2024"])
    assert _passes(md, "9", ["B", "2025"])
    assert not _passes(md, "7", ["B", "2024"])


@pytest.mark.parametrize(
    "description", ["", "N/A", "JSON:\n```json\nN/A\n```", '```json\n{"values": {"S": {"x": 5}},\n```']
)
def test_missing_or_invalid_json_produces_no_tables(description):
    assert chart_description_to_markdown(description) == ""


def test_figure_title_applies_to_later_panels_without_cross_panel_labels():
    chart = {
        "title": "Annual results",
        "panels": {
            "Europe": {"values": {"Sales": {str(year): year for year in range(2010, 2025)}}},
            "Asia": {"values": {"Sales": {"2024": 7}}},
        },
    }
    md = chart_json_to_markdown(chart)
    assert _passes(md, "7", ["Annual results", "Asia", "Sales", "2024"])
    assert not _passes(md, "7", ["Europe", "Sales", "2024"])


@pytest.mark.parametrize("label", ["North | South", "Revenue < tax & fees", "North\nAmerica"])
def test_labels_survive_table_serialization(label):
    md = chart_json_to_markdown({"values": {label: {"2024": 7}}})
    assert len(parse_chart_tables(md)) == 1
    assert _passes(md, "7", [label, "2024"])


def test_html_is_escaped_in_labels():
    label = '<script>alert("label")</script>'
    md = chart_json_to_markdown({"values": {label: {"2024": 7}}})
    assert "<script>" not in md
    assert parse_chart_tables(md)[0].data[0, 1] == label


def test_pipe_in_series_name_does_not_shift_later_column_labels():
    chart = {"values": {"A | B": {"2024": 1}, "Others": {"2024": 2}, "Last": {"2024": 3}}}
    md = chart_json_to_markdown(chart)
    assert _passes(md, "2", ["Others", "2024"])
    assert not _passes(md, "3", ["Others", "2024"])


def test_missing_values_are_not_filled_with_zero():
    md = chart_json_to_markdown({"values": {"Sales": {"2024": None, "2025": 7}}})
    assert not _passes(md, "0", ["Sales", "2024"])
    assert _passes(md, "7", ["Sales", "2025"])


def test_unlabeled_array_does_not_invent_x_coordinates():
    assert chart_json_to_markdown({"values": {"Sales": [7, 9]}}) == ""


def test_wrong_series_association_still_fails():
    md = chart_json_to_markdown({"values": {"Revenue": {"2024": 7}, "Profit": {"2024": 9}}})
    assert _passes(md, "7", ["Revenue", "2024"])
    assert not _passes(md, "9", ["Revenue", "2024"])


def test_plain_markdown_is_unchanged():
    md = "# Sales\n\n| Year | Revenue |\n| --- | --- |\n| 2024 | 7 |"
    assert normalize_markdown_with_chart_json(md) == md


def test_conversion_does_not_invent_axis_or_series_labels():
    md = chart_json_to_markdown({"values": {"2024": 7}})
    assert _passes(md, "7", ["2024"])
    for label in ["x", "category", "value"]:
        assert not _passes(md, "7", ["2024", label])
