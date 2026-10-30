#!/usr/bin/env python3
"""Scan tracked public files for recognizable Telegram/GitHub credentials.

Only filenames/line numbers are printed, never matched secret values.
This detects known patterns; it cannot certify absence of arbitrary secrets.
"""
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parent.parent
PATTERNS = (
    re.compile(rb"\b\d{5,16}:[A-Za-z0-9_-]{30,}\b"),
    re.compile(rb"\bgh[pousr]_[A-Za-z0-9]{30,}\b"),
    re.compile(rb"\bgithub_pat_[A-Za-z0-9_]{40,}\b"),
)


def main():
    paths = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).decode().split("\0")
    findings, count = [], 0
    for name in filter(None, paths):
        path = ROOT / name
        if not path.is_file():
            continue
        if path.name.startswith((".dev.vars", ".env")) and not path.name.endswith(".example"):
            findings.append((name, 0))
            continue
        data = path.read_bytes()
        for pattern in PATTERNS:
            for match in pattern.finditer(data):
                findings.append((name, data[:match.start()].count(b"\n") + 1))
        count += 1
    if findings:
        for name, line in sorted(set(findings)):
            print(f"Potential credential: {name}:{line}; value withheld")
        raise SystemExit(1)
    print(f"Scanned {count} tracked files: no recognized Telegram/GitHub credential patterns")


if __name__ == "__main__":
    main()
