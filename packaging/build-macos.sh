#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT"
PYTHON=${RL_PYTHON:-"$ROOT/.venv/bin/python"}
export RL_SOURCE="$ROOT/src" PYINSTALLER_CONFIG_DIR="$ROOT/build/pyinstaller-cache"
mkdir -p "$ROOT/build" "$ROOT/dist"
"$PYTHON" -m PyInstaller --noconfirm --distpath "$ROOT/build/engine-dist" --workpath "$ROOT/build/engine-work" packaging/runtime.spec
APP="$ROOT/build/mac-stage/投研纵览.app"
REBUILD_ICON=0 RESEARCH_LIBRARY_APP_OUTPUT="$APP" native/build.sh
mkdir -p "$APP/Contents/Resources/engine"
ditto "$ROOT/build/engine-dist/research-library-engine" "$APP/Contents/Resources/engine"
cp packaging/components-macos-arm64.json "$APP/Contents/Resources/engine/components.json"
ditto THIRD_PARTY_NOTICES "$APP/Contents/Resources/ThirdPartyNotices"
cp LICENSE COPYRIGHT PLATFORM-LINKING-PERMISSION.txt "$APP/Contents/Resources/"
/usr/libexec/PlistBuddy -c 'Delete :ResearchLibraryDataRoot' "$APP/Contents/Info.plist"
/usr/libexec/PlistBuddy -c 'Add :ResearchLibraryDistribution bool true' "$APP/Contents/Info.plist"
codesign --force --deep --sign - "$APP"
codesign --verify --deep --strict "$APP"
ln -sfn /Applications "$ROOT/build/mac-stage/Applications"
cp README.md "$ROOT/build/mac-stage/安装说明.md"
hdiutil create -volname '投研纵览 0.6.10' -srcfolder "$ROOT/build/mac-stage" -ov -format UDZO -imagekey zlib-level=9 "$ROOT/dist/research_library-macos-arm64.dmg"
hdiutil verify "$ROOT/dist/research_library-macos-arm64.dmg"
