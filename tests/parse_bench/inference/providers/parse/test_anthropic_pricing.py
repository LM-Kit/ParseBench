"""Unit tests for Anthropic provider pricing."""

from __future__ import annotations

import pytest

from parse_bench.inference.providers.parse import anthropic
from parse_bench.inference.providers.parse.anthropic import AnthropicProvider


def _provider_for_model(model: str) -> AnthropicProvider:
    provider = object.__new__(AnthropicProvider)
    provider._model = model
    return provider


@pytest.mark.parametrize(
    ("model", "expected"),
    [
        # Longest prefix wins: the x.5 ids must not fall through to the x entry.
        ("claude-opus-5-5", (4.00, 20.00, 0.20, 5.00)),
        ("claude-opus-5", (5.00, 25.00, 0.50, 6.25)),
        ("claude-fable-5-1", (10.00, 50.00, 0.25, 12.50)),
        ("claude-fable-5", (10.00, 50.00, 1.00, 12.50)),
        ("claude-sonnet-5", (2.00, 10.00, 0.20, 2.50)),
        # Dated snapshot ids resolve to their family entry.
        ("claude-haiku-4-5-20251001", (1.00, 5.00, 0.10, 1.25)),
        ("claude-unknown-model", (0.0, 0.0, 0.0, 0.0)),
    ],
)
def test_get_pricing_resolves_longest_prefix(model: str, expected: tuple[float, float, float, float]) -> None:
    assert _provider_for_model(model)._get_pricing() == expected


# --- cache-aware cost --------------------------------------------------------


def test_cache_aware_cost_uses_listed_cache_rates() -> None:
    # Opus 5.5 listed rates: $4 in, $20 out, $0.20 cache read, $5 5m cache write.
    usage = {"input": 1_000_000, "output": 1_000_000, "cache_read": 1_000_000, "cache_write": 1_000_000}
    cost = anthropic.anthropic_cache_aware_cost_usd(usage, 4.0, 20.0, 0.20, 5.0)
    assert cost == pytest.approx(4.0 + 20.0 + 0.20 + 5.0)


def test_cache_aware_cost_matches_flat_formula_without_cache_tokens() -> None:
    usage = {"input": 2_000_000, "output": 500_000}
    assert anthropic.anthropic_cache_aware_cost_usd(usage, 1.0, 5.0, 0.10, 1.25) == pytest.approx(2.0 + 2.5)


def test_extract_usage_reads_cache_tokens() -> None:
    class Usage:
        input_tokens = 100
        output_tokens = 20
        cache_read_input_tokens = 300
        cache_creation_input_tokens = 50

    class Response:
        usage = Usage()
        content: list = []

    usage = AnthropicProvider._extract_usage(Response())
    assert usage["cache_read_tokens"] == 300
    assert usage["cache_write_tokens"] == 50
    assert usage["total_tokens"] == 470


def test_cache_tokens_reach_evaluation_stats() -> None:
    from types import SimpleNamespace

    from parse_bench.evaluation.stats import build_operational_stats

    result = SimpleNamespace(latency_in_ms=None, raw_output={"cache_read_tokens": 300, "cache_write_tokens": 50})
    stats = {stat.name: stat.value for stat in build_operational_stats(result)}  # type: ignore[arg-type]
    assert stats["cache_read_tokens"] == 300
    assert stats["cache_write_tokens"] == 50
