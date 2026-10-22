param([string]$Python="python",[string]$DotNet="dotnet",[string]$InnoCompiler="ISCC.exe")
$ErrorActionPreference='Stop'
$Root=Split-Path -Parent $PSScriptRoot
$Build=Join-Path $Root 'build'
$Release=Join-Path $Build 'release/research_library'
if(Test-Path $Release){Remove-Item $Release -Recurse -Force}
New-Item -ItemType Directory -Force $Build,$Release,"$Root/dist"|Out-Null
$env:RL_SOURCE="$Root/windows/backend"
$env:PYINSTALLER_CONFIG_DIR="$Build/pyinstaller-cache"
$env:DOTNET_CLI_TELEMETRY_OPTOUT='1'
$ErrorActionPreference='Continue'
& $Python -m PyInstaller --noconfirm --distpath "$Build/engine-dist" --workpath "$Build/engine-work" "$PSScriptRoot/runtime.spec"
if($LASTEXITCODE -ne 0){throw 'Engine build failed'}
& $DotNet publish "$Root/windows/frontend/ResearchLibrary.Windows.csproj" -c Release -r win-x64 -p:Platform=x64 -p:DebugType=None -p:DebugSymbols=false "-p:PathMap=$Root=/src" --self-contained true -o $Release --nologo
if($LASTEXITCODE -ne 0){throw 'Frontend build failed'}
$ErrorActionPreference='Stop'
Copy-Item "$Build/engine-dist/research-library-engine" "$Release/engine" -Recurse -Force
Copy-Item "$PSScriptRoot/components-windows-x64.json" "$Release/engine/components.json" -Force
Copy-Item "$Root/THIRD_PARTY_NOTICES" "$Release/ThirdPartyNotices" -Recurse -Force
Copy-Item "$Root/LICENSE","$Root/COPYRIGHT","$Root/PLATFORM-LINKING-PERMISSION.txt","$Root/README.md" $Release -Force
# Inactive ARM host resources are not part of the x64 application.
Remove-Item "$Release/Microsoft.Windows.Workloads.Resources_ec.dll" -ErrorAction SilentlyContinue
Get-ChildItem $Release -Filter *.pdb -Recurse|Remove-Item -Force
[IO.File]::WriteAllText("$Release/distribution.json",'{"version":"0.6.10"}')
& $Python -c "import json,pathlib;p=pathlib.Path(r'$Release');(p/'distribution-files.json').write_text(json.dumps(sorted(f.relative_to(p).as_posix() for f in p.rglob('*') if f.is_file() and f.name!='distribution-files.json')))"
& $Python "$PSScriptRoot/inspect-pe.py" $Release "$Build/architecture.json"
if($LASTEXITCODE -ne 0){throw 'Architecture mismatch'}
& $Python -c "import shutil;shutil.make_archive(r'$Root/dist/research_library-windows-x64','zip',r'$Build/release')"
if($LASTEXITCODE -ne 0){throw 'Archive build failed'}

& $InnoCompiler "$PSScriptRoot/windows-installer.iss"
if($LASTEXITCODE -ne 0){throw "Installer build failed"}
