#!/bin/sh
set -eu
cd "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
bundle=$(pwd)
restic_binary=bin/restic
output=B_S_Reserve
if [ "$(uname -s)" = Darwin ]; then
    restic_binary=B_S_Reserve.app/Contents/MacOS/bin/restic
    output=B_S_Reserve.app/Contents/MacOS/B_S_Reserve
    restic_hash=$(shasum -a 256 "$restic_binary" | cut -d ' ' -f 1)
else
    restic_hash=$(sha256sum "$restic_binary" | cut -d ' ' -f 1)
fi
cd src
BS_TEST_RESTIC="$bundle/$restic_binary" go test ./...
CGO_ENABLED=0 go build -buildvcs=false -trimpath -ldflags="-s -w -X main.ResticHash=$restic_hash" -o "../$output" .
printf '%s\n' 'Build complete. Recalculate SHA256SUMS.txt after rebuilding.'
