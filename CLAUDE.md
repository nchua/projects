# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Purpose

This repository contains MCP (Model Context Protocol) server configurations migrated from Claude Desktop App to work with Claude Code CLI. It includes setup scripts, configuration templates, and locally installed MCP server implementations.

## Common Commands

### Setup and Installation

```bash
# Initial setup - installs all MCP servers
./setup-mcps.sh

# Check installed global MCP servers
npm list -g --depth=0 | grep mcp

# Check Node.js and npm versions
node --version && npm --version
```

### Testing MCP Servers

```bash
# Test filesystem MCP server (global installation)
npx -y @modelcontextprotocol/server-filesystem /Users/nickchua/Desktop

# Test PDF toolkit MCP server (local installation)
node mcp-servers/pdf-filler-simple/server/index.js

# Test OSAScript MCP server (local installation)
node mcp-servers/osascript-dxt/server/index.js
```

### Updating MCP Servers

```bash
# Update global filesystem server
npm update -g @modelcontextprotocol/server-filesystem

# Update local MCP servers
cd mcp-servers/osascript-dxt && git pull && npm install
cd ../pdf-filler-simple && git pull && npm install
```

## Architecture Overview

### MCP Server Organization Strategy

This repository uses a **hybrid installation approach** for MCP servers:

1. **Global npm packages** (via `npm install -g`)
   - Used for: Official MCP servers from npm registry
   - Example: `@modelcontextprotocol/server-filesystem`
   - Benefit: Easily accessible via `npx`, automatic PATH resolution

2. **Local git clones** (in `mcp-servers/` directory)
   - Used for: Community MCP servers from GitHub
   - Examples: `osascript-dxt`, `pdf-filler-simple`
   - Benefit: Full source code access, easier to debug and modify

### Configuration Template System

The `mcp-config-template.json` file demonstrates the MCP server configuration format for Claude Code:

- **Global servers**: Use `npx -y <package-name>` as the command
- **Local servers**: Use `node <absolute-path-to-server/index.js>` as the command
- **Environment variables**: Passed via the `env` object for each server

Key configuration patterns:
```json
{
  "mcpServers": {
    "server-name": {
      "command": "npx" | "node",
      "args": ["..."],
      "env": { /* optional environment variables */ }
    }
  }
}
```

### Directory Structure Logic

```
/Users/nickchua/Desktop/AI/
├── mcp-servers/              # Local MCP server installations (git clones)
│   ├── osascript-dxt/       # macOS AppleScript automation
│   └── pdf-filler-simple/   # PDF toolkit with node_modules
├── docs/                     # Migration documentation
│   └── MCP_MIGRATION.md     # Detailed server descriptions and tools
├── setup-mcps.sh            # Automated installation script
└── mcp-config-template.json # Configuration reference
```

## Important Implementation Details

### Platform-Specific Considerations

- **macOS-only servers**: `osascript-dxt`, Chrome Control, Excel, Apple Notes
  - Require macOS system permissions (Automation, Accessibility)
  - Use AppleScript under the hood

- **Cross-platform servers**: filesystem, PDF toolkit, Postman
  - Work on macOS, Linux, Windows
  - No special OS permissions required (except filesystem directories)

### Environment Variable Patterns

MCP servers use environment variables for configuration:

- **PDF Toolkit**:
  - `DEFAULT_PDF_DIR`: Where to look for PDFs (default: Documents folder)
  - `DEFAULT_PROFILES_DIR`: Where to store form profiles (default: `~/.pdf-filler-profiles`)

- **Postman MCP**:
  - `POSTMAN_API_KEY`: Required API key for Postman integration

- **Filesystem MCP**:
  - Allowed directories passed as command arguments, NOT environment variables
  - Example: `npx @modelcontextprotocol/server-filesystem /path1 /path2`

### Anthropic Official vs Community Servers

The original Claude Desktop setup included 7 MCP servers:

- **3 Anthropic official macOS-only** (Chrome Control, Excel, Notes): Currently only available in Claude Desktop app, not migrated
- **1 Anthropic official cross-platform** (Filesystem): Migrated via npm
- **3 Community servers** (OSAScript, PDF Toolkit, Postman): Migrated via git clone or npm

## Migration Reference

See `docs/MCP_MIGRATION.md` for:
- Complete list of all available tools for each MCP server
- Detailed descriptions of each server's capabilities
- Migration paths from Claude Desktop to Claude Code
- Security and permission requirements

See `MCP_SUMMARY.txt` for a quick reference of what was migrated.
