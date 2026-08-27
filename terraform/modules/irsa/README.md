# terraform/modules/irsa

Generic "trust exactly this ServiceAccount, grant exactly this policy"
module. Instantiated once per (service, AWS permission) pair that needs
one -- see `environments/staging/main.tf` **and**
`environments/production/main.tf` for the one real instantiation today in
each (the `deployment` service, read/write on the artifacts bucket from
`modules/object_storage`) -- both environments define it, since IAM roles
aren't shared across accounts/clusters the way a Helm chart is.

## The Kubernetes side of IRSA -- now wired, not yet real

Creating the IAM role is only half of IRSA. The other half is the
Kubernetes side, and as of this pass all of it exists in code:

- `infra/helm/service-chart` has a `serviceAccount.create` /
  `serviceAccount.annotations` value block (and the template to go with
  it), so a pod can actually run as a ServiceAccount carrying an
  `eks.amazonaws.com/role-arn` annotation instead of `default`.
- `gitops/values/services/deployment-worker.yaml` turns that on and sets
  the annotation -- currently to a placeholder string, not a real ARN
  (see below).
- The *other* half of "can this pod actually act on the cluster",
  in-cluster Kubernetes RBAC, is now also wired:
  `infra/helm/service-chart/templates/clusterrole.yaml` +
  `clusterrolebinding.yaml`, toggled on via `clusterRbac.enabled` in that
  same values file. IRSA and in-cluster RBAC are two genuinely different
  permission systems (AWS API vs. the cluster's own Kubernetes API) that
  are easy to conflate -- see that template file's own comments for why
  both were needed and why the K8s side specifically had to be a
  ClusterRole rather than a namespaced Role.

## What's still not real

Every piece above is real, reviewable code -- none of it has run against
an actual AWS account. This module produces a correctly-scoped IAM role
*specification*; nobody has run `terraform apply` (no AWS credentials or
network egress were available in any session that built this, sandboxed
the same way this one is). Concretely, that leaves:

1. The placeholder in `deployment-worker.yaml`
   (`REPLACE_WITH_terraform_output_deployment_irsa_role_arn`) needs the
   real `deployment_irsa_role_arn` output from a real `terraform apply`,
   for whichever environment you apply first.
   `terraform/scripts/apply_irsa_output.py` automates that hand-off --
   see its own docstring.
2. **A real limitation the placeholder-patching script above can't paper
   over**: `deployment-worker.yaml` is one file, loaded by *both* the
   staging and production `ApplicationSet`s
   (`gitops/root/resources/applicationset-{staging,production}.yaml`
   both list it under `helm.valueFiles`). Staging and production each
   get their *own* IAM role from their *own* `deployment_irsa` module
   instantiation, with different ARNs -- but there's only one place to
   put "the" annotation value today. Applying the script for the second
   environment will overwrite the first environment's real ARN in this
   shared file. This isn't a new problem introduced by the script; the
   placeholder already had this shape before the script existed. Fixing
   it for real means either splitting this into per-environment
   per-service values files, or moving just this one annotation into the
   environment-tier files (`gitops/values/environments/*.yaml`) and
   relying on Helm's per-key map merge to let the service-level file's
   *other* keys still win -- both are real, undone design decisions, not
   implemented here.
3. Nothing has verified the trust policy's OIDC condition actually
   matches a real cluster's real OIDC provider, since no real cluster
   exists to check it against.
