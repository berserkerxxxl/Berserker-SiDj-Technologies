"""Run real tests and the packaged executable on its native OS/architecture."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import queue
import re
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.request
import zipfile

import build


def smoke(binary: Path, target: str, work: Path) -> None:
    root = work / "Тест архива с пробелами" / "Data"
    process = subprocess.Popen([str(binary), "--no-browser", "--data", str(root)],
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True, encoding="utf-8")
    lines: queue.Queue[str] = queue.Queue()
    threading.Thread(target=lambda: lines.put(process.stdout.readline()), daemon=True).start()
    try:
        url = lines.get(timeout=30).strip()
        if not re.fullmatch(r"http://127\.0\.0\.1:\d+", url):
            raise RuntimeError("program did not publish a loopback URL: " + repr(url))
        html = urllib.request.urlopen(url, timeout=10).read().decode("utf-8")
        token = re.search(r"const TOKEN='([a-f0-9]+)'", html).group(1)
        if build.CONFIG["version"] not in html:
            raise AssertionError("alpha banner missing")

        def api(path: str, payload: dict | None = None):
            request = urllib.request.Request(url + path, headers={"X-BS-Token": token})
            if payload is not None:
                request.data = json.dumps(payload).encode("utf-8")
                request.add_header("Content-Type", "application/json")
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.load(response)

        def action(name: str, **fields):
            api("/api/action", {"Action": name, **fields})
            until = time.monotonic() + 180
            while time.monotonic() < until:
                job = api("/api/job")
                if not job["Running"]:
                    if job["Error"]:
                        raise AssertionError(name + ": " + job["Error"])
                    return job["Result"]
                time.sleep(0.1)
            raise TimeoutError(name)

        state = api("/api/state")
        entry = build.TARGETS[target]
        assert state["OS"] == entry["os"] and state["Arch"] == entry["arch"]
        assert state["Version"] == build.CONFIG["version"] and state["Build"] == build.CONFIG["build"]
        assert state["Sources"] == []
        try:
            urllib.request.urlopen(url + "/api/state", timeout=10)
            raise AssertionError("API accepted unauthenticated request")
        except urllib.error.HTTPError as error:
            assert error.code == 403
        action("demo")
        state = api("/api/state")
        assert len(state["Sources"]) == 3 and len(state["Conversations"]) == 1
        assert len(state["Conversations"][0]["Revisions"]) == 2 and len(state["Notes"]) == 1
        action("demo")
        assert len(api("/api/state")["Sources"]) == 3
        action("note", Kind="instructions", Text="Synthetic cross-platform release test")
        assert len(api("/api/state")["Notes"]) == 2
        assert not action("verify")["Errors"]
        repo = work / "Пробная копия" / "repository"
        credentials = {"Repository": str(repo), "Password": "Synthetic release test passphrase 2026!"}
        action("init", **credentials, Confirm=credentials["Password"])
        action("backup", **credentials)
        action("check-full", **credentials)
        snapshots = action("snapshots", **credentials)
        assert len(snapshots) == 1
        restored = action("restore", **credentials, Snapshot=snapshots[0]["ID"], Target=str(work / "Восстановлено"))
        assert restored["Checked"] > 0 and not restored["Errors"]
        migration = action("migration", Target=str(work / "Пакет на другом диске"))
        assert Path(migration["Path"]).parent == work / "Пакет на другом диске"
        package = Path(migration["Path"]).read_bytes()
        assert hashlib.sha256(package).hexdigest() == migration["SHA256"]
        with zipfile.ZipFile(io.BytesIO(package)) as archive:
            assert archive.testzip() is None
            assert any(name.endswith("index.html") for name in archive.namelist())
        action("shutdown")
        process.wait(timeout=20)
        assert process.returncode == 0
        print("PASS packaged executable:", target, "empty archive, token boundary, demo/dedup, notes, SHA-256, encryption, full check, restore, offline migration", flush=True)
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)
        error = process.stderr.read()
        if error:
            print(error)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("target", choices=build.TARGETS)
    parser.add_argument("--race", action="store_true")
    parser.add_argument("--cache", type=Path, default=Path(tempfile.gettempdir()) / "bs-reserve-restic-cache")
    args = parser.parse_args()
    expected = build.TARGETS[args.target]
    goos = {"Darwin": "darwin", "Linux": "linux", "Windows": "windows"}[platform.system()]
    machine = {"x86_64": "amd64", "AMD64": "amd64", "aarch64": "arm64", "arm64": "arm64"}[platform.machine()]
    assert goos == expected["os"] and machine == expected["arch"], "native test on wrong runner"
    build.check_go()
    with tempfile.TemporaryDirectory(prefix="bs-reserve-native-") as temp:
        work = Path(temp)
        _, binary, restic = build.stage_bundle(args.target, work, args.cache.resolve())
        env = os.environ.copy()
        env["BS_TEST_RESTIC"] = str(restic)
        env["GOTOOLCHAIN"] = "local"
        if args.target == "windows_amd64":
            env["BS_TEST_SCHEDULER"] = "1"
        command = ["go", "test", "-count=1", "-v"]
        if args.race:
            command.append("-race")
        subprocess.run(command + ["./..."], cwd=build.SOURCE / "src", env=env, check=True)
        subprocess.run(["go", "vet", "./..."], cwd=build.SOURCE / "src", env=env, check=True)
        smoke(binary, args.target, work)


if __name__ == "__main__":
    main()
