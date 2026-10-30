#!/usr/bin/env python3
"""Pin bot downloads to a committed Git revision and record their SHA-256/size.

Run AFTER the release binaries have been committed, then commit the catalog.
No credentials or third-party Python packages are required.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parent.parent
CATALOG = ROOT / "automation/sidj_projects.json"


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, stderr=subprocess.DEVNULL)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ref", default="HEAD", help="Commit that already contains the release files")
    parser.add_argument("--check", action="store_true", help="Read-only verification, no catalog writes")
    args = parser.parse_args()
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    ref = catalog.get("files_ref") if args.check else git("rev-parse", "--verify", args.ref + "^{commit}").decode().strip()
    if not re.fullmatch(r"[0-9a-f]{40}", ref or ""):
        raise SystemExit("Catalog has no valid files_ref")
    entries = 0
    for project in catalog["projects"]:
        for entry in project["downloads"]:
            path = entry["path"]
            if not re.fullmatch(r"(?:apps|downloads)/[A-Za-z0-9._/-]+", path) or any(
                part in ("", ".", "..") for part in path.split("/")
            ):
                raise SystemExit("Invalid catalog path")
            mode = git("ls-tree", ref, "--", path).decode().split(" ", 1)[0]
            if mode not in ("100644", "100755"):
                raise SystemExit("Catalog path must reference a regular Git file: " + path)
            data = git("show", ref + ":" + path)
            digest = hashlib.sha256(data).hexdigest()
            if args.check:
                if entry.get("sha256") != digest or entry.get("size_bytes") != len(data):
                    raise SystemExit("Catalog checksum or size mismatch: " + path)
            else:
                entry.update(sha256=digest, size_bytes=len(data))
            if path.endswith((".zip", ".tar.gz")):
                expected = git("show", ref + ":" + path + ".sha256").decode().split()[0]
                if digest != expected.lower():
                    raise SystemExit("Archive sidecar checksum mismatch: " + path)
            entries += 1
    catalog["files_ref"] = ref
    if not args.check:
        CATALOG.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Verified {entries} downloads at {ref[:12]}; catalog {'unchanged' if args.check else 'updated'}")


if __name__ == "__main__":
    main()
