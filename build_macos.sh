#!/bin/bash
# Build script for MTG Budget Builder on macOS.
# Run from the project root: bash build_macos.sh

set -e

echo "=== MTG Budget Builder — macOS Build ==="

# 1. Create virtual environment if it doesn't exist
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
fi

# 2. Install dependencies
echo "Installing dependencies..."
.venv/bin/pip install --quiet -r requirements.txt
.venv/bin/pip install --quiet pyinstaller

# 3. Generate icon.icns from assets/icon_512.png
echo "Generating icon.icns..."
ICONSET="assets/icon.iconset"
mkdir -p "$ICONSET"
sips -z 16 16     assets/icon_512.png --out "$ICONSET/icon_16x16.png"    > /dev/null
sips -z 32 32     assets/icon_512.png --out "$ICONSET/icon_16x16@2x.png" > /dev/null
sips -z 32 32     assets/icon_512.png --out "$ICONSET/icon_32x32.png"    > /dev/null
sips -z 64 64     assets/icon_512.png --out "$ICONSET/icon_32x32@2x.png" > /dev/null
sips -z 128 128   assets/icon_512.png --out "$ICONSET/icon_128x128.png"  > /dev/null
sips -z 256 256   assets/icon_512.png --out "$ICONSET/icon_128x128@2x.png" > /dev/null
sips -z 256 256   assets/icon_512.png --out "$ICONSET/icon_256x256.png"  > /dev/null
sips -z 512 512   assets/icon_512.png --out "$ICONSET/icon_256x256@2x.png" > /dev/null
cp assets/icon_512.png "$ICONSET/icon_512x512.png"
iconutil -c icns "$ICONSET" -o assets/icon.icns
rm -rf "$ICONSET"
echo "Saved assets/icon.icns"

# 4. Build the app
echo "Building .app bundle..."
.venv/bin/pyinstaller build_macos.spec --noconfirm

echo ""
echo "Done! Output: dist/MTG Budget Builder (v1.0.0 macOS).app"
echo "To distribute: right-click the .app -> Compress, then send the zip."
