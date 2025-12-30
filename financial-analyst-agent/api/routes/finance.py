"""FastAPI routes for financial data analysis.

This module mirrors the Next.js /api/finance endpoint behavior while
using the enhanced agent framework.
"""

import json
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any, Optional

from agent.financial_agent import FinancialAgent
from agent.utils.file_handlers import FileProcessor


router = APIRouter()


class FileData(BaseModel):
    """File data from frontend."""

    base64: str
    fileName: str
    mediaType: str
    isText: bool = False


class MessageRequest(BaseModel):
    """Request model matching Next.js API."""

    messages: List[Dict[str, Any]]
    fileData: Optional[FileData] = None
    model: str


class MessageResponse(BaseModel):
    """Response model matching Next.js API."""

    content: str
    hasToolUse: bool
    toolUse: Optional[Dict[str, Any]] = None
    chartData: Optional[Dict[str, Any]] = None


@router.post("/finance", response_model=MessageResponse)
async def process_finance_message(request: MessageRequest) -> MessageResponse:
    """Main financial analyst endpoint - uses enhanced agent framework.

    Args:
        request: Message request with conversation history and optional file

    Returns:
        MessageResponse with text content and optional chart data

    Raises:
        HTTPException: If processing fails
    """
    try:
        # Validate input
        if not request.messages or not isinstance(request.messages, list):
            raise HTTPException(status_code=400, detail="Messages array is required")

        if not request.model:
            raise HTTPException(status_code=400, detail="Model selection is required")

        # Process file if present and build the user input
        user_input = ""

        if request.fileData:
            try:
                file_processor = FileProcessor()
                processed_file = await file_processor.process_file(
                    request.fileData.base64,
                    request.fileData.fileName,
                    request.fileData.mediaType,
                    request.fileData.isText,
                )

                # Build file content prefix
                if processed_file["type"] == "image":
                    # For images, we'll need to handle this specially
                    # The Agent framework expects messages in a specific format
                    user_input = f"[Image file uploaded: {processed_file['fileName']}]\n\n"
                else:
                    # For text/PDF/CSV, include the content
                    file_content = (
                        f"File contents of {processed_file['fileName']}:\n\n"
                        f"{processed_file['content']}\n\n"
                    )
                    user_input = file_content

            except Exception as e:
                raise HTTPException(
                    status_code=400, detail=f"Error processing file: {str(e)}"
                )

        # Get the last user message
        if request.messages:
            last_message = request.messages[-1]
            if isinstance(last_message.get("content"), str):
                user_input += last_message["content"]
            elif isinstance(last_message.get("content"), list):
                # Handle structured content
                for block in last_message["content"]:
                    if isinstance(block, dict) and block.get("type") == "text":
                        user_input += block["text"]

        # Initialize agent with selected model
        # Use basic configuration for API compatibility
        agent = FinancialAgent(
            model=request.model,
            enable_file_tools=False,  # Files are handled via API upload
            enable_web_search=False,  # Disable for now to keep responses fast
            verbose=True,
        )

        # Run agent with the user input
        # The base Agent's run_async expects a string input
        response = await agent.run_async(user_input)

        # Extract chart data from agent's tracked data
        # The agent captures this during its execution loop
        chart_data = agent.last_chart_data
        has_tool_use = chart_data is not None
        tool_use = None

        if has_tool_use:
            tool_use = {
                "type": "tool_use",
                "id": "chart_generation",
                "name": "generate_graph_data",
                "input": chart_data,
            }

        # Extract text content from response
        text_content = ""
        for content_block in response.content:
            if content_block.type == "text":
                text_content = content_block.text
                break

        return MessageResponse(
            content=text_content,
            hasToolUse=has_tool_use,
            toolUse=tool_use,
            chartData=chart_data,
        )

    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        # Log the error and return a 500
        print(f"Error processing finance message: {str(e)}")
        import traceback

        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
