"""Unit tests for the pure aggregation functions, using data shaped
exactly like the real deployment/incident/alert services' actual API
output -- confirmed against DeploymentOut.model_dump_json() directly
(see the comment in aggregations.py) rather than guessed.
"""

from app.aggregations import alert_stats, deployment_stats, incident_stats


def test_deployment_stats_empty_list():
    result = deployment_stats([])
    assert result == {"total": 0, "success_rate": None, "by_status": {}, "deployments_per_day": None}


def test_deployment_stats_computes_success_rate():
    deployments = [
        {"status": "succeeded", "created_at": "2026-08-01T10:00:00Z"},
        {"status": "succeeded", "created_at": "2026-08-02T10:00:00Z"},
        {"status": "failed", "created_at": "2026-08-03T10:00:00Z"},
        {"status": "rolled_back", "created_at": "2026-08-04T10:00:00Z"},
    ]
    result = deployment_stats(deployments)
    assert result["total"] == 4
    assert result["success_rate"] == 0.5
    assert result["by_status"] == {"succeeded": 2, "failed": 1, "rolled_back": 1}


def test_deployment_stats_frequency_over_a_known_span():
    # 4 deployments spread evenly across exactly 3 days -> 4/3 per day
    deployments = [
        {"status": "succeeded", "created_at": f"2026-08-0{d}T00:00:00Z"} for d in [1, 2, 3, 4]
    ]
    result = deployment_stats(deployments)
    assert result["deployments_per_day"] == round(4 / 3, 4)


def test_deployment_stats_single_deployment_has_no_meaningful_span():
    result = deployment_stats([{"status": "succeeded", "created_at": "2026-08-01T00:00:00Z"}])
    assert result["total"] == 1
    assert result["deployments_per_day"] == 1.0


def test_incident_stats_empty_list():
    result = incident_stats([])
    assert result["total"] == 0
    assert result["avg_resolution_seconds"] is None


def test_incident_stats_computes_mean_time_to_resolution():
    incidents = [
        {
            "status": "resolved", "severity": "critical",
            "created_at": "2026-08-01T00:00:00Z", "resolved_at": "2026-08-01T01:00:00Z",
        },
        {
            "status": "resolved", "severity": "warning",
            "created_at": "2026-08-01T00:00:00Z", "resolved_at": "2026-08-01T03:00:00Z",
        },
        {
            "status": "open", "severity": "critical",
            "created_at": "2026-08-01T00:00:00Z", "resolved_at": None,
        },
    ]
    result = incident_stats(incidents)
    assert result["total"] == 3
    assert result["resolved_count"] == 2  # the still-open one is correctly excluded
    assert result["avg_resolution_seconds"] == 2.0 * 3600  # (1h + 3h) / 2
    assert result["by_status"] == {"resolved": 2, "open": 1}
    assert result["by_severity"] == {"critical": 2, "warning": 1}


def test_alert_stats_empty_list():
    result = alert_stats(rules=[], alerts=[])
    assert result == {"total": 0, "by_severity": {}, "by_status": {}, "noisiest_rules": []}


def test_alert_stats_identifies_noisiest_rule_by_name():
    rules = [{"id": "r1", "name": "high error rate"}, {"id": "r2", "name": "latency spike"}]
    alerts = [
        {"rule_id": "r1", "severity": "critical", "status": "firing"},
        {"rule_id": "r1", "severity": "critical", "status": "resolved"},
        {"rule_id": "r1", "severity": "critical", "status": "resolved"},
        {"rule_id": "r2", "severity": "warning", "status": "resolved"},
    ]
    result = alert_stats(rules, alerts)
    assert result["total"] == 4
    assert result["by_severity"] == {"critical": 3, "warning": 1}
    assert result["noisiest_rules"][0] == {"rule_id": "r1", "rule_name": "high error rate", "count": 3}


def test_alert_stats_handles_alert_for_a_rule_not_in_the_rules_list():
    # Defensive case: shouldn't crash if a rule was deleted after firing
    result = alert_stats(rules=[], alerts=[{"rule_id": "gone", "severity": "info", "status": "firing"}])
    assert result["noisiest_rules"][0]["rule_name"] == "(unknown)"
