import json

import pytest
import requests

from parse_bench.inference.pipelines import get_pipeline
from parse_bench.inference.providers.base import ProviderConfigError, ProviderPermanentError, ProviderTransientError
from parse_bench.inference.providers.parse.databricks_ai_parse import DatabricksAiParseProvider
from parse_bench.schemas.pipeline_io import InferenceRequest
from parse_bench.schemas.product import ProductType

_CONFIG = {"host": "https://example.invalid", "token": "test", "volume_path": "/Volumes/test/test/test"}


@pytest.mark.parametrize("status", [200, 400, 429])
def test_rest_request_and_cleanup(tmp_path, monkeypatch, status):
    monkeypatch.delenv("DATABRICKS_SQL_WAREHOUSE_ID", raising=False)
    pipeline = get_pipeline("databricks_ai_parse_rest")
    provider = DatabricksAiParseProvider(
        "databricks_ai_parse",
        {**_CONFIG, **pipeline.config, "description_element_types": "figure"},
    )
    source = tmp_path / "document.pdf"
    source.write_bytes(b"document bytes")
    parsed = {
        "document": {"pages": [], "elements": [{"type": "text", "content": "Parsed text"}]},
        "metadata": {"id": "request-id"},
    }
    response = requests.Response()
    response.status_code = status
    response._content = json.dumps(parsed).encode()
    uploaded, deleted = [], []

    def post(url, **kwargs):
        assert url == "https://example.invalid/api/2.0/ai-functions/ai_parse_document"
        assert kwargs["json"] == {
            "content": uploaded[0],
            "options": {"version": "2.0", "descriptionElementTypes": "figure"},
        }
        return response

    monkeypatch.setattr(provider, "_upload_file", lambda source, path: uploaded.append(path))
    monkeypatch.setattr(requests, "post", post)
    monkeypatch.setattr(provider, "_delete_file", deleted.append)
    request = InferenceRequest(example_id="chart", source_file_path=str(source), product_type=ProductType.PARSE)
    if status == 200:
        result = provider.run_inference(pipeline, request)
        assert result.raw_output["ai_parse_document"] == parsed
        assert result.raw_output["_config"]["transport"] == "rest"
        assert provider.normalize(result).output.markdown == "Parsed text"
    else:
        with pytest.raises(ProviderTransientError if status == 429 else ProviderPermanentError):
            provider.run_inference(pipeline, request)
    assert deleted == uploaded


@pytest.mark.parametrize(
    ("config", "error"), [({}, "warehouse_id"), ({"transport": "rest", "batch_size": 2}, "batch_size")]
)
def test_transport_configuration(monkeypatch, config, error):
    monkeypatch.delenv("DATABRICKS_SQL_WAREHOUSE_ID", raising=False)
    with pytest.raises(ProviderConfigError, match=error):
        DatabricksAiParseProvider("databricks_ai_parse", {**_CONFIG, **config})
