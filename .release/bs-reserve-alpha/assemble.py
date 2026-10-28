"""Assemble the verified alpha archive from transport-sized Git blobs."""
from pathlib import Path
import hashlib
import json
import zipfile

root = Path.cwd()
manifest = json.loads((root / ".release/bs-reserve-alpha/manifest.json").read_text())
target = root / manifest["path"]
if target.is_file() and hashlib.sha256(target.read_bytes()).hexdigest() == manifest["sha256"]:
    print("Verified archive already present:", target.name)
    raise SystemExit(0)

target.parent.mkdir(parents=True, exist_ok=True)
temporary = target.with_suffix(target.suffix + ".tmp")
digest = hashlib.sha256()
total = 0
try:
    with temporary.open("wb") as out:
        for part in manifest["parts"]:
            p = Path(part["path"])
            assert not p.is_absolute() and ".." not in p.parts
            data = (root / p).read_bytes()
            assert len(data) == part["size"], p
            assert hashlib.sha256(data).hexdigest() == part["sha256"], p
            out.write(data)
            digest.update(data)
            total += len(data)
    assert total == manifest["bytes"]
    assert digest.hexdigest() == manifest["sha256"]
    with zipfile.ZipFile(temporary) as archive:
        assert archive.testzip() is None
        assert not any("/Data/" in name for name in archive.namelist())
    temporary.replace(target)
finally:
    temporary.unlink(missing_ok=True)
print("Verified alpha archive:", target.name, total, digest.hexdigest())
