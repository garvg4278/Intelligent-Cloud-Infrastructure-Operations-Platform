"""The actual agent loop: send messages + tool definitions to the model,
execute whatever tools it asks for against real services, feed the
results back, repeat until it gives a final text answer or a safety cap
is hit. Pure logic, no FastAPI/Celery/DB import here -- same separation
as executor.py in the deployment and alert services, testable by calling
run_agent() directly with any LLMClient/ToolExecutor.
"""

import json
from dataclasses import dataclass, field

from .llm_client import LLMClient
from .tools import TOOL_DEFINITIONS, ToolExecutor


class NoLLMConfiguredError(Exception):
    pass


@dataclass
class AgentResult:
    answer: str
    evidence: list[dict] = field(default_factory=list)
    iterations: int = 0


SYSTEM_CONTEXT = (
    "You are an operations assistant for a cloud infrastructure platform. "
    "You have READ-ONLY tools to check a service's recent deployments, "
    "alerts, incidents, and current metric values. Use them to gather "
    "actual evidence before answering -- do not guess or make up numbers, "
    "statuses, or timestamps. If the tools don't show anything relevant, "
    "say so plainly instead of inventing an explanation. You cannot deploy, "
    "roll back, or change anything -- if a fix is needed, recommend it, "
    "don't imply you performed it."
)


def run_agent(
    question: str,
    service_name: str,
    llm_client: LLMClient | None,
    tool_executor: ToolExecutor,
    max_iterations: int,
) -> AgentResult:
    if llm_client is None:
        raise NoLLMConfiguredError(
            "no ANTHROPIC_API_KEY configured -- set it to enable /ai/explain (see README)"
        )

    messages = [
        {
            "role": "user",
            "content": f"{SYSTEM_CONTEXT}\n\nService: {service_name}\nQuestion: {question}",
        }
    ]
    evidence: list[dict] = []

    for iteration in range(1, max_iterations + 1):
        response = llm_client.send(messages, TOOL_DEFINITIONS)

        if response.stop_reason != "tool_use":
            return AgentResult(
                answer=response.text or "(model returned no text)",
                evidence=evidence,
                iterations=iteration,
            )

        messages.append({"role": "assistant", "content": response.raw_content})

        tool_result_blocks = []
        for call in response.tool_calls:
            result = tool_executor.execute(call.name, call.input)
            evidence.append({"tool": call.name, "input": call.input, "result": result})
            tool_result_blocks.append(
                {"type": "tool_result", "tool_use_id": call.id, "content": _stringify(result)}
            )
        messages.append({"role": "user", "content": tool_result_blocks})

    return AgentResult(
        answer=(
            f"Stopped after {max_iterations} tool-use rounds without a final answer. "
            "Evidence gathered so far is below; this usually means the question needs "
            "narrowing or a tool kept returning something the model wanted to re-check."
        ),
        evidence=evidence,
        iterations=max_iterations,
    )


def _stringify(result: dict) -> str:
    return json.dumps(result)
