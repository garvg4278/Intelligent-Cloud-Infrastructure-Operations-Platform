# service-chart

One generic Helm chart used to deploy every ICOP service (`auth`,
`gateway`, `deployment`, and whatever comes next) via
`--set image.repository=<service> --set image.tag=<tag>`. See
`values.yaml` for the full set of overridable values.

## What's in it

- `Deployment` — replicas, resource requests/limits, liveness + readiness
  probes against `/health` (every ICOP service exposes this — see e.g.
  `services/auth/app/main.py`)
- `Service` (ClusterIP by default) — not rendered when `workload.type:
  worker` (a Celery worker has nothing to route HTTP traffic to)
- `HorizontalPodAutoscaler` — only rendered if `autoscaling.enabled: true`
- `ServiceAccount` — only rendered if `serviceAccount.create: true`;
  carries the `eks.amazonaws.com/role-arn` annotation IRSA needs (see
  `terraform/modules/irsa/README.md`)
- `NetworkPolicy` — only rendered if `networkPolicy.enabled: true` (on by
  default in both `gitops/values/environments/*.yaml` tiers) — see the
  template's own comments for exactly what it allows
- `PodDisruptionBudget` — on by default (`podDisruptionBudget.enabled:
  true` in this chart's own `values.yaml`)
- `ClusterRole` + `ClusterRoleBinding` — only rendered if
  `clusterRbac.enabled: true` (off by default; only
  `gitops/values/services/deployment-worker.yaml` turns it on today) —
  see `templates/clusterrole.yaml` for exactly what it grants and why
- Optional plain env vars (`env:`) and/or a `Secret` reference
  (`envFromSecret:`) — this chart does not create or manage secret
  contents, only references one that already exists

## How this was validated — read this before trusting it blindly

**No real `helm` binary was reachable from the sandbox this was built
in** (confirmed by direct connection to the real `github.com` — it's not
a network-allowlist issue, GitHub's release-asset endpoint 404'd for
reasons that weren't worth chasing further). That means `helm lint` and
`helm template` were never run against this chart, and it has never been
applied to a real cluster.

What *was* done instead: `_approximate_render_check.py` in this
directory is a small, deliberately narrow stand-in for `helm template` —
it handles exactly the Go-template constructs this chart uses
(`.Values.x.y`, `include`, `nindent`, `toYaml`, `{{- if }}`/`{{- end }}`)
and nothing more general. It renders every template in this directory —
`deployment.yaml`, `service.yaml`, `hpa.yaml`, `serviceaccount.yaml`,
`networkpolicy.yaml`, `poddisruptionbudget.yaml`, `clusterrole.yaml`,
`clusterrolebinding.yaml` — across several values combinations each and
confirms every one is valid YAML with the expected `kind`. Run it
yourself:

```bash
pip install pyyaml
python3 _approximate_render_check.py
```

**What that catches:** indentation bugs, unbalanced `if`/`end`, and
whether the output is structurally valid YAML for each combination.
**What it does NOT catch:** anything real Helm's actual template engine
or the Kubernetes API server would catch — a typo in a field name Helm
wouldn't care about but Kubernetes would reject, an invalid resource
value, a real `helm lint` schema warning, or (the big one) whether any of
this actually works against a real cluster.

**Before relying on this for anything real:** run `helm lint
infra/helm/service-chart` and `helm template` yourself once you have
`helm` installed locally, and apply it to a real (even local, e.g. `kind`
or `minikube`) cluster at least once. That's one command and a few
minutes — much cheaper than debugging an untested chart during an actual
deployment.

## Try it (once you have helm + a cluster)

```bash
helm lint infra/helm/service-chart
helm template auth infra/helm/service-chart \
  --set image.repository=icop-auth --set image.tag=latest -n local
helm upgrade --install auth infra/helm/service-chart \
  --set image.repository=icop-auth --set image.tag=latest -n local --create-namespace
```
