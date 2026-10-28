@echo off
setlocal
cd /d "%~dp0src"
where go >nul 2>nul
if errorlevel 1 (
  echo Install Go 1.27.3 from https://go.dev/dl/
  pause
  exit /b 1
)
set GOOS=windows
set GOARCH=amd64
set CGO_ENABLED=0
go test ./...
if errorlevel 1 exit /b 1
go build -buildvcs=false -trimpath -ldflags="-H=windowsgui -s -w -X main.ResticHash=b0dd1fd21eea5d8fe1325f55f7118213c21f36de8a261e04c0624a5ab9fd7830" -o "..\B_S_Reserve.exe" .
if errorlevel 1 exit /b 1
echo Build complete. Recalculate SHA256SUMS.txt after rebuilding.
pause
