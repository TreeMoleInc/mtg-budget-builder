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

# 3. Generate macOS icon
echo "Generating icon.icns..."
.venv/bin/python generate_icon.py --icns

# 4. Build the app
echo "Building .app bundle..."
.venv/bin/pyinstaller build_macos.spec --noconfirm

echo ""
echo "Done! Output: dist/MTG Budget Builder.app"
echo "To distribute, drag it into a .dmg or zip it."
