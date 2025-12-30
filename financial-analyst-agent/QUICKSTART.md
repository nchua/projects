# Quick Start Guide

## What We Built

You now have a **standalone Python agent** that provides all the functionality of the Financial Data Analyst quickstart, powered by **Claude Opus 4.5**.

### Architecture

```
┌─────────────────────┐
│  React Frontend     │  (Existing Next.js app)
│  localhost:3000     │
└──────────┬──────────┘
           │ HTTP POST
           ▼
┌─────────────────────┐
│  FastAPI Backend    │  (NEW - Python agent)
│  localhost:8000     │
└──────────┬──────────┘
           │ Anthropic SDK
           ▼
┌─────────────────────┐
│  Claude Opus 4.5    │
│  + Chart Tool       │
└─────────────────────┘
```

## Running the System

### Step 1: Start Python Backend

```bash
cd /Users/nickchua/Desktop/AI/financial-analyst-agent
source venv/bin/activate
export ANTHROPIC_API_KEY=your-api-key-here
uvicorn api.main:app --reload --port 8000
```

You should see:
```
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
INFO:     Started reloader process
INFO:     Started server process
INFO:     Application startup complete.
```

### Step 2: Start React Frontend

The frontend is already running! It's been configured to use the Python backend.

**Current status:**
- ✅ React dev server running on http://localhost:3000
- ✅ Configured to use `http://localhost:8000/api/finance`

If you need to restart it:
```bash
cd /Users/nickchua/Desktop/AI/anthropic-quickstarts/financial-data-analyst
npm run dev
```

### Step 3: Test It Out

1. Open http://localhost:3000 in your browser
2. Select **Claude Opus 4.5** from the model dropdown
3. Upload a financial document (PDF, CSV, or image)
4. Ask for visualizations: "Show me a revenue trend chart"
5. Watch the agent generate interactive charts!

## What Was Implemented

### ✅ Core Components

1. **Chart Generation Tool** (`agent/tools/chart_tool.py`)
   - Generates all 6 chart types
   - Validates data with Pydantic
   - Handles pie chart transformations
   - Adds color variables

2. **File Processing** (`agent/utils/file_handlers.py`)
   - PDF text extraction (PyPDF2)
   - CSV parsing (pandas)
   - Image handling (Pillow + Claude vision)
   - Text file support

3. **Financial Agent** (`agent/financial_agent.py`)
   - Claude Opus 4.5 integration
   - Tool execution loop
   - Message history handling
   - Verbose logging

4. **FastAPI Backend** (`api/routes/finance.py`)
   - Mirrors Next.js API behavior exactly
   - CORS configuration for localhost
   - File processing integration
   - Chart data extraction

5. **Frontend Integration**
   - Updated to use `NEXT_PUBLIC_API_URL`
   - Seamless switch between backends
   - No other changes needed!

### ✅ Chart Types Supported

1. **Line Charts**: Time series trends
2. **Bar Charts**: Single metric comparisons
3. **Multi-Bar Charts**: Multiple metrics
4. **Pie Charts**: Distribution analysis
5. **Area Charts**: Volume over time
6. **Stacked Area Charts**: Component breakdowns

## Testing the Agent

### Test Case 1: Simple Query

Ask: "Show me a pie chart of portfolio allocation with 60% stocks and 40% bonds"

Expected: Claude generates a pie chart with proper segments.

### Test Case 2: File Upload

1. Upload a CSV with financial data
2. Ask: "Create a line chart showing the trends"

Expected: Claude analyzes the CSV and generates an appropriate chart.

### Test Case 3: PDF Analysis

1. Upload a financial PDF
2. Ask: "Summarize the key metrics and visualize revenue"

Expected: Claude extracts text and creates charts.

## Troubleshooting

### Backend Not Starting

**Error:** `ModuleNotFoundError: No module named 'agent'`

**Fix:**
```bash
cd /Users/nickchua/Desktop/AI/financial-analyst-agent
source venv/bin/activate
```

### CORS Errors

**Error:** `Access to fetch at 'http://localhost:8000/api/finance' from origin 'http://localhost:3000' has been blocked by CORS policy`

**Fix:** Make sure:
1. FastAPI server is running on port 8000
2. `api/main.py` has correct CORS config (already set)
3. Restart both servers

### Frontend Not Connecting

**Error:** `Failed to fetch`

**Fix:** Check that `.env.local` has:
```
NEXT_PUBLIC_API_URL=http://localhost:8000/api/finance
```

Then restart Next.js:
```bash
cd /Users/nickchua/Desktop/AI/anthropic-quickstarts/financial-data-analyst
npm run dev
```

## Next Steps

### 1. Create a CLI Version

Add `cli.py` for terminal-based financial analysis:

```python
import asyncio
from agent.financial_agent import FinancialAgent

async def main():
    agent = FinancialAgent(verbose=True)

    print("Financial Analyst Agent (CLI)")
    print("=" * 50)

    while True:
        query = input("\nYou: ")
        if query.lower() in ["exit", "quit"]:
            break

        messages = [{"role": "user", "content": query}]
        response = await agent.run_async(messages)

        # Print response
        for block in response.content:
            if block.type == "text":
                print(f"\nAgent: {block.text}")

if __name__ == "__main__":
    asyncio.run(main())
```

### 2. Add More Tools

Extend the agent with additional capabilities:
- Financial calculations (DCF, NPV, IRR)
- Data aggregation from APIs (Alpha Vantage, Yahoo Finance)
- Statistical analysis tools
- PDF report generation

### 3. Deploy to Production

Options:
- **Railway**: Easy FastAPI deployment
- **Render**: Free tier available
- **Fly.io**: Global deployment
- **AWS EC2**: Full control

### 4. Integrate with Your Job Search Skill

Combine the financial analyst with your existing job-search skill to analyze company financials during research!

```python
# Example: Add financial analysis to company research
from agent.financial_agent import FinancialAgent

agent = FinancialAgent()
result = await agent.run_async([
    {"role": "user", "content": "Analyze Anthropic's potential market size and growth"}
])
```

## File Structure Summary

```
financial-analyst-agent/
├── agent/
│   ├── financial_agent.py       # Main agent (Claude Opus 4.5)
│   ├── tools/
│   │   ├── base.py              # Tool base class
│   │   ├── chart_tool.py        # Chart generation (6 types)
│   │   └── think.py             # Thinking tool
│   ├── prompts/
│   │   └── financial_analyst.py # System prompt
│   └── utils/
│       ├── file_handlers.py     # PDF/CSV/image processing
│       └── chart_schemas.py     # Pydantic models
├── api/
│   ├── main.py                  # FastAPI app
│   └── routes/
│       └── finance.py           # /api/finance endpoint
├── venv/                        # Python virtual environment
├── requirements.txt             # Dependencies
├── README.md                    # Full documentation
└── QUICKSTART.md                # This file!
```

## Success! 🎉

You now have a fully functional standalone financial analyst agent powered by Claude Opus 4.5!

The agent can:
- ✅ Analyze financial data
- ✅ Generate 6 types of interactive charts
- ✅ Process PDFs, CSVs, and images
- ✅ Work with the existing React UI
- ✅ Run autonomously with custom workflows

**Next:** Start asking it to analyze your financial data and watch it create beautiful visualizations!
