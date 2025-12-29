# MCP Server Migration from Claude Desktop

This document lists all MCP servers that were installed in Claude Desktop and how to migrate them to Claude Code.

## Installed MCP Servers

### 1. Chrome Control (chrome-control)
- **Version**: 0.1.5
- **Author**: Anthropic
- **Description**: Control Google Chrome browser tabs, windows, and navigation
- **Platform**: macOS only (uses AppleScript)
- **Status in Claude Desktop**: Enabled
- **Source**: Official Anthropic registry

**Tools Available**:
- `open_url` - Open a URL in Chrome
- `get_current_tab` - Get information about the current active tab
- `list_tabs` - List all open tabs in Chrome
- `close_tab` - Close a specific tab
- `switch_to_tab` - Switch to a specific tab
- `reload_tab` - Reload a tab
- `go_back` - Navigate back in browser history
- `go_forward` - Navigate forward in browser history
- `execute_javascript` - Execute JavaScript in the current tab
- `get_page_content` - Get the text content of the current page

**Migration Path**: This is an official Anthropic extension. For Claude Code, you would need to install the equivalent MCP server if available, or use the Claude Desktop version.

---

### 2. Filesystem
- **Version**: 0.2.0
- **Author**: Anthropic
- **Description**: Read and write files on your local filesystem
- **Platform**: Cross-platform (macOS, Windows, Linux)
- **Status in Claude Desktop**: Disabled (needs allowed directories configuration)
- **Source**: Official Anthropic registry
- **Underlying MCP**: @modelcontextprotocol/server-filesystem

**Tools Available**:
- `read_file` - Read the contents of a file
- `read_multiple_files` - Read the contents of multiple files
- `write_file` - Write content to a file
- `edit_file` - Edit the contents of a file
- `create_directory` - Create a new directory
- `list_directory` - List contents of a directory
- `directory_tree` - Display directory structure as a tree
- `move_file` - Move or rename a file
- `search_files` - Search for files by name or content
- `get_file_info` - Get information about a file
- `list_allowed_directories` - List directories that can be accessed

**Migration Path**: Install `@modelcontextprotocol/server-filesystem` via npm

---

### 3. MS Office Excel
- **Version**: 0.3.0
- **Author**: Anthropic
- **Description**: Control Microsoft Excel with AppleScript automation
- **Platform**: macOS only (requires Microsoft Excel)
- **Status in Claude Desktop**: Enabled
- **Source**: Official Anthropic registry

**Tools Available**:
- `create_workbook` - Create a new Excel workbook
- `open_workbook` - Open an existing Excel workbook
- `get_cell_value` - Get the value of a specific cell
- `set_cell_value` - Set the value of a specific cell
- `get_range_values` - Get values from a range of cells
- `set_range_values` - Set values for a range of cells
- `insert_formula` - Insert a formula into a cell
- `create_chart` - Create a chart from data range
- `save_workbook` - Save the active workbook
- `close_workbook` - Close the active workbook
- `export_pdf` - Export the active worksheet as PDF

**Migration Path**: This is an official Anthropic extension for Claude Desktop.

---

### 4. Apple Notes
- **Version**: 0.1.7
- **Author**: Anthropic
- **Description**: Read, write, and manage notes in Apple Notes
- **Platform**: macOS only (uses AppleScript)
- **Status in Claude Desktop**: Enabled
- **Source**: Official Anthropic registry

**Tools Available**:
- `list_notes` - List all notes from Apple Notes app
- `get_note_content` - Get the content of a specific note by its name
- `add_note` - Create a new note in Apple Notes
- `update_note_content` - Update the content of an existing note

**Migration Path**: This is an official Anthropic extension for Claude Desktop.

---

### 5. OSAScript (Control your Mac)
- **Version**: 0.0.1
- **Author**: Kenneth Lien
- **Description**: Execute AppleScript to automate tasks on macOS
- **Platform**: macOS only
- **Status in Claude Desktop**: Enabled
- **Source**: Community (GitHub: k6l3/osascript-dxt)

**Tools Available**:
- `osascript` - Execute `osascript -e <script>`

**Migration Path**: Install from GitHub repository https://github.com/k6l3/osascript-dxt

---

### 6. PDF Toolkit
- **Version**: 0.4.0
- **Author**: Mat Silverstein
- **Description**: Work with PDFs - read, analyze, fill forms, extract data
- **Platform**: Cross-platform
- **Status in Claude Desktop**: Enabled
- **Source**: Community (GitHub: silverstein/pdf-filler-simple)

**Tools Available**:
- `list_pdfs` - List all PDF files in a directory
- `read_pdf_fields` - Read all form fields from a PDF file
- `fill_pdf` - Fill a PDF form with provided data and save it
- `bulk_fill_from_csv` - Fill multiple PDFs using data from a CSV file
- `save_profile` - Save form data as a reusable profile
- `load_profile` - Load a saved profile
- `list_profiles` - List all saved profiles
- `fill_with_profile` - Fill a PDF using a saved profile
- `extract_to_csv` - Extract form data from filled PDFs to a CSV file
- `validate_pdf` - Validate if all required fields in a PDF are filled
- `read_pdf_content` - Read and analyze the full content of a PDF file
- `get_pdf_resource_uri` - Get a resource URI for a PDF file

**Environment Variables**:
- `DEFAULT_PDF_DIR`: `${DOCUMENTS}` (Your Documents folder)
- `DEFAULT_PROFILES_DIR`: `${HOME}/.pdf-filler-profiles`

**Migration Path**: Install from GitHub repository https://github.com/silverstein/pdf-filler-simple

---

### 7. Postman MCP Server (Minimal)
- **Version**: 2.3.6
- **Author**: Postman, Inc.
- **Description**: Connect your AI to your APIs on Postman
- **Platform**: Cross-platform
- **Status in Claude Desktop**: Disabled (needs API key configuration)
- **Source**: Official Postman (GitHub: postmanlabs/postman-mcp-server)

**Configuration Required**:
- `POSTMAN_API_KEY` - A valid Postman API key (sensitive)

**Migration Path**: Install from npm or GitHub repository https://github.com/postmanlabs/postman-mcp-server

---

## Migration Steps for Claude Code

Claude Code (the CLI) uses a different configuration system than Claude Desktop. Here's how to migrate:

### Step 1: Install MCP Servers

For npm-based MCP servers, you can install them globally:

```bash
# Filesystem MCP (cross-platform)
npm install -g @modelcontextprotocol/server-filesystem

# Postman MCP (if you need it)
npm install -g @postmanlabs/mcp-server
```

For GitHub-based MCP servers:

```bash
# Clone and install OSAScript MCP
cd mcp-servers
git clone https://github.com/k6l3/osascript-dxt.git
cd osascript-dxt
npm install

# Clone and install PDF Toolkit
cd ../
git clone https://github.com/silverstein/pdf-filler-simple.git
cd pdf-filler-simple
npm install
```

### Step 2: Configure MCP Servers in Claude Code

Claude Code uses MCP servers through its configuration. You'll need to add MCP servers to your Claude Code settings.

Refer to the Claude Code documentation for the exact configuration format for your version.

### Step 3: Test Each MCP Server

After configuration, test each MCP server to ensure it works correctly with Claude Code.

## Notes

- **Platform Dependencies**: Several MCP servers (chrome-control, ms_office_excel, notes, osascript) are macOS-only and use AppleScript
- **Security**: Some MCP servers require system permissions (Automation, Accessibility) on macOS
- **API Keys**: Postman MCP requires a Postman API key to function
- **Directory Access**: Filesystem MCP needs explicit directory permissions

## Additional Resources

- [Model Context Protocol Documentation](https://modelcontextprotocol.io/)
- [Claude Code Documentation](https://github.com/anthropics/claude-code)
- [Anthropic MCP Servers](https://github.com/anthropics/)
