#!/usr/bin/env python3
"""Offline structural sanity check for .tf files.

Not a substitute for `terraform validate` -- it has no idea what a valid
argument name is, whether a referenced attribute exists on a resource, or
whether types line up. What it *does* catch, without needing the
provider plugin (i.e. without network access): unbalanced braces,
brackets, parens, or quotes, which is the single most common way
hand-written HCL breaks, and the first thing `terraform validate` would
report anyway.

Usage: python3 check_tf_balance.py [root_dir]
Exits non-zero if any file fails.
"""
import re
import sys
from pathlib import Path

PAIRS = {"{": "}", "[": "]", "(": ")"}
CLOSERS = {v: k for k, v in PAIRS.items()}


def strip_comments_and_strings(text: str) -> str:
    """Blank out string contents and comments so their brace-like
    characters (e.g. a "${...}" example inside a comment, or a literal
    "{" inside a description string) can't confuse the balance check --
    replace each with a same-length run of 'x' to preserve line/column
    positions for error messages.
    """
    out = []
    i = 0
    n = len(text)
    in_string = False
    while i < n:
        ch = text[i]
        if in_string:
            if ch == "\\" and i + 1 < n:
                out.append("xx")
                i += 2
                continue
            if ch == '"':
                in_string = False
                out.append(ch)
                i += 1
                continue
            out.append("x" if ch != "\n" else "\n")
            i += 1
            continue

        if ch == '"':
            in_string = True
            out.append(ch)
            i += 1
            continue

        if ch == "#" or text[i:i+2] == "//":
            j = text.find("\n", i)
            j = n if j == -1 else j
            out.append(text[i:j])
            i = j
            continue

        if text[i:i+2] == "/*":
            j = text.find("*/", i + 2)
            j = n if j == -1 else j + 2
            out.append(re.sub(r"[^\n]", "x", text[i:j]))
            i = j
            continue

        out.append(ch)
        i += 1
    return "".join(out)


def check_file(path: Path) -> list[str]:
    errors = []
    text = path.read_text()
    cleaned = strip_comments_and_strings(text)

    stack = []
    line = 1
    for ch in cleaned:
        if ch == "\n":
            line += 1
        elif ch in PAIRS:
            stack.append((ch, line))
        elif ch in CLOSERS:
            if not stack:
                errors.append(f"line {line}: unmatched closing '{ch}'")
                continue
            open_ch, open_line = stack.pop()
            if PAIRS[open_ch] != ch:
                errors.append(
                    f"line {line}: '{ch}' does not match '{open_ch}' opened at line {open_line}"
                )
    for open_ch, open_line in stack:
        errors.append(f"line {open_line}: unclosed '{open_ch}'")

    # Quote balance on the ORIGINAL text (cleaned text has already
    # resolved strings, so check raw quote count minus escaped quotes is even).
    raw_quotes = len(re.findall(r'(?<!\\)"', text))
    if raw_quotes % 2 != 0:
        errors.append("odd number of unescaped double-quote characters in file")

    return errors


def main():
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    tf_files = sorted(root.rglob("*.tf"))
    if not tf_files:
        print(f"No .tf files found under {root}")
        return 1

    total_errors = 0
    for f in tf_files:
        errors = check_file(f)
        rel = f.relative_to(root) if f.is_relative_to(root) else f
        if errors:
            total_errors += len(errors)
            print(f"FAIL {rel}")
            for e in errors:
                print(f"  - {e}")
        else:
            print(f"ok   {rel}")

    print(f"\n{len(tf_files)} files checked, {total_errors} structural issue(s) found.")
    return 1 if total_errors else 0


if __name__ == "__main__":
    sys.exit(main())
