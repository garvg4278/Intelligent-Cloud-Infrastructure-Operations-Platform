# terraform/bootstrap

Creates the S3 bucket (versioned, encrypted, public access blocked) that
every environment in `terraform/environments/` uses as its remote state
backend, plus a DynamoDB lock table kept as a documented fallback for
Terraform versions older than 1.10.

## Why this is separate from everything else

A `backend "s3"` block has to point at a bucket that already exists --
Terraform can't create the very bucket it's about to store its own state
in during the same `apply`. So this module is applied by hand, once, with
**local** state, before `environments/staging` or `environments/production`
can run `terraform init` for the first time.

## Run this once per AWS account

```bash
cd terraform/bootstrap
terraform init
terraform apply -var="state_bucket_name=your-globally-unique-bucket-name"
```

Then put that same bucket name into `environments/staging/backend.tf` and
`environments/production/backend.tf` (see the placeholder there).

## Status

Written, never applied — no AWS account was reachable from the sandbox
this was built in (no network egress at all, in fact — see the root
README's caveats section). Same category of caveat as the Helm chart and
Prometheus/Grafana config already in this repo: syntactically real HCL,
cross-checked by hand against the AWS provider's documented resource
schema, but not `terraform validate`d or `apply`'d for real. Do that
before trusting it — `terraform validate` alone (no AWS credentials
needed, just provider download) would already catch anything structurally
wrong.
