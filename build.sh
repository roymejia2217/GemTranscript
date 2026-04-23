#!/bin/bash
set -e

cd "$(dirname "$0")"

# Create fresh venv
rm -rf build_venv
python3 -m venv build_venv
source build_venv/bin/activate

# Install dependencies
pip install --upgrade pip
pip install -r requirements.txt
pip install pyinstaller

# Build executables
pyinstaller --onefile --paths . main.py --name gemtranscript
pyinstaller --onefile --paths . gui.py --name gemtranscript-gui

# Cleanup
deactivate
rm -rf build_venv

echo "Build complete. Executables are in dist/"
