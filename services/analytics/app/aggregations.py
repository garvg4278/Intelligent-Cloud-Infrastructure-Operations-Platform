"""Pure functions turning raw records from other services into
statistics. No I/O, no imports from service_clients -- every function
here takes plain lists of dicts (exactly what those services' APIs
return) and returns a plain dict. That separation is what makes this
module's logic fully unit-testable without mocking any HTTP call at all.
"""

from collections import Counter
from datetime import datetime


def _parse(ts: str) -> datetime:
    # Pydantic v2 serializes tz-aware datetimes as e.g.
    # "2026-08-09T11:22:46.396592Z" (Z suffix, not "+00:00") -- checked
    # directly against DeploymentOut.model_dump_json(), not assumed.
    # Python 3.11+'s fromisoformat handles that Z suffix natively.
    return datetime.fromisoformat(ts)


def deployment_stats(deployments: list[dict]) -> dict:
    total = len(deployments)
    if total == 0:
        return {"total": 0, "success_rate": None, "by_status": {}, "deployments_per_day": None}

    by_status = Counter(d["status"] for d in deployments)
    succeeded = by_status.get("succeeded", 0)

    timestamps = sorted(_parse(d["created_at"]) for d in deployments)
    span_days = (timestamps[-1] - timestamps[0]).total_seconds() / 86400
    deployments_per_day = total / span_days if span_days > 0 else float(total)

    return {
        "total": total,
        "success_rate": round(succeeded / total, 4),
        "by_status": dict(by_status),
        "deployments_per_day": round(deployments_per_day, 4),
    }


def incident_stats(incidents: list[dict]) -> dict:
    total = len(incidents)
    if total == 0:
        return {
            "total": 0,
            "by_status": {},
            "by_severity": {},
            "resolved_count": 0,
            "avg_resolution_seconds": None,
        }

    by_status = Counter(i["status"] for i in incidents)
    by_severity = Counter(i["severity"] for i in incidents)

    resolution_times = [
        (_parse(i["resolved_at"]) - _parse(i["created_at"])).total_seconds()
        for i in incidents
        if i.get("resolved_at")
    ]

    return {
        "total": total,
        "by_status": dict(by_status),
        "by_severity": dict(by_severity),
        "resolved_count": len(resolution_times),
        "avg_resolution_seconds": (
            round(sum(resolution_times) / len(resolution_times), 2) if resolution_times else None
        ),
    }


def alert_stats(rules: list[dict], alerts: list[dict]) -> dict:
    total = len(alerts)
    rule_names = {r["id"]: r["name"] for r in rules}

    if total == 0:
        return {"total": 0, "by_severity": {}, "by_status": {}, "noisiest_rules": []}

    by_severity = Counter(a["severity"] for a in alerts)
    by_status = Counter(a["status"] for a in alerts)
    rule_counts = Counter(a["rule_id"] for a in alerts)
    noisiest_rules = [
        {"rule_id": rule_id, "rule_name": rule_names.get(rule_id, "(unknown)"), "count": count}
        for rule_id, count in rule_counts.most_common(5)
    ]

    return {
        "total": total,
        "by_severity": dict(by_severity),
        "by_status": dict(by_status),
        "noisiest_rules": noisiest_rules,
    }
