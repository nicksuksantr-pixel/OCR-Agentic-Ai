# build.ps1 — one-command release build (rule #14/#15: regen CODEMAP first,
# output named OCR-Agentic-Ai_Setup_vX.Y.Z.exe)
#
#   powershell -ExecutionPolicy Bypass -File build\build.ps1
#
# Steps: icon → CODEMAP → PyInstaller (folder mode) → stage bundled Tesseract
# → Inno Setup installer → SHA-256 sidecar (verified by the auto-updater).
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$py = Join-Path $root ".venv\Scripts\python.exe"
$pyinstaller = Join-Path $root ".venv\Scripts\pyinstaller.exe"
$iscc = "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
$tesseractSrc = "C:\Program Files\Tesseract-OCR"

# Version straight from the app — single source of truth.
$appPy = Get-Content (Join-Path $root "src\app\app.py") -Raw
if ($appPy -notmatch 'APP_VERSION = "v(\d+\.\d+\.\d+)"') { throw "APP_VERSION not found" }
$version = $Matches[1]
Write-Host "=== Building OCR-Agentic-Ai v$version ===" -ForegroundColor Cyan

# Windows version-info resource for the exe (pro touch: Properties > Details)
@"
VSVersionInfo(
  ffi=FixedFileInfo(filevers=($($version.Replace('.', ', ')), 0), prodvers=($($version.Replace('.', ', ')), 0)),
  kids=[StringFileInfo([StringTable('040904B0', [
    StringStruct('CompanyName', 'Nick (Suksan Trisaranasart)'),
    StringStruct('FileDescription', 'OCR Agentic AI - the eyes of Open-Claw'),
    StringStruct('FileVersion', '$version'),
    StringStruct('ProductName', 'OCR Agentic AI'),
    StringStruct('ProductVersion', '$version')])]),
  VarFileInfo([VarStruct('Translation', [1033, 1200])])]
)
"@ | Set-Content (Join-Path $PSScriptRoot "_version_info.txt") -Encoding ascii

Write-Host "[1/6] App icon + mascot/wizard art..." -ForegroundColor Yellow
& $py (Join-Path $PSScriptRoot "make_icon.py")
& $py (Join-Path $PSScriptRoot "make_mascot.py")

Write-Host "[2/6] CODEMAP layer B (rule #15)..." -ForegroundColor Yellow
& $py (Join-Path $root "gen_codemap.py")

Write-Host "[3/6] PyInstaller (folder mode)..." -ForegroundColor Yellow
& $pyinstaller (Join-Path $PSScriptRoot "OCR-Agentic-Ai.spec") --noconfirm --clean `
    --distpath (Join-Path $root "dist") --workpath (Join-Path $PSScriptRoot "_work")
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }

Write-Host "[4/6] Staging bundled Tesseract (exe + DLLs + tha/eng/osd)..." -ForegroundColor Yellow
$stage = Join-Path $PSScriptRoot "stage\tesseract"
if (Test-Path $stage) { Remove-Item $stage -Recurse -Force }
New-Item -ItemType Directory -Force "$stage\tessdata\configs" | Out-Null
Copy-Item "$tesseractSrc\tesseract.exe" $stage
Copy-Item "$tesseractSrc\*.dll" $stage
foreach ($m in "eng", "tha", "osd") {
    # Language models live in the project's data\tessdata (winget's Tesseract
    # ships English-only); fall back to the system tessdata if needed.
    $local = Join-Path $root "data\tessdata\$m.traineddata"
    $system = "$tesseractSrc\tessdata\$m.traineddata"
    if (Test-Path $local) { Copy-Item $local "$stage\tessdata" }
    elseif (Test-Path $system) { Copy-Item $system "$stage\tessdata" }
    else { throw "$m.traineddata not found in project data\tessdata or system tessdata" }
}
if (Test-Path "$tesseractSrc\tessdata\configs") {
    Copy-Item "$tesseractSrc\tessdata\configs\*" "$stage\tessdata\configs"
}

Write-Host "[5/6] Inno Setup installer..." -ForegroundColor Yellow
& $iscc /Qp "/DMyAppVersion=$version" (Join-Path $PSScriptRoot "installer.iss")
if ($LASTEXITCODE -ne 0) { throw "ISCC failed" }

Write-Host "[6/6] SHA-256 sidecar for the auto-updater..." -ForegroundColor Yellow
$setup = Join-Path $root "dist\installer\OCR-Agentic-Ai_Setup_v$version.exe"
$hash = (Get-FileHash $setup -Algorithm SHA256).Hash.ToLower()
"$hash  OCR-Agentic-Ai_Setup_v$version.exe" |
    Set-Content "$setup.sha256" -Encoding ascii

$size = [math]::Round((Get-Item $setup).Length / 1MB, 1)
Write-Host "=== DONE: $setup ($size MB) ===" -ForegroundColor Green
Write-Host "Release to GitHub: upload BOTH the .exe and the .sha256 file, tag v$version"
