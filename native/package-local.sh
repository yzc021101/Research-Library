#!/bin/sh
set -eu
LAB_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
STAGE="$LAB_DIR/tmp/research_library-installer"
mkdir -p "$STAGE" "$LAB_DIR/dist"
"$LAB_DIR/native/build.sh"
ditto "$LAB_DIR/投研纵览.app" "$STAGE/投研纵览.app"
ln -sfn /Applications "$STAGE/Applications"
cp "$LAB_DIR/native/安装说明.txt" "$STAGE/安装说明.txt"
VERSION=$(/usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' "$STAGE/投研纵览.app/Contents/Info.plist")
IMAGE="$LAB_DIR/dist/research_library-$VERSION-arm64-local.dmg"
hdiutil create -volname '投研纵览 本机试用版' -srcfolder "$STAGE" -ov -format UDZO "$IMAGE"
hdiutil verify "$IMAGE"
