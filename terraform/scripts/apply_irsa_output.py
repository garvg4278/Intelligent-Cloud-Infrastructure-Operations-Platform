#!/usr/bin/env python3
"""Patch a real Terraform `deployment_irsa_role_arn` output into
gitops/values/services/deployment-worker.yaml, replacing the placeholder.

Text substitution, not a YAML parse+dump round-trip -- that file is
heavily comment-annotated, and a real YAML dump would silently strip
every one of those comments. gitops/README.md's own bootstrap step 3
uses `sed` on a different placeholder for exactly this reason.

**A real limitation this script does NOT fix**: deployment-worker.yaml is
one file, shared by both the staging and production ApplicationSets.
Each environment has its own `deployment_irsa` module instance with its
own real ARN -- but there's only one place in this repo to put "the"
annotation value today. Running this a second time, for the other
environment, overwrites the first environment's real ARN in that shared
file (this script will refuse to do that silently -- see --force below
-- but it can't make the underlying file structure hold two values at
once). See terraform/modules/irsa/README.md for the actual fix (splitting
into per-environment values files, or relocating this one key into the
environment-tier files instead).

Usage:
    terraform -chdir=terraform/environments/staging output -json \\
        | python3 terraform/scripts/apply_irsa_output.py

    # or from a saved file:
    python3 terraform/scripts/apply_irsa_output.py --outputs-file staging_outputs.json

    # preview without writing:
    python3 terraform/scripts/apply_irsa_output.py --dry-run < staging_outputs.json

    # prove this script works with no real terraform/AWS involved at all:
    python3 terraform/scripts/apply_irsa_output.py --self-test

Exits non-zero on any failure (missing output key, malformed JSON/ARN,
placeholder already replaced with a *different* real-looking ARN and
--force wasn't given, target file not found).
"""
import argparse
import json
import re
import sys
from pathlib import Path

OUTPUT_KEY = "deployment_irsa_role_arn"
PLACEHOLDER = "REPLACE_WITH_terraform_output_deployment_irsa_role_arn"
ARN_RE = re.compile(r"^arn:aws:iam::\d{12}:role/\S+$")
ANNOTATION_RE = re.compile(r'eks\.amazonaws\.com/role-arn:\s*"([^"]*)"')
DEFAULT_VALUES_FILE = (
    Path(__file__).resolve().parent.parent.parent
    / "gitops" / "values" / "services" / "deployment-worker.yaml"
)


def extract_arn(outputs: dict) -> str:
    """Pull the role ARN out of a `terraform output -json` dict (or a
    plain {key: value} dict, for tests/hand-built input). Raises
    ValueError with a specific, actionable message on anything wrong --
    main() just prints str(e) and exits 1, so keep these human-readable.
    """
    if OUTPUT_KEY not in outputs:
        available = ", ".join(sorted(outputs)) or "(none)"
        raise ValueError(
            f"no '{OUTPUT_KEY}' key in the given terraform output JSON. "
            f"Available outputs: {available}. Did you run this against "
            f"the right environment directory (terraform/environments/"
            f"staging or .../production)?"
        )
    raw = outputs[OUTPUT_KEY]
    # `terraform output -json` wraps each output as {"value": ..., "type": ...};
    # allow a plain string too, so a hand-built {"deployment_irsa_role_arn": "arn:..."}
    # works for tests without needing to fake terraform's exact shape.
    arn = raw["value"] if isinstance(raw, dict) and "value" in raw else raw
    if not isinstance(arn, str) or not ARN_RE.match(arn):
        raise ValueError(
            f"'{OUTPUT_KEY}' doesn't look like a real IAM role ARN: {arn!r}. "
            f"Expected something matching arn:aws:iam::<account-id>:role/<name>."
        )
    return arn


def patch_file(values_file: Path, arn: str, force: bool, dry_run: bool) -> int:
    if not values_file.exists():
        print(f"error: {values_file} does not exist", file=sys.stderr)
        return 1

    text = values_file.read_text()
    matches = ANNOTATION_RE.findall(text)

    if len(matches) == 0:
        print(
            f"error: found no 'eks.amazonaws.com/role-arn: \"...\"' line in "
            f"{values_file} to replace -- has the file's structure changed?",
            file=sys.stderr,
        )
        return 1
    if len(matches) > 1:
        print(
            f"error: found {len(matches)} matching lines in {values_file}, "
            f"expected exactly 1 -- refusing to guess which one. Edit the "
            f"file by hand.",
            file=sys.stderr,
        )
        return 1

    existing = matches[0]

    if existing == arn:
        print(f"{values_file}: already set to this exact ARN. No change.")
        return 0

    if existing != PLACEHOLDER and not force:
        print(
            f"error: {values_file} no longer contains the placeholder "
            f"({PLACEHOLDER!r}) -- it currently has {existing!r}, which "
            f"looks like a different real ARN already. Re-run with "
            f"--force to overwrite it anyway (this is exactly the "
            f"cross-environment overwrite risk documented in this "
            f"script's own module docstring and in "
            f"terraform/modules/irsa/README.md -- make sure that's "
            f"actually what you want before using --force).",
            file=sys.stderr,
        )
        return 1

    if dry_run:
        print(f"[dry-run] would replace the role-arn annotation in {values_file}:")
        print(f"  - old: {existing}")
        print(f"  + new: {arn}")
        return 0

    new_text = ANNOTATION_RE.sub(f'eks.amazonaws.com/role-arn: "{arn}"', text, count=1)
    values_file.write_text(new_text)
    print(f"{values_file}: role-arn annotation set to {arn}")
    return 0


def _self_test() -> int:
    """Round-trip sanity check using a fabricated example -- no real
    terraform, AWS, or gitops file touched. Exercises: the
    placeholder-replace path, the already-correct no-op path, the
    different-existing-value refusal path (and --force overriding it),
    and extract_arn's validation and both input shapes.
    """
    import tempfile

    sample = (
        "serviceAccount:\n"
        "  create: true\n"
        "  name: deployment-worker\n"
        "  annotations:\n"
        f'    eks.amazonaws.com/role-arn: "{PLACEHOLDER}"\n'
    )
    fake_arn = "arn:aws:iam::123456789012:role/icop-staging-deployment-artifacts"
    other_arn = "arn:aws:iam::999999999999:role/icop-production-deployment-artifacts"

    with tempfile.TemporaryDirectory() as tmp:
        f = Path(tmp) / "deployment-worker.yaml"
        f.write_text(sample)

        assert patch_file(f, fake_arn, force=False, dry_run=False) == 0
        rendered = f.read_text()
        assert fake_arn in rendered and PLACEHOLDER not in rendered, "placeholder wasn't replaced"

        assert patch_file(f, fake_arn, force=False, dry_run=False) == 0, "re-applying the same ARN should be a clean no-op"

        assert patch_file(f, other_arn, force=False, dry_run=False) == 1, "a different real ARN without --force should be refused"
        assert fake_arn in f.read_text(), "refused write must not touch the file"

        assert patch_file(f, other_arn, force=True, dry_run=False) == 0, "--force should override a different real ARN"
        assert other_arn in f.read_text()

        f.write_text(sample)
        assert patch_file(f, fake_arn, force=False, dry_run=True) == 0
        assert PLACEHOLDER in f.read_text(), "--dry-run must not write"

    try:
        extract_arn({OUTPUT_KEY: {"value": "not-an-arn"}})
        assert False, "extract_arn should have raised on a malformed ARN"
    except ValueError:
        pass

    try:
        extract_arn({"some_other_output": "whatever"})
        assert False, "extract_arn should have raised on a missing key"
    except ValueError:
        pass

    assert extract_arn({OUTPUT_KEY: fake_arn}) == fake_arn, "plain-string shape should work"
    assert extract_arn({OUTPUT_KEY: {"value": fake_arn, "type": "string"}}) == fake_arn, "terraform output -json shape should work"

    print("self-test: all checks passed")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--outputs-file", type=Path, default=None,
        help="Path to a saved `terraform output -json` file. Reads stdin if omitted.",
    )
    parser.add_argument(
        "--values-file", type=Path, default=DEFAULT_VALUES_FILE,
        help=f"Target values file (default: {DEFAULT_VALUES_FILE}).",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Overwrite an existing real-looking ARN, not just the placeholder "
             "-- see this script's own module docstring for the cross-environment risk first.",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show what would change without writing anything.",
    )
    parser.add_argument(
        "--self-test", action="store_true",
        help="Run built-in self-tests against a fabricated example and exit.",
    )
    args = parser.parse_args()

    if args.self_test:
        return _self_test()

    try:
        raw = args.outputs_file.read_text() if args.outputs_file else sys.stdin.read()
        outputs = json.loads(raw)
    except (OSError, json.JSONDecodeError) as e:
        print(f"error: couldn't read/parse terraform output JSON: {e}", file=sys.stderr)
        return 1

    try:
        arn = extract_arn(outputs)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    return patch_file(args.values_file, arn, args.force, args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
