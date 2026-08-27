import pytest

from app.agent import NoLLMConfiguredError, run_agent
from app.tools import ToolExecutor

from .fakes import (
    FakeAlertClient,
    FakeDeploymentClient,
    FakeIncidentClient,
    FakeLLMClient,
    FakeMetricsClient,
    text_response,
    tool_use_response,
)


def _executor(**overrides) -> ToolExecutor:
    return ToolExecutor(
        deployment_client=overrides.get("deployment_client", FakeDeploymentClient()),
        alert_client=overrides.get("alert_client", FakeAlertClient()),
        incident_client=overrides.get("incident_client", FakeIncidentClient()),
        metrics_client=overrides.get("metrics_client", FakeMetricsClient()),
    )


def test_no_llm_configured_raises_before_calling_anything():
    with pytest.raises(NoLLMConfiguredError):
        run_agent("why?", "auth", llm_client=None, tool_executor=_executor(), max_iterations=6)


def test_single_turn_no_tools_returns_answer_directly():
    llm = FakeLLMClient([text_response("Nothing unusual found.")])
    result = run_agent("why?", "auth", llm, _executor(), max_iterations=6)

    assert result.answer == "Nothing unusual found."
    assert result.evidence == []
    assert result.iterations == 1


def test_agent_executes_a_real_tool_call_and_feeds_result_back():
    deployments = [{"id": "d1", "status": "failed", "image_tag": "v2.0"}]
    llm = FakeLLMClient(
        [
            tool_use_response("get_recent_deployments", {"service_name": "auth"}),
            text_response("The last deployment (v2.0) failed, which likely explains the errors."),
        ]
    )
    dep_client = FakeDeploymentClient(deployments=deployments)

    result = run_agent("why is auth erroring?", "auth", llm, _executor(deployment_client=dep_client), 6)

    assert "v2.0" in result.answer
    assert result.iterations == 2
    assert dep_client.queried_for == ["auth"]
    assert result.evidence == [
        {
            "tool": "get_recent_deployments",
            "input": {"service_name": "auth"},
            "result": {"deployments": deployments},
        }
    ]
    # The second call to the LLM must include the tool result from the first
    second_call_messages = llm.calls[1]
    assert second_call_messages[-1]["role"] == "user"
    assert second_call_messages[-1]["content"][0]["type"] == "tool_result"


def test_agent_can_chain_multiple_tool_calls_across_turns():
    llm = FakeLLMClient(
        [
            tool_use_response("get_recent_deployments", {"service_name": "auth"}, call_id="c1"),
            tool_use_response("get_recent_alerts", {"service_name": "auth"}, call_id="c2"),
            text_response("Combined evidence points to the deployment."),
        ]
    )
    result = run_agent("why?", "auth", llm, _executor(), max_iterations=6)

    assert result.iterations == 3
    assert [e["tool"] for e in result.evidence] == ["get_recent_deployments", "get_recent_alerts"]


def test_tool_failure_is_handed_to_the_model_not_raised():
    llm = FakeLLMClient(
        [
            tool_use_response("query_current_metric", {"promql": "up"}),
            text_response("Couldn't confirm via metrics, but here's what I know otherwise."),
        ]
    )
    broken_metrics = FakeMetricsClient(raise_error=True)

    result = run_agent("why?", "auth", llm, _executor(metrics_client=broken_metrics), 6)

    assert result.iterations == 2  # didn't crash, the loop continued
    assert "error" in result.evidence[0]["result"]


def test_max_iterations_caps_a_model_that_never_stops_calling_tools():
    llm = FakeLLMClient(
        [
            tool_use_response("get_recent_deployments", {"service_name": "auth"}, call_id=f"c{i}")
            for i in range(10)
        ]
    )
    result = run_agent("why?", "auth", llm, _executor(), max_iterations=3)

    assert result.iterations == 3
    assert len(result.evidence) == 3
    assert "Stopped after 3" in result.answer


def test_unknown_tool_name_returns_error_without_crashing():
    llm = FakeLLMClient(
        [
            tool_use_response("delete_everything", {}),  # not a real tool -- must not exist to be called
            text_response("That tool isn't available."),
        ]
    )
    result = run_agent("why?", "auth", llm, _executor(), max_iterations=6)

    assert result.evidence[0]["result"] == {"error": "unknown tool: delete_everything"}
