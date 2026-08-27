# ansible/

Post-provision node configuration for the EKS clusters `terraform/`
creates -- the "Ansible installs runtime dependencies" / "Monitoring
agents are installed" steps of the original design doc's infrastructure
workflow (ROADMAP.md's linked design doc, section 6.4).

## Why SSM instead of SSH

Every node `terraform/modules/eks` creates has no SSH keypair, no public
IP, and no inbound rule for port 22 anywhere -- see that module's node
security group. Reaching nodes for configuration instead goes over AWS
Systems Manager Session Manager, using the `amazon.aws.aws_ssm` Ansible
connection plugin (the collection this used to ship under,
`community.aws`, now redirects to `amazon.aws` -- worth knowing if you've
used this plugin before under its old name). Concretely, that means:

- `terraform/modules/eks`'s node IAM role has
  `AmazonSSMManagedInstanceCore` attached, which is the only thing the
  EKS-optimized AMI's already-running SSM Agent needs to actually register.
- `terraform/modules/object_storage` creates a small, unversioned,
  1-day-lifecycle S3 bucket (`ssm_transfer_bucket` output) that the
  connection plugin uses to relay files and module code -- required by the
  plugin even for tasks that don't explicitly transfer a file, since
  Ansible ships its own module code to the target that way.
- Nothing here ever opens port 22, needs a bastion host, or stores an SSH
  private key anywhere.

## Running this

```bash
# Once:
ansible-galaxy collection install -r requirements.yml
# The AWS Session Manager plugin is a separate, non-Ansible binary the
# *controller* needs -- see AWS's docs for your OS:
# https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-working-with-install-plugin.html

cp inventory/aws_ec2.yml.example inventory/aws_ec2.yml
# edit the region and "tag:eks:cluster-name" filter for your environment

cd .. && terraform -chdir=terraform/environments/staging output -raw ssm_transfer_bucket
# copy that value into the next command:

ansible-playbook playbooks/site.yml \
  -e aws_region=us-east-1 \
  -e ssm_transfer_bucket=<value from the terraform output above>
```

## What's actually in scope here

This targets **EKS managed node group nodes running the standard AL2023
AMI** -- the default this repo's `terraform/modules/eks` uses. Two things
worth being explicit about:

- **This does not install kubelet, containerd, or the CNI.** EKS's own AMI
  bootstrap does that, before a node ever joins the cluster -- "managed
  node group" means AWS owns that part. `roles/baseline` verifies both are
  running (read-only -- `service_facts` + `assert`, never a start/restart)
  and fails loudly if either isn't, but it never tries to install or
  restart them. Pretending Ansible does that step, when EKS already did it
  first, is exactly the kind of unexplained inconsistency the original
  design doc warns makes a project look unconvincing (ROADMAP.md's linked
  design doc, section 34).
- **A Bottlerocket node group would not be reachable this way at all.**
  Bottlerocket (EKS's other first-party AMI option) has no general-purpose
  shell or package manager -- it's configured through its own API. This
  repo's node group doesn't use it, so the gap doesn't apply today, but
  switching `ami_type` in `terraform/modules/eks` later would silently
  break every playbook here without something in this README having said
  so.

## `inventory/ci-static.ini`

Not for real use -- a one-host static inventory that exists only so
`.github/workflows/ci.yml` can run `ansible-playbook --syntax-check`
without hitting the AWS API. The dynamic `aws_ec2` inventory plugin
(`inventory/aws_ec2.yml.example`) calls `ec2:DescribeInstances` the
moment Ansible loads it -- before a playbook ever runs, even for
`--syntax-check` -- which would fail outright without real AWS
credentials configured in CI. See the file itself for the fuller version
of this note.

## Status: written, never run

Same caveat as `terraform/README.md`, for the same reason (no network
egress at all from the sandbox this was built in -- not even to install
the `amazon.aws` collection, let alone reach a real EKS node over SSM).
What was checked instead: every YAML file here parses
(`scripts/check_ansible_yaml.py`, run from `ansible/`), and every Jinja2
`{{ }}` reference in a template or task resolves to a variable actually
defined somewhere in `defaults/`, `group_vars/`, or as a task `register:`
-- both by hand and with that same script. Run `ansible-playbook
playbooks/site.yml --syntax-check` for real before trusting this against
a real cluster; that alone (no AWS credentials needed, just the
collections installed) would catch anything this repo's own offline
checks can't.
