#!/bin/bash

# MCP Server Setup Script
# This script helps migrate MCP servers from Claude Desktop to Claude Code

set -e

echo "==================================="
echo "MCP Server Migration Setup"
echo "==================================="
echo ""

# Create directories
echo "Creating directories..."
mkdir -p mcp-servers
cd mcp-servers

# Install filesystem MCP globally
echo ""
echo "Installing @modelcontextprotocol/server-filesystem globally..."
npm install -g @modelcontextprotocol/server-filesystem

# Clone and install community MCP servers
echo ""
echo "Cloning OSAScript MCP..."
if [ -d "osascript-dxt" ]; then
    echo "osascript-dxt already exists, skipping..."
else
    git clone https://github.com/k6l3/osascript-dxt.git
    cd osascript-dxt
    npm install
    cd ..
fi

echo ""
echo "Cloning PDF Toolkit MCP..."
if [ -d "pdf-filler-simple" ]; then
    echo "pdf-filler-simple already exists, skipping..."
else
    git clone https://github.com/silverstein/pdf-filler-simple.git
    cd pdf-filler-simple
    npm install
    cd ..
fi

cd ..

echo ""
echo "==================================="
echo "Setup Complete!"
echo "==================================="
echo ""
echo "Next steps:"
echo "1. Review the mcp-config-template.json file"
echo "2. Update paths and API keys as needed"
echo "3. Configure Claude Code to use the MCP servers"
echo "4. See docs/MCP_MIGRATION.md for detailed information"
echo ""
