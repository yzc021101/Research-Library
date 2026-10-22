#!/bin/sh
set -eu
LAB_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
APP_DIR="${RESEARCH_LIBRARY_APP_OUTPUT:-$LAB_DIR/投研纵览.app}"
mkdir -p "$APP_DIR/Contents/MacOS" "$APP_DIR/Contents/Resources" "$LAB_DIR/cache/swift" "$LAB_DIR/tmp"
export TMPDIR="$LAB_DIR/tmp"
export CLANG_MODULE_CACHE_PATH="$LAB_DIR/cache/swift"
if [ "${REBUILD_ICON:-1}" = "1" ]; then
  "$LAB_DIR/native/build-icon.sh"
else
  # UI-only builds may reuse the already exported icon without regenerating it.
  test -s "$LAB_DIR/assets/AppIcon.icns"
fi
cp "$LAB_DIR/assets/AppIcon.icns" "$APP_DIR/Contents/Resources/AppIcon.icns"
cp "$LAB_DIR/assets/MenuBarTemplate.png" "$APP_DIR/Contents/Resources/MenuBarTemplate.png"
swiftc -swift-version 5 -parse-as-library -O \
  -module-cache-path "$LAB_DIR/cache/swift" \
  -target arm64-apple-macosx14.0 \
  "$LAB_DIR/native/ResearchLibrary.swift" "$LAB_DIR/native/MCPConfiguration.swift" "$LAB_DIR/native/MCPConnectionView.swift" "$LAB_DIR/native/MCPClientGuide.swift" "$LAB_DIR/native/OnboardingView.swift" "$LAB_DIR/native/ComponentSettings.swift" "$LAB_DIR/native/StorageSettings.swift" "$LAB_DIR/native/UpdateSettings.swift" "$LAB_DIR/native/TableContentView.swift" \
  -o "$APP_DIR/Contents/MacOS/research_library" \
  -framework SwiftUI -framework AppKit -framework ServiceManagement
cat > "$APP_DIR/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>CFBundleIdentifier</key><string>local.research.library.lab</string>
<key>CFBundleName</key><string>投研纵览</string>
<key>CFBundleDisplayName</key><string>投研纵览</string>
<key>CFBundleExecutable</key><string>research_library</string>
<key>CFBundlePackageType</key><string>APPL</string>
<key>CFBundleShortVersionString</key><string>0.6.7</string>
<key>CFBundleVersion</key><string>31</string>
<key>CFBundleIconFile</key><string>AppIcon.icns</string>
<key>LSMinimumSystemVersion</key><string>14.0</string>
<key>LSUIElement</key><false/>
<key>NSHighResolutionCapable</key><true/>
<key>NSAppTransportSecurity</key><dict><key>NSAllowsLocalNetworking</key><true/></dict>
<key>NSDesktopFolderUsageDescription</key><string>读取你选择的资料文件夹中的报告、文本、演示文稿和表格，用于本地检索。</string>
<key>NSDocumentsFolderUsageDescription</key><string>读取你选择的资料文件夹中的报告、文本、演示文稿和表格，用于本地检索。</string>
<key>NSDownloadsFolderUsageDescription</key><string>读取你选择的资料文件夹中的报告、文本、演示文稿和表格，用于本地检索。</string>
</dict></plist>
PLIST
/usr/libexec/PlistBuddy -c "Add :ResearchLibraryDataRoot string $LAB_DIR" "$APP_DIR/Contents/Info.plist"
codesign --force --sign - "$APP_DIR"
printf 'Built: %s\n' "$APP_DIR"
