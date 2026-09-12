import pytest

from src.app.mcp_client import _parse_sse_response


def test_parse_sse_response_valid():
    sse_text = 'event: message\ndata: {"jsonrpc":"2.0","id":1,"result":{"tools":[]}}\n\n'
    result = _parse_sse_response(sse_text)
    assert result["result"]["tools"] == []


def test_parse_sse_response_no_result():
    sse_text = "event: ping\ndata: {}\n\n"
    with pytest.raises(ValueError, match="No valid JSON-RPC response"):
        _parse_sse_response(sse_text)


def test_parse_sse_response_with_error():
    sse_text = 'data: {"jsonrpc":"2.0","id":1,"error":{"code":-32600,"message":"Invalid"}}\n\n'
    result = _parse_sse_response(sse_text)
    assert "error" in result
