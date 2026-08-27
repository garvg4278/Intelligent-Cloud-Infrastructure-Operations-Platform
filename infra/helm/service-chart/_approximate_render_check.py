"""NOT Helm. This is a deliberately narrow stand-in for `helm template`,
built because no real helm binary is reachable from this sandbox (see the
chart's README for why). It handles exactly the Go-template constructs
used in this chart's templates -- {{ .Values.x.y }}, {{ include ... }},
{{ ... | nindent N }}, {{ toYaml ... | nindent N }}, and
{{- if COND }} / {{- end }} -- and nothing more general than that.

What this catches: indentation bugs, unbalanced if/end, and whether the
rendered output is valid YAML for a given values combination.
What this does NOT catch: anything a real `helm template` / `helm lint`
/ `kubectl apply --dry-run` would catch that's specific to Helm's actual
template engine or the Kubernetes API schema. Treat a clean run of this
script as "the YAML shape looks structurally sound," not as "Helm
approved this chart."
"""

import re
import sys
from pathlib import Path

import yaml

CHART_DIR = Path(__file__).parent
TEMPLATES_DIR = CHART_DIR / "templates"


def load_values(overrides: dict) -> dict:
    with open(CHART_DIR / "values.yaml") as f:
        values = yaml.safe_load(f)
    for key, val in overrides.items():
        values[key] = val
    return values


def get_path(ctx: dict, dotted: str):
    node = ctx
    for part in dotted.split(".")[1:]:  # drop leading "" from ".Values.x"
        node = node[part]
    return node


def render_helpers(release_name: str, chart_app_version: str, values: dict) -> dict[str, str]:
    sa = values.get("serviceAccount", {}) or {}
    # Mirrors _helpers.tpl's service-chart.serviceAccountName exactly:
    # explicit name wins, else the fullname if we're creating one, else the
    # namespace's literal "default" ServiceAccount.
    if sa.get("name"):
        service_account_name = sa["name"]
    elif sa.get("create"):
        service_account_name = release_name  # == service-chart.fullname
    else:
        service_account_name = "default"

    selector_labels = f"app.kubernetes.io/name: {release_name}\napp.kubernetes.io/instance: {release_name}"

    return {
        "service-chart.fullname": release_name,
        "service-chart.labels": (
            f"app.kubernetes.io/name: {release_name}\n"
            f"app.kubernetes.io/instance: {release_name}\n"
            f"app.kubernetes.io/managed-by: Helm\n"
            f'app.kubernetes.io/version: "{chart_app_version}"'
        ),
        "service-chart.selectorLabels": selector_labels,
        "service-chart.podLabels": f"{selector_labels}\nicop.io/component: {values.get('component') or 'backend-service'}",
        "service-chart.serviceAccountName": service_account_name,
    }


def truthy(value) -> bool:
    if isinstance(value, (list, dict)):
        return len(value) > 0
    return bool(value)


def render_template(text: str, values: dict, release_name: str, namespace: str, app_version: str) -> str:
    helpers = render_helpers(release_name, app_version, values)
    ctx = {"Values": values, "Release": {"Name": release_name, "Namespace": namespace, "Service": "Helm"},
           "Chart": {"AppVersion": app_version}}

    lines = text.split("\n")
    out_lines: list[str] = []
    # Stack of booleans: whether we're currently inside a TRUE branch at
    # each nesting level of {{- if }} / {{- end }}.
    cond_stack: list[bool] = []

    def active() -> bool:
        return all(cond_stack)

    if_re = re.compile(r"^\s*\{\{-\s*if\s+(.+?)\s*\}\}\s*$")
    end_re = re.compile(r"^\s*\{\{-\s*end\s*\}\}\s*$")

    for raw_line in lines:
        if_match = if_re.match(raw_line)
        if if_match:
            cond_stack.append(active() and eval_condition(if_match.group(1), ctx))
            continue
        if end_re.match(raw_line):
            if cond_stack:
                cond_stack.pop()
            continue
        if not active():
            continue
        out_lines.append(render_line(raw_line, ctx, helpers))

    return "\n".join(out_lines)


def eval_condition(expr: str, ctx: dict) -> bool:
    expr = expr.strip()
    if expr.startswith("not "):
        return not eval_condition(expr[4:], ctx)
    if expr.startswith("or "):
        parts = split_args(expr[3:])
        return any(eval_condition(p, ctx) for p in parts)
    if expr.startswith("eq "):
        parts = split_args(expr[3:])
        if len(parts) != 2:
            raise ValueError(f"eq expects exactly 2 args, got: {expr!r}")
        return _resolve_eq_operand(parts[0], ctx) == _resolve_eq_operand(parts[1], ctx)
    return truthy(resolve_value(expr, ctx))


def _resolve_eq_operand(token: str, ctx: dict):
    token = token.strip()
    if token.startswith('"') and token.endswith('"'):
        return token[1:-1]
    if token.startswith("."):
        return resolve_value(token, ctx)
    return token


def split_args(s: str) -> list[str]:
    return [p for p in s.split(" ") if p]


def resolve_value(expr: str, ctx: dict):
    expr = expr.strip()
    if expr.startswith("."):
        return get_path(ctx, expr)
    raise ValueError(f"cannot resolve: {expr!r}")


NINDENT_RE = re.compile(r"\{\{-?\s*(.+?)\s*\|\s*nindent\s+(\d+)\s*\}\}")
INCLUDE_RE = re.compile(r'include\s+"([^"]+)"\s+\.')
TOYAML_RE = re.compile(r"toYaml\s+(\..+)")
SIMPLE_RE = re.compile(r"\{\{\s*(.+?)\s*\}\}")


def render_line(line: str, ctx: dict, helpers: dict) -> str:
    nindent_match = NINDENT_RE.search(line)
    if nindent_match:
        inner, indent_n = nindent_match.group(1), int(nindent_match.group(2))
        content = render_pipeable(inner, ctx, helpers)
        indented = "\n".join((" " * indent_n) + ln if ln else ln for ln in content.split("\n"))
        return line[: nindent_match.start()].rstrip() + indented

    def sub_simple(m: re.Match) -> str:
        return str(render_pipeable(m.group(1), ctx, helpers))

    return SIMPLE_RE.sub(sub_simple, line)


def render_pipeable(expr: str, ctx: dict, helpers: dict):
    include_match = INCLUDE_RE.match(expr)
    if include_match:
        return helpers[include_match.group(1)]
    toyaml_match = TOYAML_RE.match(expr)
    if toyaml_match:
        value = get_path(ctx, toyaml_match.group(1))
        return yaml.safe_dump(value, default_flow_style=False).rstrip("\n")
    if expr.startswith("."):
        return get_path(ctx, expr)
    raise ValueError(f"unhandled expression: {expr!r}")


def render_and_check(template_name: str, values_overrides: dict, label: str) -> None:
    values = load_values(values_overrides)
    text = (TEMPLATES_DIR / template_name).read_text()
    rendered = render_template(text, values, release_name="auth", namespace="local", app_version="0.1.0")
    if not rendered.strip():
        print(f"[{label}] {template_name}: renders to nothing (expected for hpa.yaml when disabled)")
        return
    try:
        parsed = yaml.safe_load(rendered)
    except yaml.YAMLError as exc:
        print(f"[{label}] {template_name}: INVALID YAML -- {exc}")
        print(rendered)
        sys.exit(1)
    print(f"[{label}] {template_name}: valid YAML, kind={parsed.get('kind')}")


if __name__ == "__main__":
    render_and_check("deployment.yaml", {}, "defaults")
    render_and_check("service.yaml", {}, "defaults")
    render_and_check("hpa.yaml", {}, "defaults (autoscaling disabled)")

    render_and_check("deployment.yaml", {"env": [{"name": "LOG_LEVEL", "value": "info"}]}, "with env")
    render_and_check("deployment.yaml", {"envFromSecret": "auth-secrets"}, "with envFromSecret")
    render_and_check(
        "deployment.yaml",
        {"env": [{"name": "LOG_LEVEL", "value": "info"}], "envFromSecret": "auth-secrets"},
        "with env AND envFromSecret",
    )
    render_and_check(
        "hpa.yaml", {"autoscaling": {"enabled": True, "minReplicas": 2, "maxReplicas": 10,
                                      "targetCPUUtilizationPercentage": 70}},
        "autoscaling enabled",
    )

    render_and_check("serviceaccount.yaml", {}, "defaults (serviceAccount.create=false -> renders to nothing)")
    render_and_check(
        "serviceaccount.yaml",
        {"serviceAccount": {"create": True, "name": "", "annotations": {}}},
        "create=true, no explicit name (falls back to fullname)",
    )
    render_and_check(
        "serviceaccount.yaml",
        {"serviceAccount": {"create": True, "name": "", "annotations": {
            "eks.amazonaws.com/role-arn": "arn:aws:iam::123456789012:role/icop-staging-deployment-artifacts"
        }}},
        "create=true, with IRSA role-arn annotation",
    )
    # deployment.yaml's new serviceAccountName line, exercised at every
    # serviceAccount.create state (not just the top-of-file default case).
    render_and_check(
        "deployment.yaml",
        {"serviceAccount": {"create": True, "name": "", "annotations": {}}},
        "deployment.yaml with serviceAccount.create=true",
    )
    render_and_check(
        "deployment.yaml",
        {"serviceAccount": {"create": True, "name": "custom-sa-name", "annotations": {}}},
        "deployment.yaml with explicit serviceAccount.name",
    )

    render_and_check(
        "networkpolicy.yaml", {},
        "defaults (networkPolicy.enabled=false -> renders to nothing)",
    )
    render_and_check(
        "networkpolicy.yaml",
        {"networkPolicy": {"enabled": True, "observabilityNamespace": "observability"}},
        "networkPolicy.enabled=true, default observability namespace",
    )
    render_and_check(
        "networkpolicy.yaml",
        {"networkPolicy": {"enabled": True, "observabilityNamespace": "monitoring-custom"}},
        "networkPolicy.enabled=true, custom observability namespace",
    )
    # deployment.yaml's pod template now uses podLabels (selectorLabels +
    # icop.io/component), not selectorLabels directly -- confirmed it
    # still renders correctly with a non-default component value.
    render_and_check(
        "deployment.yaml", {"component": "gateway"},
        "deployment.yaml with component=gateway (podLabels helper)",
    )

    render_and_check(
        "poddisruptionbudget.yaml", {"podDisruptionBudget": {"enabled": True}},
        "podDisruptionBudget.enabled=true (the chart's own default)",
    )
    render_and_check(
        "poddisruptionbudget.yaml", {"podDisruptionBudget": {"enabled": False}},
        "podDisruptionBudget.enabled=false -> renders to nothing",
    )

    render_and_check(
        "deployment.yaml",
        {"workload": {"type": "worker", "command": ["celery", "-A", "app.tasks", "worker", "--loglevel=info"]}},
        "workload.type=worker with a command override",
    )
    render_and_check(
        "service.yaml",
        {"workload": {"type": "worker", "command": []}},
        "service.yaml with workload.type=worker -> renders to nothing",
    )

    render_and_check(
        "clusterrole.yaml", {"clusterRbac": {"enabled": False}},
        "defaults (clusterRbac.enabled=false -> renders to nothing)",
    )
    render_and_check(
        "clusterrole.yaml", {"clusterRbac": {"enabled": True}},
        "clusterRbac.enabled=true",
    )
    render_and_check(
        "clusterrolebinding.yaml", {"clusterRbac": {"enabled": False}},
        "defaults (clusterRbac.enabled=false -> renders to nothing)",
    )
    render_and_check(
        "clusterrolebinding.yaml",
        {"clusterRbac": {"enabled": True}, "serviceAccount": {"create": True, "name": "", "annotations": {}}},
        "clusterRbac.enabled=true, with serviceAccount.create=true",
    )

    print("\nAll checked value combinations render to valid YAML.")
