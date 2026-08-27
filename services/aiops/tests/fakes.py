from app.llm_client import LLMResponse, ToolCall
from app.service_clients import ServiceClientError


class FakeLLMClient:
    """Scripted sequence of responses, simulating a real multi-turn
    tool-use conversation. Each call to send() returns the next response
    in the list and pops it -- .calls records every messages list sent,
    so tests can assert on exactly what the agent loop sent back after
    executing tools.
    """

    def __init__(self, responses: list[LLMResponse]):
        self.responses = list(responses)
        self.calls: list[list[dict]] = []

    def send(self, messages: list[dict], tools: list[dict]) -> LLMResponse:
        self.calls.append(messages)
        if not self.responses:
            raise AssertionError("FakeLLMClient ran out of scripted responses")
        return self.responses.pop(0)


def text_response(text: str) -> LLMResponse:
    return LLMResponse(
        stop_reason="end_turn",
        text=text,
        tool_calls=[],
        raw_content=[{"type": "text", "text": text}],
    )


def tool_use_response(tool_name: str, tool_input: dict, call_id: str = "call_1") -> LLMResponse:
    return LLMResponse(
        stop_reason="tool_use",
        text=None,
        tool_calls=[ToolCall(id=call_id, name=tool_name, input=tool_input)],
        raw_content=[{"type": "tool_use", "id": call_id, "name": tool_name, "input": tool_input}],
    )


class FakeDeploymentClient:
    def __init__(self, deployments: list[dict] | None = None, raise_error: bool = False):
        self.deployments = deployments or []
        self.raise_error = raise_error
        self.queried_for: list[str] = []

    def recent_deployments(self, service_name: str) -> list[dict]:
        self.queried_for.append(service_name)
        if self.raise_error:
            raise ServiceClientError("simulated deployment service failure")
        return self.deployments


class FakeAlertClient:
    def __init__(self, alerts: list[dict] | None = None, raise_error: bool = False):
        self.alerts = alerts or []
        self.raise_error = raise_error

    def recent_alerts(self, service_name: str) -> list[dict]:
        if self.raise_error:
            raise ServiceClientError("simulated alert service failure")
        return self.alerts


class FakeIncidentClient:
    def __init__(self, incidents: list[dict] | None = None, raise_error: bool = False):
        self.incidents = incidents or []
        self.raise_error = raise_error

    def recent_incidents(self, service_name: str) -> list[dict]:
        if self.raise_error:
            raise ServiceClientError("simulated incident service failure")
        return self.incidents


class FakeMetricsClient:
    def __init__(self, value: float = 0.0, raise_error: bool = False):
        self.value = value
        self.raise_error = raise_error
        self.queries: list[str] = []

    def query(self, promql: str) -> float:
        self.queries.append(promql)
        if self.raise_error:
            raise ServiceClientError("simulated prometheus failure")
        return self.value
