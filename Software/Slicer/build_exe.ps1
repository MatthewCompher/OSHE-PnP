# Builds dist\pnpslice.exe: the slicer as one Windows program (no Python needed to run it).
# Run in PowerShell from this folder:   powershell -ExecutionPolicy Bypass -File .\build_exe.ps1
# Needs Python 3.10+ on the PATH. Makes a private .build-venv here (PySide6 + PyInstaller, ~300 MB),
# so nothing is installed into your normal Python. The .exe is NOT committed to git (too big):
# publish it as a GitHub Release download instead, rebuilt from this script.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
if (-not (Test-Path .build-venv)) { python -m venv .build-venv }
$py = Join-Path $PSScriptRoot ".build-venv\Scripts\python.exe"
& $py -m pip install --quiet --upgrade pip
# exact versions the released pnpslice.exe was built and checked with (2026-11-18)
& $py -m pip install --quiet "PySide6-Essentials==6.12.0" "pyinstaller==6.22.3"
& $py -m PyInstaller --noconfirm --clean --onefile --windowed --name pnpslice --paths src pnpslice_app.py
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }
Write-Host "Built $PSScriptRoot\dist\pnpslice.exe"
