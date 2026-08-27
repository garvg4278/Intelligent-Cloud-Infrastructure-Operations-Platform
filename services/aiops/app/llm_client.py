"""Talks to a real LLM with real tool use. Only implementation right now
is Anthropic's Messages API, since that's the one this service was built
against and verified against (see the README for exactly what "verified"
means without an API key in the build sandbox).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import httpx

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"


class LLMClientError(Exception):
    pass


@dataclass
class ToolCall:
    id: str
    name: str
    input: dict


@dataclass
class LLMResponse:
    stop_reason: str
    text: str | None
    tool_calls: list[ToolCall]
    # The raw content blocks Anthropic returned, needed verbatim to append
    # back into the message history as the assistant's turn -- reformatting
    # them from text/tool_calls would lose fields the API expects to see
    # unchanged on the next call.
    raw_content: list[dict]


class LLMClient(Protocol):
    def send(self, messages: list[dict], tools: list[dict]) -> LLMResponse: ...


class AnthropicLLMClient:
    def __init__(self, api_key: str, model: str):
        self.api_key = api_key
        self.model = model

    def send(self, messages: list[dict], tools: list[dict]) -> LLMResponse:
        try:
            resp = httpx.post(
                ANTHROPIC_API_URL,
                headers={
                    "x-api-key": self.api_key,
                    "anthropic-version": ANTHROPIC_VERSION,
                    "content-type": "application/json",
                },
                json={
                    "model": self.model,
                    "max_tokens": 1024,
                    "messages": messages,
                    "tools": tools,
                },
                timeout=60,
            )
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            # Anthropic's error body is genuinely useful (e.g. which field
            # was wrong) -- surface it instead of just the status code.
            status = exc.response.status_code
            raise LLMClientError(f"Anthropic API error {status}: {exc.response.text}") from exc
        except httpx.HTTPError as exc:
            raise LLMClientError(f"Anthropic API call failed: {exc}") from exc

        return self._parse(resp.json())

    @staticmethod
    def _parse(data: dict) -> LLMResponse:
        content = data.get("content", [])
        text_parts = [block["text"] for block in content if block.get("type") == "text"]
        tool_calls = [
            ToolCall(id=block["id"], name=block["name"], input=block.get("input", {}))
            for block in content
            if block.get("type") == "tool_use"
        ]
        return LLMResponse(
            stop_reason=data.get("stop_reason", "end_turn"),
            text="\n".join(text_parts) if text_parts else None,
            tool_calls=tool_calls,
            raw_content=content,
        )


_llm_client: LLMClient | None = None


def get_llm_client() -> LLMClient | None:
    """Returns None (not a client) if no API key is configured -- callers
    are expected to handle that as "not configured" rather than treating
    it as a request-time failure of a client that does exist."""
    global _llm_client
    if _llm_client is None:
        from .config import settings

        if not settings.ANTHROPIC_API_KEY:
            return None
        _llm_client = AnthropicLLMClient(settings.ANTHROPIC_API_KEY, settings.ANTHROPIC_MODEL)
    return _llm_client


def set_llm_client(client: LLMClient | None) -> None:
    """Test hook."""
    global _llm_client
    _llm_client = client
