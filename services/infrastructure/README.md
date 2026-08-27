# infrastructure service

Provisions and destroys this platform's own AWS environments by driving
Terraform (`../../terraform/`) and Ansible (`../../ansible/`) from a Celery
worker, the same shape as the `deployment` service driving Helm/kubectl:
a Protocol-based orchestrator per external tool, a pure state-machine
`executor.py` with no Celery import, and every transition audited.

## What this actually does

```
POST /environments {"environment_type": "staging"}
  -> pending
  -> provisioning_infra   (terraform -chdir=.../staging apply -auto-approve)
  -> configuring_nodes    (ansible-playbook -i inventory playbooks/site.yml)
  -> ready                (cluster_name recorded from `terraform output`)
```

A failure at either step lands on `provision_failed` with the real error
message attached -- see `executor.py`'s comments for why a Terraform
success followed by an Ansible failure still records `cluster_name`
rather than discarding it: the infrastructure genuinely exists at that
point, only node configuration didn't finish.

```
DELETE /environments/{id}
  -> destroying
  -> destroyed   (terraform -chdir=... destroy -auto-approve)
```

Only `ready`, `provision_failed`, or `destroy_failed` environments can be
destroyed -- see `routers/environments.py`'s `_DESTROYABLE_STATUSES`.

## Why exactly two environment types

`environment_type` is `staging` or `production` and nothing else,
matching `terraform/environments/` exactly. `POST /environments` doesn't
take a free-text name -- `name` is always derived
(`f"icop-{environment_type}"`) because that's genuinely the only thing
`terraform apply` can target today. This is narrower than the original
design doc's more general "provision an environment on demand" framing
(the linked design doc in ROADMAP.md, section 6.4) -- see
`../../terraform/README.md`'s own note on that gap. At most one active
(non-destroyed) environment per type is enforced at the API layer
(`crud.get_active_environment_by_type`), since the Terraform layout is a
singleton per type, not a multi-tenant factory.

## Honest gaps

- **Never run against a real AWS account.** Same caveat as
  `terraform/README.md` and `ansible/README.md` -- everything here is
  tested with `subprocess.run` mocked out (`tests/test_terraform_orchestrator.py`,
  `tests/test_ansible_orchestrator.py`) and the full state machine tested
  through fakes (`tests/test_api.py`), never a real `terraform apply`.
- **No progress visibility during a run.** A real `terraform apply` for
  EKS takes 15-20 minutes; a real `ansible-playbook` run against a fresh
  node group adds more. `GET /environments/{id}` only reports whichever
  of the four statuses the row is currently in, not per-resource progress
  within `provisioning_infra` -- streaming that (e.g. by tailing terraform's
  own JSON log format, `TF_LOG` output, or Ansible's callback plugins into
  something pollable) is real follow-up work, not built here.
- **No concurrency control beyond the one-active-per-type check.** Two
  concurrent `POST /environments` requests for the same type racing past
  `get_active_environment_by_type` before either commits could both
  proceed -- a real `SELECT ... FOR UPDATE` or a unique partial index
  would close this properly; not done here.
- **No progress rollback if `configuring_nodes` fails.** Unlike the
  deployment service's automatic Helm rollback on a failed health check,
  a failed Ansible run here does not `terraform destroy` automatically --
  the infrastructure is left standing (in `provision_failed`) for an
  operator to inspect or retry against, on the theory that auto-destroying
  a freshly-created EKS cluster because a package install failed is a much
  more expensive mistake to make automatically than leaving it for a human
  to look at first.

## Running tests

Same as every other service: `pytest` from this directory, or `make test`
from the repo root, against in-memory SQLite + Celery's eager mode +
mocked `subprocess.run` -- no Terraform/Ansible/AWS involved. 31 tests.
