import pytest

from parse_bench.evaluation.metrics.parse.rules_chart import ChartDataPointRule
from parse_bench.inference.providers.parse.databricks_ai_parse import _render_markdown


@pytest.mark.parametrize("content", ["Figure text", ""])
def test_figure_description_reaches_scorer_in_reading_order(content):
    figure = {
        "id": 1,
        "type": "figure",
        "content": content,
        "description": 'JSON:\n```json\n{"values":{"Sales":{"2024":7}}}\n```',
    }
    markdown = _render_markdown(
        [
            {"id": 2, "type": "text", "content": "After"},
            figure,
            {"id": 0, "type": "text", "content": "Before"},
        ]
    )
    rule = ChartDataPointRule({"type": "chart_data_point", "value": "7", "labels": ["Sales", "2024"]})
    assert rule.run(markdown)[0]
    assert markdown.startswith("Before\n\n" + content)
    assert markdown.endswith("\n\nAfter")


@pytest.mark.parametrize(
    "description", [None, "A diagram.", "```json\nN/A\n```", '```json\n{"values":{"S":{"x":5}},\n```']
)
def test_non_chart_description_preserves_content(description):
    assert _render_markdown([{"type": "figure", "content": "Figure text", "description": description}]) == "Figure text"
