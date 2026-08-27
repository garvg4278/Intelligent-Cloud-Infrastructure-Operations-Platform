# gitops/

ArgoCD configuration for continuously deploying every ICOP service (via
the one shared chart at `infra/helm/service-chart`) plus the observability
stack, onto the clusters `terraform/` creates. This is the "GitOps and
ArgoCD" piece of the original design doc (ROADMAP.md's linked design doc,
section 14): desired state lives in Git, ArgoCD makes the cluster match it.

```
gitops/
├── bootstrap/
│   └── argocd-values.yaml         # helm install argocd itself -- the one imperative step
├── root/
│   ├── root-app.yaml               # kubectl apply this once -- bootstraps everything below
│   └── resources/
│       ├── project.yaml             # AppProject: scopes what these Applications can touch
│       ├── applicationset-staging.yaml     # auto-sync: every merge reaches staging
│       ├── applicationset-production.yaml  # NO auto-sync: production needs a human to `argocd app sync`
│       └── observability.yaml       # kube-prometheus-stack, in the staging cluster (see caveats below)
└── values/
    ├── environments/{staging,production}.yaml   # replica/resource tier, shared by every service in that environment
    └── services/{gateway,auth,...}.yaml          # per-service identity: image repo, secret name, (deployment only) IRSA annotation
```

## Bootstrap order

```bash
# 1. Provision the staging cluster (terraform/environments/staging), then:
aws eks update-kubeconfig --name icop-staging --region us-east-1

# 2. Install ArgoCD itself into the staging cluster -- imperative, once:
helm repo add argo https://argoproj.github.io/argo-helm && helm repo update
kubectl create namespace argocd
helm install argocd argo/argo-cd -n argocd -f gitops/bootstrap/argocd-values.yaml

# 3. Point root-app.yaml and every ApplicationSet at this repo's real
#    remote (they all currently say https://github.com/YOUR_ORG/icop-platform.git):
grep -rl YOUR_ORG gitops/ | xargs sed -i 's#https://github.com/YOUR_ORG/icop-platform.git#<your real remote>#'

# 4. Bootstrap everything else:
kubectl apply -f gitops/root/root-app.yaml

# 5. Provision the production cluster (terraform/environments/production),
#    then register it as a remote destination -- see
#    applicationset-production.yaml's destination.name comment for why
#    this is a separate step rather than another in-cluster destination:
aws eks update-kubeconfig --name icop-production --region us-east-1 --alias icop-production
argocd cluster add icop-production --name icop-production-cluster

# 6. Create each service's envFromSecret (see values/services/*.yaml) in
#    both icop-staging and icop-production namespaces before expecting any
#    Application to actually come up healthy -- this repo's chart never
#    manages secret *contents*, only references a name (same "bring your
#    own secrets" posture as ANTHROPIC_API_KEY in the root README).
```

## Honest caveats

- **Both ApplicationSets deploy 15 Applications now, not 10** —
  `deployment-worker`, `alert-worker`, `alert-beat`, `notification-worker`,
  and `infrastructure-worker` were missing until a follow-up audit found
  it (see ROADMAP.md's Phase 6 "Follow-up hardening" section): without
  them, this repo's GitOps would deploy every API service correctly and
  nothing would ever actually consume the jobs those APIs enqueue. Each
  worker's `gitops/values/services/*-worker.yaml` sets
  `workload.type: worker` (see `infra/helm/service-chart/values.yaml`),
  which is what makes it render with no Service and no HTTP probes
  instead of the default web-service shape.
- **`networkPolicy.enabled: true` in both environment values files (Phase
  6) means every service is unreachable from outside its own
  `icop-{env}` namespace by default, the observability namespace
  excepted.** Real, and on by default deliberately (see
  `infra/helm/service-chart/templates/networkpolicy.yaml`'s own
  comments for why) -- but it means anything added later that needs to
  reach a service cross-namespace (a future Ingress controller,
  a monitoring tool outside the `observability` namespace) will need an
  explicit allow rule added, not just a Service/DNS entry. This has never
  synced against a real cluster (see below), so that interaction is
  reasoned through, not observed.
- **`root/resources/project.yaml`'s resource whitelists didn't cover
  everything the chart actually renders, until a later audit pass caught
  it.** `podDisruptionBudget.enabled: true` is the chart's own default
  (see `infra/helm/service-chart/values.yaml`) and `networkPolicy.enabled`
  is on in both environment tiers (previous bullet) -- meaning both kinds
  render for every single service, in both environments, always. Neither
  `NetworkPolicy` nor `PodDisruptionBudget` was in
  `namespaceResourceWhitelist` until this pass added them. As committed
  before that fix, every Application sync would have failed on "resource
  kind not permitted in project" for both kinds, on every service, in
  both environments -- a real bug the earlier structural checks
  (`check_gitops_yaml.py` parses YAML shape, not cross-file resource-kind
  coverage) had no way to catch. Nothing currently re-checks this
  automatically; a chart change that adds a new resource kind can
  reintroduce the same class of bug.
- **`deployment-worker` now carries a ClusterRole/ClusterRoleBinding**
  (`clusterRbac.enabled: true` in its values file), whitelisted in
  `project.yaml`'s `clusterResourceWhitelist` alongside the fix above.
  This closes the "IRSA only grants AWS permissions, not Kubernetes API
  permissions" gap noted in `terraform/modules/irsa/README.md` -- see
  `infra/helm/service-chart/templates/clusterrole.yaml` for exactly what
  it grants and why it has to be cluster-scoped. Real code, same caveat
  as everything else in this list: never synced against a live cluster,
  so the actual permission set has been reasoned through against
  `orchestrator.py`/`executor.py`'s real behavior, not observed working.
- **Every `repoURL` says `YOUR_ORG/icop-platform.git`.** This repo doesn't
  have a real Git remote yet (it's been worked on as a local checkout /
  zip export) -- every Application these ApplicationSets produce would
  fail to sync until that placeholder is replaced with a real one. Step 3
  above is not optional.
- **The observability Application deploys into the staging cluster only.**
  Production, as its own separate EKS cluster
  (`terraform/environments/production`), would need its own Prometheus/
  Grafana (or a remote-write setup feeding one central store) -- not built
  here. See `observability.yaml`'s own comments for exactly what scrape
  config it does carry over from the existing, real
  `infra/prometheus/prometheus.yml`.
- **Nothing here has synced against a real ArgoCD instance.** Same category
  of caveat as `terraform/` and `ansible/` -- no network access at all from
  the sandbox this was built in. What was checked instead:
  `scripts/check_gitops_yaml.py` (parses every YAML file, and for the
  ApplicationSets specifically, checks every `{{.field}}` Go-template
  reference resolves to a field the generator actually produces). Run
  `argocd app diff` / `kubectl apply --dry-run=server` for real, with a
  real ArgoCD instance, before trusting this against anything real.
- **The chart version pins in `bootstrap/argocd-values.yaml` and
  `observability.yaml`** were current when written; re-check
  `helm search repo <chart> --versions` before actually applying either --
  both are the kind of fast-moving numbers this repo's own conventions
  (see the root README's knowledge-cutoff-adjacent caveats) say not to
  trust blindly months later.
