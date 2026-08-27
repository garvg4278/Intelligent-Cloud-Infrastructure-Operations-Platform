#!/usr/bin/env python3
"""Offline sanity check for gitops/ YAML.

Two things, neither requiring a cluster, ArgoCD, or network access:

1. Every .yaml file under gitops/ parses as YAML.
2. For files containing an ApplicationSet's `spec.generators` (a `list`
   generator, specifically -- the only kind used in this repo) and a
   `spec.template`, every `{{.field}}` / `{{ .field }}` Go-template
   reference found anywhere in the template block is checked against the
   field names the generator's `elements` actually define. This is the
   offline stand-in for the class of mistake that only otherwise surfaces
   as a real ArgoCD "field not found" error at sync time.
"""
import re
import sys
from pathlib import Path

import yaml

FIELD_RE = re.compile(r"\{\{-?\s*\.([A-Za-z_][A-Za-z0-9_]*)\s*-?\}\}")


def check_applicationset(doc: dict, rel_path: Path) -> list[str]:
    errors = []
    generators = doc.get("spec", {}).get("generators", [])
    element_fields = set()
    for gen in generators:
        if "list" in gen:
            for element in gen["list"].get("elements", []):
                element_fields.update(element.keys())

    if not element_fields:
        return errors  # not a list-generator ApplicationSet this script knows how to check

    template_text = yaml.dump(doc.get("spec", {}).get("template", {}))
    used_fields = set(FIELD_RE.findall(template_text))
    unknown = sorted(used_fields - element_fields)
    if unknown:
        unknown_refs = ", ".join("{{." + f + "}}" for f in unknown)
        errors.append(
            f"{rel_path}: template references {unknown_refs} "
            f"but the list generator's elements only define {sorted(element_fields)}"
        )
    return errors


def main():
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    yaml_files = sorted(root.rglob("*.yaml")) + sorted(root.rglob("*.yml"))
    if not yaml_files:
        print(f"No YAML files found under {root}")
        return 1

    errors = 0
    for f in yaml_files:
        rel = f.relative_to(root)
        try:
            docs = list(yaml.safe_load_all(f.read_text()))
        except yaml.YAMLError as e:
            print(f"FAIL {rel}\n  - parse error: {e}")
            errors += 1
            continue

        print(f"ok   {rel}")
        for doc in docs:
            if isinstance(doc, dict) and doc.get("kind") == "ApplicationSet":
                for err in check_applicationset(doc, rel):
                    print(f"FAIL {rel}\n  - {err}")
                    errors += 1

    print(f"\n{len(yaml_files)} file(s) checked, {errors} issue(s) found.")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
