"""Unit tests for AnthropicLLMClient's request construction and response
parsing, with the underlying httpx call mocked -- same spirit as every
other adapter test in this repo. Real end-to-end verification against the
live API (no key available) is separate -- see the README.
"""

from unittest.mock import MagicMock, patch

import httpx
import pytest

from app.llm_client import ANTHROPIC_API_URL, ANTHROPIC_VERSION, AnthropicLLMClient, LLMClientError


@pytest.fixture()
def client():
    return AnthropicLLMClient(api_key="sk-test-key", model="claude-sonnet-5")


def test_send_builds_correct_request(client):
    fake_response = MagicMock(
        status_code=200,
        json=lambda: {"content": [{"type": "text", "text": "hi"}], "stop_reason": "end_turn"},
    )
    fake_response.raise_for_status = lambda: None

    with patch("app.llm_client.httpx.post", return_value=fake_response) as mock_post:
        client.send([{"role": "user", "content": "hello"}], tools=[{"name": "foo"}])

    called_url, called_kwargs = mock_post.call_args
    assert called_url[0] == ANTHROPIC_API_URL
    assert called_kwargs["headers"]["x-api-key"] == "sk-test-key"
    assert called_kwargs["headers"]["anthropic-version"] == ANTHROPIC_VERSION
    assert called_kwargs["json"]["model"] == "claude-sonnet-5"
    assert called_kwargs["json"]["messages"] == [{"role": "user", "content": "hello"}]
    assert called_kwargs["json"]["tools"] == [{"name": "foo"}]


def test_send_parses_text_only_response(client):
    fake_response = MagicMock(
        json=lambda: {
            "content": [{"type": "text", "text": "The answer is X."}],
            "stop_reason": "end_turn",
        }
    )
    fake_response.raise_for_status = lambda: None

    with patch("app.llm_client.httpx.post", return_value=fake_response):
        result = client.send([], [])

    assert result.stop_reason == "end_turn"
    assert result.text == "The answer is X."
    assert result.tool_calls == []


def test_send_parses_tool_use_response():
    llm_client = AnthropicLLMClient(api_key="sk-test", model="claude-sonnet-5")
    fake_response = MagicMock(
        json=lambda: {
            "content": [
                {"type": "text", "text": "Let me check."},
                {
                    "type": "tool_use",
                    "id": "toolu_1",
                    "name": "get_recent_deployments",
                    "input": {"service_name": "auth"},
                },
            ],
            "stop_reason": "tool_use",
        }
    )
    fake_response.raise_for_status = lambda: None

    with patch("app.llm_client.httpx.post", return_value=fake_response):
        result = llm_client.send([], [])

    assert result.stop_reason == "tool_use"
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].name == "get_recent_deployments"
    assert result.tool_calls[0].input == {"service_name": "auth"}
    # raw_content must be preserved verbatim -- the agent loop appends it
    # straight back into message history
    assert result.raw_content == fake_response.json()["content"]


def test_send_raises_llm_client_error_with_body_on_http_status_error(client):
    request = httpx.Request("POST", ANTHROPIC_API_URL)
    response = httpx.Response(401, json={"error": {"message": "invalid x-api-key"}}, request=request)

    with (
        patch("app.llm_client.httpx.post", return_value=response),
        pytest.raises(LLMClientError, match="401"),
    ):
        client.send([], [])


def test_send_raises_llm_client_error_on_connection_failure(client):
    with (
        patch("app.llm_client.httpx.post", side_effect=httpx.ConnectError("boom")),
        pytest.raises(LLMClientError, match="Anthropic API call failed"),
    ):
        client.send([], [])
