#!/bin/sh
set -eu
LAB_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
ICONSET="$LAB_DIR/tmp/AppIcon.iconset"
mkdir -p "$ICONSET" "$LAB_DIR/cache/swift"
swiftc -module-cache-path "$LAB_DIR/cache/swift" "$LAB_DIR/native/ExportAppIcon.swift" -o "$LAB_DIR/tmp/export-app-icon"
"$LAB_DIR/tmp/export-app-icon" "$LAB_DIR/assets/app-icon-v4-transparent.png" "$LAB_DIR/assets/app-icon-macos.png"
for size in 16 32 128 256 512; do
    sips -z "$size" "$size" "$LAB_DIR/assets/app-icon-macos.png" --out "$ICONSET/icon_${size}x${size}.png" >/dev/null
    retina=$((size * 2))
    sips -z "$retina" "$retina" "$LAB_DIR/assets/app-icon-macos.png" --out "$ICONSET/icon_${size}x${size}@2x.png" >/dev/null
done
iconutil -c icns "$ICONSET" -o "$LAB_DIR/assets/AppIcon.icns"
