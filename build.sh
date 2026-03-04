#!/bin/bash
# Build script for Render deployment

echo "Installing Python dependencies..."
pip install -r requirements.txt

echo "Installing Playwright browsers..."
playwright install chromium

echo "Build complete!"
