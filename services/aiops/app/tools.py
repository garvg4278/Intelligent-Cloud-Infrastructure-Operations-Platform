"""Tool schemas (Anthropic's tool-use format) and the executor that
dispatches a tool call the model makes to a real HTTP call against one of
this platform's own services. Every tool here is READ-ONLY -- there is no
tool that deploys, rolls back, or changes anything. That's not an
oversight: the original design explicitly says "the AI service must not
blindly act," and read-only tools are how that's actually enforced here,
not just documented.
"""

from dataclasses import dataclass

from .service_clients import AlertClient, DeploymentClient, IncidentClient, MetricsClient, ServiceClientError

TOOL_DEFINITIONS = [
    {
        "name": "get_recent_deployments",
        "description": (
            "Get the most recent deployment records for a service: status "
            "(pending/deploying/health_checking/succeeded/rolling_back/rolled_back/failed), "
            "image tag, revision, and timestamps. Use this to check whether a recent "
            "deployment might be related to the issue being investigated."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "service_name": {"type": "string", "description": "e.g. 'auth', 'gateway'"},
            },
            "required": ["service_name"],
        },
    },
    {
        "name": "get_recent_alerts",
        "description": (
            "Get recent alerts for a service: severity, status (firing/resolved), the "
            "observed metric value, and whether it's linked to an incident."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"service_name": {"type": "string"}},
            "required": ["service_name"],
        },
    },
    {
        "name": "get_recent_incidents",
        "description": (
            "Get recent incidents for a service: status, severity, and their timeline of "
            "status changes and comments."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"service_name": {"type": "string"}},
            "required": ["service_name"],
        },
    },
    {
        "name": "query_current_metric",
        "description": (
            "Query Prometheus for the CURRENT value of a metric using PromQL. Metrics "
            "available on every service: http_requests_total (Counter; labels: method, "
            "path, status, job) and http_request_duration_seconds (Histogram; labels: "
            "method, path, job). Example: "
            "'sum(rate(http_requests_total{job=\"auth\",status=~\"5..\"}[5m]))'"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "promql": {"type": "string", "description": "A valid PromQL instant-query expression"},
            },
            "required": ["promql"],
        },
    },
]


@dataclass
class ToolExecutor:
    deployment_client: DeploymentClient
    alert_client: AlertClient
    incident_client: IncidentClient
    metrics_client: MetricsClient

    def execute(self, tool_name: str, tool_input: dict) -> dict:
        try:
            if tool_name == "get_recent_deployments":
                return {"deployments": self.deployment_client.recent_deployments(tool_input["service_name"])}
            if tool_name == "get_recent_alerts":
                return {"alerts": self.alert_client.recent_alerts(tool_input["service_name"])}
            if tool_name == "get_recent_incidents":
                return {"incidents": self.incident_client.recent_incidents(tool_input["service_name"])}
            if tool_name == "query_current_metric":
                return {"value": self.metrics_client.query(tool_input["promql"])}
            return {"error": f"unknown tool: {tool_name}"}
        except ServiceClientError as exc:
            # A tool failing (a downstream service being down, a bad
            # PromQL query) is handed back to the MODEL as a tool result,
            # not raised -- the agent loop can see the query failed and
            # say so, rather than the whole request 500ing because one of
            # four evidence sources had a bad moment.
            return {"error": str(exc)}
