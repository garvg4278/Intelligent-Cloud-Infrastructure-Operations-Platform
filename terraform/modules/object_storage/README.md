# terraform/modules/object_storage

One encrypted, versioned, non-public S3 bucket per environment for the
artifacts the original design doc describes (ROADMAP.md's linked design
doc, section 7.5): deployment manifests, build logs, reports, exported
incident bundles, model artifacts.

## Honest gap this module doesn't hide

**No ICOP service writes to this bucket yet.** This module creates
somewhere real and correctly-secured for that to happen, plus (via
`terraform/modules/irsa`) a way for a specific service's pods to get
scoped read/write access to it without static AWS keys -- but the actual
`ObjectStorageClient` (a boto3 S3 call behind a `Protocol`, same shape as
every other external-system client in this repo -- see
`services/deployment/app/orchestrator.py` or
`services/deployment/app/audit_client.py` for the pattern) hasn't been
written. That's real follow-up work, not something this module pretends
to have solved by existing.
