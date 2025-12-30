"""FastAPI application for Financial Data Analyst agent.

This server provides REST API endpoints for the financial analyst
functionality, replacing the Next.js API routes.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import finance

# Create FastAPI app
app = FastAPI(
    title="Financial Data Analyst API",
    description="Python backend for financial data analysis and visualization using Claude",
    version="1.0.0",
)

# Configure CORS for React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",  # Next.js dev server
        "http://127.0.0.1:3000",  # Alternative localhost
    ],
    allow_credentials=True,
    allow_methods=["*"],  # Allow all HTTP methods
    allow_headers=["*"],  # Allow all headers
)

# Include routers
app.include_router(finance.router, prefix="/api", tags=["finance"])


@app.get("/")
async def root():
    """Health check endpoint."""
    return {
        "status": "ok",
        "service": "Financial Data Analyst API",
        "message": "Server is running. Use /api/finance to interact with the agent.",
    }


@app.get("/health")
async def health_check():
    """Health check endpoint for monitoring."""
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,  # Enable auto-reload during development
    )
