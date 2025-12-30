# Financial Data Analyst Agent

A standalone Python agent for financial data analysis and visualization using Claude Opus 4.5. This project ports the functionality from the Anthropic quickstarts Next.js application to a Python backend with FastAPI, **enhanced with the full Anthropic agent framework**.

## Features

### Core Capabilities

- **Claude Opus 4.5 Integration**: Uses the most capable Claude model for complex financial analysis
- **6 Chart Types**: Bar, Multi-Bar, Line, Pie, Area, and Stacked Area charts
- **File Processing**: Support for PDF, CSV, images, and text files
- **Interactive Web UI**: Works with the existing React frontend from the quickstarts
- **Standalone Agent**: Can run as CLI tool or web service

### Enhanced Capabilities (NEW!)

- **Autonomous File Operations**: Agent can read and write files independently
- **Web Search Integration**: Real-time financial data retrieval
- **MCP Server Support**: Connect to external tools (PDF toolkit, filesystem, etc.)
- **Token Tracking**: Automatic usage monitoring and cost optimization
- **Prompt Caching**: Up to 90% cost reduction on repeated contexts
- **Context Management**: Automatic conversation truncation for long sessions
- **Parallel Tool Execution**: Up to 3x faster multi-tool operations
- **Think Tool**: Internal reasoning for better analysis quality

📖 **See [ENHANCED_FEATURES.md](ENHANCED_FEATURES.md) for detailed documentation of all new capabilities**

## Architecture

```
React Frontend (Next.js)
    ↓ HTTP
FastAPI Backend (Python)
    ↓
FinancialAgent
    ↓ API
Claude Opus 4.5
```

## Installation

### 1. Create Virtual Environment

```bash
cd financial-analyst-agent
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Set API Key

```bash
export ANTHROPIC_API_KEY=sk-ant-api03-...
```

Or create a `.env` file:
```
ANTHROPIC_API_KEY=sk-ant-api03-...
```

## Usage

### Option 1: Web Service (with React Frontend)

**Terminal 1: Start Python Backend**
```bash
cd /Users/nickchua/Desktop/AI/financial-analyst-agent
source venv/bin/activate
uvicorn api.main:app --reload --port 8000
```

**Terminal 2: Start React Frontend**
```bash
cd /Users/nickchua/Desktop/AI/anthropic-quickstarts/financial-data-analyst
npm run dev
```

Then open http://localhost:3000 in your browser.

### Option 2: CLI Mode (Coming Soon)

```bash
python cli.py
```

## Project Structure

```
financial-analyst-agent/
├── agent/
│   ├── financial_agent.py       # Main agent class
│   ├── tools/
│   │   ├── base.py              # Tool base class
│   │   ├── chart_tool.py        # Chart generation tool
│   │   └── think.py             # Thinking tool
│   ├── prompts/
│   │   └── financial_analyst.py # System prompt
│   └── utils/
│       ├── file_handlers.py     # File processing
│       └── chart_schemas.py     # Pydantic models
├── api/
│   ├── main.py                  # FastAPI app
│   └── routes/
│       └── finance.py           # /api/finance endpoint
├── requirements.txt
└── README.md
```

## API Endpoints

### POST /api/finance

Main endpoint for financial analysis.

**Request:**
```json
{
  "messages": [
    {"role": "user", "content": "Show me revenue trends"}
  ],
  "fileData": {
    "base64": "...",
    "fileName": "data.csv",
    "mediaType": "text/csv",
    "isText": false
  },
  "model": "claude-opus-4-5-20251101"
}
```

**Response:**
```json
{
  "content": "Here's the revenue trend analysis...",
  "hasToolUse": true,
  "chartData": {
    "chartType": "line",
    "config": {
      "title": "Revenue Trends",
      "description": "Quarterly revenue growth"
    },
    "data": [...],
    "chartConfig": {...}
  }
}
```

### GET /

Health check endpoint.

### GET /health

Service health status.

## Development

### Running Tests

```bash
pytest tests/
```

### Code Structure

- **agent/financial_agent.py**: Main agent orchestration
- **agent/tools/chart_tool.py**: Core chart generation logic
- **agent/utils/file_handlers.py**: File processing utilities
- **api/routes/finance.py**: FastAPI endpoint matching Next.js behavior

## Features

### Supported File Types

- **Text**: .txt, .md, .html, .py, .csv (as text)
- **PDF**: Text extraction from PDFs
- **Images**: PNG, JPG, GIF (via Claude vision)
- **CSV**: Structured data parsing with pandas

### Chart Types

1. **Line Charts**: Time series trends
2. **Bar Charts**: Single metric comparisons
3. **Multi-Bar Charts**: Multiple metrics side-by-side
4. **Pie Charts**: Distribution analysis
5. **Area Charts**: Volume over time
6. **Stacked Area Charts**: Component breakdowns

## Environment Variables

- `ANTHROPIC_API_KEY`: Your Anthropic API key (required)

## Troubleshooting

### CORS Errors

If you see CORS errors, make sure:
1. The FastAPI server is running on port 8000
2. The React app is configured to use `http://localhost:8000/api/finance`
3. CORS middleware is configured correctly in `api/main.py`

### Import Errors

Make sure you're in the virtual environment:
```bash
source venv/bin/activate
```

And all dependencies are installed:
```bash
pip install -r requirements.txt
```

### API Key Issues

Verify your API key is set:
```bash
echo $ANTHROPIC_API_KEY
```

## License

MIT License - See the parent anthropic-quickstarts repository for details.

## Acknowledgments

Based on the [Anthropic Quickstarts](https://github.com/anthropics/anthropic-quickstarts) financial-data-analyst project.
