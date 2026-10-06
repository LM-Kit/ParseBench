import json

import pytest

from parse_bench.evaluation.metrics.parse.chart_json_to_markdown import (
    chart_description_to_markdown,
    chart_json_to_markdown,
)
from parse_bench.evaluation.metrics.parse.rules_chart import ChartDataPointRule, parse_chart_tables


def _passes(markdown: str, value: str, labels: list[str]) -> bool:
    return ChartDataPointRule(
        {"type": "chart_data_point", "value": value, "labels": labels, "relative_tolerance": 0}
    ).run(markdown)[0]


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
    markdown = chart_json_to_markdown(chart)
    assert _passes(markdown, "7", labels)
    for invented_label in ["category", "value"]:
        assert not _passes(markdown, "7", [*labels, invented_label])


def test_figure_title_and_panel_labels_stay_associated():
    chart = {
        "title": "Annual results",
        "panels": {
            "Europe": {"values": {"Sales": {str(year): year for year in range(2010, 2025)}}},
            "Asia": {"values": {"Sales": {"2024": 7}}},
        },
    }
    markdown = chart_json_to_markdown(chart)
    assert _passes(markdown, "7", ["Annual results", "Asia", "Sales", "2024"])
    assert not _passes(markdown, "7", ["Europe", "Sales", "2024"])


@pytest.mark.parametrize("label", ["A | B", '<tax & "fees">', "North\nAmerica"])
def test_special_characters_preserve_columns(label):
    markdown = chart_json_to_markdown({"values": {label: {"2024": 1}, "Others": {"2024": 2}, "Last": {"2024": 3}}})
    assert len(parse_chart_tables(markdown)) == 1
    assert _passes(markdown, "1", [label, "2024"])
    assert _passes(markdown, "2", ["Others", "2024"])
    assert not _passes(markdown, "3", ["Others", "2024"])


@pytest.mark.parametrize("template", ["JSON: {}", "DESCRIPTION: A chart.\n```json\n{}\n```"])
def test_description_json_with_quoted_braces(template):
    chart = {"title": 'Cost {excluding "tax"}', "values": {"A": {"2024": 7}}}
    markdown = chart_description_to_markdown(template.format(json.dumps(chart)))
    assert _passes(markdown, "7", [chart["title"], "A", "2024"])


def test_multiple_json_blocks_skip_non_chart_objects():
    objects = [{"metadata": "not a chart"}, {"values": {"A": {"2024": 7}}}, {"values": {"B": {"2025": 9}}}]
    markdown = chart_description_to_markdown("\n".join("```json\n" + json.dumps(obj) + "\n```" for obj in objects))
    assert _passes(markdown, "7", ["A", "2024"])
    assert _passes(markdown, "9", ["B", "2025"])
    assert not _passes(markdown, "7", ["B", "2024"])


def test_missing_values_are_not_zero():
    markdown = chart_json_to_markdown({"values": {"Sales": {"2024": None, "2025": 7}}})
    assert not _passes(markdown, "0", ["Sales", "2024"])
    assert _passes(markdown, "7", ["Sales", "2025"])


def test_unlabeled_values_do_not_invent_coordinates():
    assert chart_json_to_markdown({"values": {"Sales": [7, 9]}}) == ""
