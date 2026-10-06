"""Verify that figure data reaches the existing chart matcher."""

import copy
import json

import pytest

from parse_bench.evaluation.metrics.parse.rules_chart import ChartDataPointRule
from parse_bench.inference.pipelines import get_pipeline
from parse_bench.inference.providers.parse.databricks_ai_parse import DatabricksAiParseProvider, _render_markdown


@pytest.fixture
def figure():
    chart = {
        "panels": {
            "193 UN Member States": {"values": {"193 UN Member States": {"IF": 0.8079}}},
            "LDC/LLDCs": {"values": {"LDC/LLDCs": {"CP": 0.4444}}},
            "LDCs": {"values": {"LDCs": {"TEC": 0.3667}}},
            "LDC/SIDS": {"values": {"LDC/SIDS": {"EPI": 0.1969}}},
        }
    }
    return {
        "id": 0,
        "type": "figure",
        "bbox": [{"page_id": 0}],
        "content": "Online Service Index",
        "description": f"DESCRIPTION: Bar charts.\nJSON:\n```json\n{json.dumps(chart)}\n```",
    }


def test_chart_description_scores_with_existing_rules(figure):
    markdown = _render_markdown([figure])
    for value, labels in [
        ("0.8079", ["IF", "193 UN Member States"]),
        ("0.4444", ["CP", "LDC/LLDCs"]),
        ("0.3667", ["TEC", "LDCs"]),
        ("0.1969", ["EPI", "LDC/SIDS"]),
    ]:
        rule = ChartDataPointRule({"type": "chart_data_point", "value": value, "labels": labels})
        assert not rule.run(figure["content"])[0]
        assert rule.run(markdown)[0]


def test_description_is_used_when_content_is_empty(figure):
    figure["content"] = ""
    assert "0.8079" in _render_markdown([figure])


def test_multiple_figures_are_rendered_in_page_and_element_order(figure):
    later = copy.deepcopy(figure)
    later["bbox"][0]["page_id"] = 1
    later["description"] = 'JSON:\n```json\n{"values":{"Later":{"2025":12345}}}\n```'
    markdown = _render_markdown([later, figure])
    assert markdown.index("0.8079") < markdown.index("12345")


@pytest.mark.parametrize("description", [None, "A diagram of a building.", "JSON:\n```json\nN/A\n```", "{broken"])
def test_non_chart_description_preserves_content(description):
    assert (
        _render_markdown([{"id": 0, "type": "figure", "content": "Figure text", "description": description}])
        == "Figure text"
    )


def test_text_tables_and_headings_keep_existing_rendering():
    elements = [
        {"id": 0, "type": "title", "content": "Title"},
        {"id": 1, "type": "section_header", "content": "Section"},
        {"id": 2, "type": "text", "content": "Body"},
        {"id": 3, "type": "table", "content": "<table><tr><td>7</td></tr></table>"},
    ]
    assert _render_markdown(elements) == "# Title\n\n## Section\n\nBody\n\n<table><tr><td>7</td></tr></table>"


@pytest.mark.parametrize("name", ["databricks_ai_parse", "databricks_ai_parse_batch"])
def test_pipeline_requests_figure_descriptions(name):
    pipeline = get_pipeline(name)
    assert pipeline.config["description_element_types"] == "figure"
    provider = DatabricksAiParseProvider(
        "databricks_ai_parse",
        {
            **pipeline.config,
            "host": "https://example.invalid",
            "token": "test-token",
            "warehouse_id": "test",
            "volume_path": "/Volumes/test/test/test",
        },
    )
    assert "'descriptionElementTypes', 'figure'" in provider._build_statement(
        "/Volumes/test/test/test/file.pdf", include_path=False
    )
