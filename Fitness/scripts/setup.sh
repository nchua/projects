#!/bin/bash
# Setup script for Workout Screenshot Watcher

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FITNESS_DIR="$(dirname "$SCRIPT_DIR")"

echo "=================================="
echo "Workout Screenshot Watcher Setup"
echo "=================================="
echo

# Check for Python
if ! command -v python3 &> /dev/null; then
    echo "Error: Python 3 is required but not installed."
    exit 1
fi

echo "1. Installing Python dependencies..."
pip3 install -r "$SCRIPT_DIR/requirements.txt"
echo "   Done!"
echo

# Check for API key
if [ -z "$ANTHROPIC_API_KEY" ]; then
    echo "2. ANTHROPIC_API_KEY not set."
    echo "   Please add the following to your ~/.zshrc or ~/.bashrc:"
    echo
    echo "   export ANTHROPIC_API_KEY='your-api-key'"
    echo
    read -p "   Enter your Anthropic API key (or press Enter to skip): " api_key
    if [ -n "$api_key" ]; then
        echo "export ANTHROPIC_API_KEY='$api_key'" >> ~/.zshrc
        echo "   Added to ~/.zshrc"
        export ANTHROPIC_API_KEY="$api_key"
    fi
else
    echo "2. ANTHROPIC_API_KEY already set"
fi
echo

# Create directories
echo "3. Creating directories..."
mkdir -p "$FITNESS_DIR/Workout Log Screenshot/processed"
mkdir -p "$FITNESS_DIR/dashboard"
echo "   Done!"
echo

# Make scripts executable
echo "4. Making scripts executable..."
chmod +x "$SCRIPT_DIR/process_workout_screenshot.py"
chmod +x "$SCRIPT_DIR/watch_screenshots.py"
echo "   Done!"
echo

echo "=================================="
echo "Setup Complete!"
echo "=================================="
echo
echo "Usage:"
echo
echo "  Process existing screenshots:"
echo "    python3 $SCRIPT_DIR/process_workout_screenshot.py"
echo
echo "  Start watcher (foreground):"
echo "    python3 $SCRIPT_DIR/watch_screenshots.py"
echo
echo "  Start watcher (background):"
echo "    python3 $SCRIPT_DIR/watch_screenshots.py --daemon"
echo
echo "  View dashboard:"
echo "    cd $FITNESS_DIR/dashboard && python3 -m http.server 8080"
echo "    Then open http://localhost:8080"
echo
echo "Screenshot folder: $FITNESS_DIR/Workout Log Screenshot/"
echo
