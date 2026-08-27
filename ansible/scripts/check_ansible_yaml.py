#!/usr/bin/env python3
"""Offline sanity check for this ansible/ directory.

Not a substitute for `ansible-playbook --syntax-check` -- it doesn't know
module argument schemas, doesn't resolve role dependencies, and doesn't
understand Jinja control flow (loops, conditionals) precisely. What it
does, without needing ansible-core, its collections, or network access to
install either:

1. Parses every .yml/.yaml file as YAML -- catches indentation errors,
   bad quoting, tab characters, all the ways hand-written YAML most often
   breaks.
2. Extracts every `{{ variable }}` reference (from YAML files and any
   .j2 templates) and checks the base variable name resolves to
   something defined in a role's defaults/, a group_vars/ file, a
   `register:` in a tasks file, a loop variable, or one of a known set of
   Ansible "magic"/fact variables -- flagging anything that looks like a
   typo'd or never-defined variable.

Usage: python3 check_ansible_yaml.py [root_dir]
"""
import re
import sys
from pathlib import Path

import yaml

# Variables Ansible provides itself, or that this repo's roles bind via
# loop/register in ways this script's static scan can't easily trace
# task-by-task -- known-good, not something a typo could plausibly produce.
KNOWN_VARS = {
    "ansible_managed", "inventory_hostname", "ansible_facts", "item",
    "ansible_distribution", "ansible_os_family", "ansible_hostname",
    "existing_binary", "installed_version", "containerd_status",
    "aws_region", "ssm_transfer_bucket",
}


def find_yaml_files(root: Path):
    return sorted(p for p in root.rglob("*.yml")) + sorted(p for p in root.rglob("*.yaml"))


def find_jinja_files(root: Path):
    return sorted(root.rglob("*.j2"))


def extract_jinja_vars(text: str) -> set[str]:
    names = set()
    for m in re.finditer(r"\{\{(.*?)\}\}", text, re.DOTALL):
        expr = m.group(1)
        # Strip Jinja filters (| default(...), | int, etc.) -- only the
        # base variable name (and any dotted/bracket attribute access
        # root) is checked.
        expr = expr.split("|")[0].strip()
        ident = re.match(r"[A-Za-z_][A-Za-z0-9_]*", expr)
        if ident:
            names.add(ident.group(0))
    return names


def collect_defined_vars(root: Path) -> set[str]:
    defined = set(KNOWN_VARS)
    for pattern_dir in ["defaults", "group_vars", "vars"]:
        for f in root.rglob(f"*/{pattern_dir}/*.yml"):
            data = yaml.safe_load(f.read_text()) or {}
            if isinstance(data, dict):
                defined.update(data.keys())
        for f in root.glob(f"{pattern_dir}/*.yml"):
            data = yaml.safe_load(f.read_text()) or {}
            if isinstance(data, dict):
                defined.update(data.keys())

    # register: targets and loop vars, and set_fact keys, from every tasks file
    for f in root.rglob("tasks/*.yml"):
        text = f.read_text()
        defined.update(re.findall(r"register:\s*([A-Za-z_][A-Za-z0-9_]*)", text))
        defined.update(re.findall(r"set_fact:\s*\n(?:\s+([A-Za-z_][A-Za-z0-9_]*):)+", text))
        defined.update(re.findall(r"loop_var:\s*([A-Za-z_][A-Za-z0-9_]*)", text))
    return defined


def main():
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".")

    yaml_files = find_yaml_files(root)
    jinja_files = find_jinja_files(root)
    if not yaml_files:
        print(f"No YAML files found under {root}")
        return 1

    errors = 0

    print("== YAML parse check ==")
    for f in yaml_files:
        rel = f.relative_to(root)
        try:
            # Ansible task files are lists of dicts; group_vars/defaults
            # are dicts. safe_load handles both; we just need it not to raise.
            list(yaml.safe_load_all(f.read_text()))
            print(f"ok   {rel}")
        except yaml.YAMLError as e:
            errors += 1
            print(f"FAIL {rel}\n  - {e}")

    print("\n== Jinja2 variable reference check ==")
    defined = collect_defined_vars(root)
    for f in list(yaml_files) + list(jinja_files):
        rel = f.relative_to(root)
        used = extract_jinja_vars(f.read_text())
        unknown = sorted(v for v in used if v not in defined)
        if unknown:
            errors += 1
            print(f"FAIL {rel}: possibly-undefined variable(s): {unknown}")
        else:
            print(f"ok   {rel} ({len(used)} var ref(s), all recognized)")

    print(f"\n{len(yaml_files)} YAML file(s), {len(jinja_files)} template(s) checked, {errors} issue(s) found.")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
