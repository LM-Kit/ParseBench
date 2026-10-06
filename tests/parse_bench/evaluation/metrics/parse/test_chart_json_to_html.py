import json

import pytest

from parse_bench.evaluation.metrics.parse.chart_json_to_html import (
    chart_description_to_html,
    chart_json_to_html,
)
from parse_bench.evaluation.metrics.parse.rules_chart import ChartDataPointRule, parse_chart_tables


def _passes(html: str, value: str, labels: list[str]) -> bool:
    return ChartDataPointRule(
        {"type": "chart_data_point", "value": value, "labels": labels, "relative_tolerance": 0}
    ).run(html)[0]


@pytest.mark.parametrize(
    ("chart", "labels"),
    [
        ({"values": {"Sales": {"2024": 7}}}, ["Sales", "2024"]),
        ({"values": {"Sales": [{"x": "2024", "y": 7}]}}, ["Sales", "2024"]),
        ({"values": {"2024": 7}}, ["2024"]),
        ({"panels": {"Europe": {"values": {"2024": 7}}}}, ["Europe", "2024"]),
        ({"panels": {"Europe": {"series": {"Sales": {"2024": 7}}}}}, ["Europe", "Sales", "2024"]),
    ],
)
def test_supported_shapes(chart, labels):
    html = chart_json_to_html(chart)
    assert html.startswith("<table>")
    assert _passes(html, "7", labels)
    for invented_label in ["category", "value"]:
        assert not _passes(html, "7", [*labels, invented_label])


def test_figure_title_and_panel_labels_stay_associated():
    chart = {
        "title": "Annual results",
        "panels": {
            "A. Literacy": {"values": {"Sales": {str(year): year for year in range(2010, 2025)}}},
            "B. Numeracy": {"values": {"Sales": {"2024": 7}}},
        },
    }
    html = chart_json_to_html(chart)
    assert _passes(html, "7", ["Annual results", "B. Numeracy", "Sales", "2024"])
    assert not _passes(html, "7", ["A. Literacy", "Sales", "2024"])


@pytest.mark.parametrize("label", ["A | B", '<tax & "fees">', "North\nAmerica"])
def test_special_characters_preserve_columns(label):
    html = chart_json_to_html({"values": {label: {"2024": 1}, "Others": {"2024": 2}, "Last": {"2024": 3}}})
    assert len(parse_chart_tables(html)) == 1
    assert _passes(html, "1", [label, "2024"])
    assert _passes(html, "2", ["Others", "2024"])
    assert not _passes(html, "3", ["Others", "2024"])


@pytest.mark.parametrize("template", ["JSON: {}", "DESCRIPTION: A chart.\n```json\n{}\n```"])
def test_description_json_with_quoted_braces(template):
    chart = {"title": 'Cost {excluding "tax"}', "values": {"A": {"2024": 7}}}
    html = chart_description_to_html(template.format(json.dumps(chart)))
    assert _passes(html, "7", [chart["title"], "A", "2024"])


def test_multiple_json_blocks_skip_non_chart_objects():
    objects = [{"metadata": "not a chart"}, {"values": {"A": {"2024": 7}}}, {"values": {"B": {"2025": 9}}}]
    html = chart_description_to_html("\n".join("```json\n" + json.dumps(obj) + "\n```" for obj in objects))
    assert _passes(html, "7", ["A", "2024"])
    assert _passes(html, "9", ["B", "2025"])
    assert not _passes(html, "7", ["B", "2024"])


def test_missing_values_are_not_zero():
    html = chart_json_to_html({"values": {"Sales": {"2024": None, "2025": 7}}})
    assert not _passes(html, "0", ["Sales", "2024"])
    assert _passes(html, "7", ["Sales", "2025"])


def test_unlabeled_values_do_not_invent_coordinates():
    assert chart_json_to_html({"values": {"Sales": [7, 9]}}) == ""


def test_point_lists_preserve_repeated_x_values_and_series():
    chart = {"values": {"Sales": [{"x": "2024", "y": 10}, {"x": "2024", "y": 12}], "Profit": {"2024": 3}}}
    html = chart_json_to_html(chart)
    assert parse_chart_tables(html)[0].data.tolist() == [["x", "y"], ["2024", "10"], ["2024", "12"]]
    for value in ["10", "12"]:
        assert _passes(html, value, ["Sales", "2024", "y"])
        assert not _passes(html, value, ["Profit", "2024"])
    assert _passes(html, "3", ["Profit", "2024"])
