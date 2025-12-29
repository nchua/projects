# MCP Server Migration

This directory contains MCP (Model Context Protocol) servers migrated from Claude Desktop to be used with Claude Code CLI.

## What's Included

### Documentation
- **docs/MCP_MIGRATION.md** - Comprehensive documentation of all MCP servers from Claude Desktop, including descriptions, tools, and migration paths

### Configuration
- **mcp-config-template.json** - Template configuration file for Claude Code MCP servers (update paths and API keys before use)

### Setup
- **setup-mcps.sh** - Automated setup script to install MCP servers
- **mcp-servers/** - Directory where cloned MCP servers will be installed

## Quick Start

### 1. Install MCP Servers

Run the setup script:

```bash
./setup-mcps.sh
```

This will:
- Install the filesystem MCP server globally
- Clone and install the OSAScript MCP server
- Clone and install the PDF Toolkit MCP server

### 2. Configure Claude Code

Copy and customize the template configuration:

```bash
cp mcp-config-template.json mcp-config.json
```

Edit `mcp-config.json` to:
- Update file paths to match your system
- Add your Postman API key (if using Postman MCP)
- Adjust allowed directories for filesystem access

### 3. Integrate with Claude Code

Follow the Claude Code documentation to configure MCP servers in your Claude Code settings.

## MCP Servers Migrated

### Cross-Platform MCP Servers

1. **Filesystem** - Read/write files on your local filesystem
   - npm: `@modelcontextprotocol/server-filesystem`

2. **PDF Toolkit** - Analyze, extract, fill, and compare PDFs
   - GitHub: https://github.com/silverstein/pdf-filler-simple

3. **Postman MCP** - Connect to Postman API
   - GitHub: https://github.com/postmanlabs/postman-mcp-server

### macOS-Only MCP Servers

4. **OSAScript** - Execute AppleScript to automate macOS
   - GitHub: https://github.com/k6l3/osascript-dxt

5. **Chrome Control** - Control Google Chrome browser (Anthropic official)
6. **MS Office Excel** - Control Microsoft Excel (Anthropic official)
7. **Apple Notes** - Read/write Apple Notes (Anthropic official)

> Note: The Anthropic official macOS extensions (Chrome Control, Excel, Notes) are currently only available in Claude Desktop.

## Directory Structure

```
.
├── README.md                      # This file
├── setup-mcps.sh                  # Setup script
├── mcp-config-template.json       # MCP configuration template
├── docs/
│   └── MCP_MIGRATION.md          # Detailed migration documentation
└── mcp-servers/                   # Installed MCP servers (created by setup script)
    ├── osascript-dxt/
    └── pdf-filler-simple/
```

## Additional Resources

- [Model Context Protocol Documentation](https://modelcontextprotocol.io/)
- [Claude Code Documentation](https://github.com/anthropics/claude-code)
- [MCP Servers Registry](https://github.com/modelcontextprotocol/servers)

## Notes

- Some MCP servers require Node.js 16+ or 20+
- macOS-specific servers require appropriate system permissions
- API-based servers (like Postman) require valid API keys
- Always review security implications before granting file system or automation access
