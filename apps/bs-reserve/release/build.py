"""Build platform releases from the shared source and pinned, verified components.

Only the public alpha.1 package supplies the unchanged collectors/examples and
licenses. Executables and source are replaced; no working Data directory is used.
Requires Python 3.11+ and the exact Go version from config.json on PATH.
"""
from __future__ import annotations

import argparse
import bz2
import gzip
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import plistlib
import shutil
import stat
import subprocess
import tarfile
import tempfile
import time
import urllib.request
import zipfile

PROJECT = Path(__file__).resolve().parents[1]
REPO = PROJECT.parents[1]
SOURCE = PROJECT / "source"
CONFIG = json.loads((PROJECT / "release/config.json").read_text(encoding="utf-8"))
TARGETS = {entry["target"]: entry for entry in CONFIG["targets"]}
EPOCH = 1793368800  # 2026-10-30 14:00 UTC; fixed archive metadata.
ROOT_NAME = "BS_Reserve_Alpha"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def download(url: str, expected: str, cache: Path) -> bytes:
    cache.parent.mkdir(parents=True, exist_ok=True)
    if cache.is_file() and digest(cache.read_bytes()) == expected:
        return cache.read_bytes()
    for attempt in range(3):
        try:
            with urllib.request.urlopen(url, timeout=120) as response:
                data = response.read()
            if digest(data) != expected:
                raise ValueError(f"SHA-256 mismatch for {url}")
            cache.write_bytes(data)
            return data
        except Exception:
            if attempt == 2:
                raise
            time.sleep(2)
    raise AssertionError("unreachable")


def restic_binary(target: str, cache: Path) -> bytes:
    entry = TARGETS[target]
    data = download(
        f"https://github.com/restic/restic/releases/download/v{CONFIG['restic_version']}/{entry['restic_asset']}",
        entry["restic_archive_sha256"], cache / entry["restic_asset"],
    )
    if entry["os"] == "windows":
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            names = [name for name in archive.namelist() if name.endswith(".exe")]
            if len(names) != 1:
                raise ValueError("unexpected restic ZIP contents")
            binary = archive.read(names[0])
    else:
        binary = bz2.decompress(data)
    if digest(binary) != entry["restic_binary_sha256"]:
        raise ValueError("unpacked restic SHA-256 mismatch")
    return binary


def check_go() -> None:
    version = subprocess.check_output(["go", "version"], text=True).split()[2]
    if version != CONFIG["go_version"]:
        raise RuntimeError(f"need {CONFIG['go_version']}, found {version}")


def seed_bundle(bundle: Path) -> None:
    baseline = REPO / CONFIG["baseline_path"]
    data = baseline.read_bytes()
    if digest(data) != CONFIG["baseline_sha256"]:
        raise ValueError("alpha.1 baseline SHA-256 mismatch")
    allowed = {"collectors", "third-party", "licenses", "examples"}
    files = {"COLLECTORS_SHA256.json", "build_collectors.py", "LICENSE.txt"}
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        for item in archive.infolist():
            p = PurePosixPath(item.filename)
            if p.is_absolute() or ".." in p.parts or not p.parts or p.parts[0] != ROOT_NAME:
                raise ValueError(f"invalid baseline path {p}")
            relative = PurePosixPath(*p.parts[1:])
            if item.is_dir() or not relative.parts:
                continue
            if relative.parts[0] not in allowed and str(relative) not in files:
                continue
            if stat.S_ISLNK(item.external_attr >> 16):
                raise ValueError("baseline symlink rejected")
            dest = bundle.joinpath(*relative.parts)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(archive.read(item))
    for source in sorted(SOURCE.rglob("*")):
        if source.is_symlink():
            raise ValueError("source symlink rejected")
        if source.is_file():
            dest = bundle / source.relative_to(SOURCE)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, dest)


def stage_bundle(target: str, work: Path, cache: Path) -> tuple[Path, Path, Path]:
    entry = TARGETS[target]
    bundle = work / ROOT_NAME
    bundle.mkdir(parents=True, exist_ok=False)
    seed_bundle(bundle)
    is_windows = entry["os"] == "windows"
    is_mac = entry["os"] == "darwin"
    runtime_dir = bundle / "B_S_Reserve.app/Contents/MacOS" if is_mac else bundle
    runtime_dir.mkdir(parents=True, exist_ok=True)
    binary = runtime_dir / ("B_S_Reserve.exe" if is_windows else "B_S_Reserve")
    restic = runtime_dir / "bin" / ("restic.exe" if is_windows else "restic")
    restic.parent.mkdir(parents=True, exist_ok=True)
    restic.write_bytes(restic_binary(target, cache))
    restic.chmod(0o755)
    flags = "-s -w -X main.ResticHash=" + entry["restic_binary_sha256"]
    if is_windows:
        flags = "-H=windowsgui " + flags
    env = os.environ.copy()
    env.update(GOOS=entry["os"], GOARCH=entry["arch"], CGO_ENABLED="0", GOTOOLCHAIN="local")
    subprocess.run(["go", "build", "-buildvcs=false", "-trimpath", "-ldflags=" + flags,
                    "-o", str(binary), "."], cwd=SOURCE / "src", env=env, check=True)
    binary.chmod(0o755)
    if is_mac:
        shutil.copytree(bundle / "examples", runtime_dir / "examples")
        plist = {
            "CFBundleExecutable": "B_S_Reserve", "CFBundleIdentifier": "tech.berserkersidj.reserve.alpha",
            "CFBundleDisplayName": "B/S Reserve Alpha", "CFBundleName": "B/S Reserve Alpha",
            "CFBundlePackageType": "APPL", "CFBundleVersion": CONFIG["build"],
            "CFBundleShortVersionString": "0.1.0", "LSMinimumSystemVersion": "13.0",
            "NSHighResolutionCapable": True, "LSUIElement": True,
        }
        (bundle / "B_S_Reserve.app/Contents/Info.plist").write_bytes(plistlib.dumps(plist, sort_keys=True))
        (bundle / "B_S_Reserve.app/Contents/PkgInfo").write_bytes(b"APPL????")
    for name in ["START.cmd"] if not is_windows else ["START.sh"]:
        (bundle / name).unlink(missing_ok=True)
    if is_mac:
        (bundle / "START.sh").unlink(missing_ok=True)
    for path in bundle.rglob("*.sh"):
        path.chmod(0o755)
    components = json.loads((bundle / "COMPONENTS.json").read_text(encoding="utf-8"))
    components["platform"] = target
    components["version"] = CONFIG["version"]
    components["build"] = CONFIG["build"]
    components["components"] = [c for c in components["components"] if c["name"] != "restic"] + [{
        "name": "restic", "version": CONFIG["restic_version"], "platform": target,
        "source": f"https://github.com/restic/restic/releases/tag/v{CONFIG['restic_version']}",
        "archive_sha256": entry["restic_archive_sha256"], "binary_sha256": entry["restic_binary_sha256"],
        "modified": False, "license": "BSD-2-Clause",
    }]
    (bundle / "COMPONENTS.json").write_text(json.dumps(components, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    sums = []
    for path in sorted(bundle.rglob("*")):
        if path.is_file() and path.name != "SHA256SUMS.txt":
            sums.append(f"{digest(path.read_bytes())}  {path.relative_to(bundle).as_posix()}")
    (bundle / "SHA256SUMS.txt").write_text("\n".join(sums) + "\n", encoding="utf-8", newline="\n")
    return bundle, binary, restic


def executable(relative: Path) -> bool:
    return relative.name in {"B_S_Reserve", "B_S_Reserve.exe", "restic", "restic.exe"} or relative.suffix in {".sh", ".command"}


def archive_bundle(bundle: Path, output: Path) -> None:
    for path in bundle.rglob("*"):
        if path.is_symlink() or "Data" in path.relative_to(bundle).parts:
            raise ValueError("working data or symlink found in release")
    if output.suffix == ".zip":
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for path in sorted(bundle.rglob("*")):
                if not path.is_file():
                    continue
                relative = path.relative_to(bundle)
                info = zipfile.ZipInfo(ROOT_NAME + "/" + relative.as_posix(), (2026, 10, 30, 12, 0, 0))
                info.create_system = 3
                info.external_attr = (stat.S_IFREG | (0o755 if executable(relative) else 0o644)) << 16
                info.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(info, path.read_bytes(), compresslevel=9)
        with zipfile.ZipFile(output) as archive:
            if archive.testzip() is not None:
                raise ValueError("release ZIP integrity failure")
    else:
        with output.open("wb") as stream, gzip.GzipFile(filename="", mode="wb", fileobj=stream, mtime=0, compresslevel=9) as zipped:
            with tarfile.open(mode="w", fileobj=zipped, format=tarfile.PAX_FORMAT) as archive:
                for path in sorted(bundle.rglob("*")):
                    if not path.is_file():
                        continue
                    relative = path.relative_to(bundle)
                    data = path.read_bytes()
                    info = tarfile.TarInfo(ROOT_NAME + "/" + relative.as_posix())
                    info.size = len(data)
                    info.mtime = EPOCH
                    info.mode = 0o755 if executable(relative) else 0o644
                    archive.addfile(info, io.BytesIO(data))


def release_all(output: Path, cache: Path) -> dict:
    check_go()
    output.mkdir(parents=True, exist_ok=True)
    result = {"version": CONFIG["version"], "build": CONFIG["build"], "date": "2026-10-30", "targets": []}
    for target, entry in TARGETS.items():
        with tempfile.TemporaryDirectory(prefix="bs-reserve-build-") as temporary:
            bundle, binary, restic = stage_bundle(target, Path(temporary), cache)
            name = f"BS_Reserve_{CONFIG['version']}_build{CONFIG['build']}_{entry['file_suffix']}"
            path = output / name
            archive_bundle(bundle, path)
            item = {key: entry[key] for key in ["target", "os", "arch", "label", "requirements"]}
            item.update(name=name, bytes=path.stat().st_size, sha256=digest(path.read_bytes()),
                        app_sha256=digest(binary.read_bytes()), restic_sha256=digest(restic.read_bytes()))
            (output / (name + ".sha256")).write_text(f"{item['sha256']}  {name}\n", encoding="utf-8", newline="\n")
            result["targets"].append(item)
            print("Built", target, name, item["bytes"], item["sha256"], flush=True)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=REPO / "downloads")
    parser.add_argument("--cache", type=Path, default=Path(tempfile.gettempdir()) / "bs-reserve-restic-cache")
    args = parser.parse_args()
    manifest = release_all(args.output.resolve(), args.cache.resolve())
    dest = PROJECT / "releases" / (CONFIG["version"] + ".json")
    dest.parent.mkdir(exist_ok=True)
    dest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
