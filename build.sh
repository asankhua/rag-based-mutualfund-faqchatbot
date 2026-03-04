#!/bin/bash
# Build script for Render deployment

echo "Installing Python dependencies..."
pip install -r requirements.txt

echo "Installing Playwright browsers with dependencies..."
playwright install chromium
playwright install-deps chromium

echo "Build complete!"
