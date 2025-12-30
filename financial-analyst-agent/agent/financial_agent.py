"""Enhanced Financial Data Analyst Agent using the full Anthropic agent framework.

This agent provides sophisticated financial analysis capabilities with:
- Chart generation (6 types)
- File reading/writing for data persistence
- MCP server integration for extended functionality
- Web search for real-time financial data
- Token tracking and prompt caching
- Context window management
"""

import os
from typing import Optional, List, Dict, Any

from agent.agent import Agent, ModelConfig
from agent.tools.chart_tool import GenerateGraphDataTool
from agent.tools.file_tools import FileReadTool, FileWriteTool
from agent.tools.think import ThinkTool
from agent.tools.web_search import WebSearchServerTool
from agent.prompts.financial_analyst import FINANCIAL_ANALYST_PROMPT


class FinancialAgent(Agent):
    """Enhanced financial analyst agent with full framework capabilities.

    This agent extends the base Agent class with:
    - Financial chart generation
    - File I/O for reading data and saving analysis
    - Web search for current financial information
    - MCP server support for external tools
    - Token tracking and context management
    """

    def __init__(
        self,
        model: str = "claude-opus-4-5-20251101",
        max_tokens: int = 4096,
        temperature: float = 0.7,
        enable_file_tools: bool = True,
        enable_web_search: bool = False,
        mcp_servers: Optional[List[Dict[str, Any]]] = None,
        verbose: bool = False,
        api_key: Optional[str] = None,
    ):
        # Initialize tracking for tool calls
        self.last_chart_data = None
        """Initialize the Enhanced Financial Analyst agent.

        Args:
            model: Claude model to use (default: Opus 4.5)
            max_tokens: Maximum tokens for response
            temperature: Sampling temperature
            enable_file_tools: Enable file read/write capabilities
            enable_web_search: Enable web search for financial data
            mcp_servers: List of MCP server configurations
            verbose: Enable detailed logging
            api_key: Anthropic API key (defaults to ANTHROPIC_API_KEY env var)
        """
        # Configure model settings
        config = ModelConfig(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            context_window_tokens=180000,  # Claude Opus 4.5 context window
        )

        # Build tool list
        tools = [
            GenerateGraphDataTool(),  # Core financial chart generation
            ThinkTool(),  # Internal reasoning
        ]

        # Add file tools if enabled
        if enable_file_tools:
            tools.extend([
                FileReadTool(),  # Read data files and directories
                FileWriteTool(),  # Save analysis results
            ])

        # Add web search if enabled
        if enable_web_search:
            tools.append(
                WebSearchServerTool(
                    name="web_search",
                    max_uses=5,  # Limit searches per conversation
                )
            )

        # Initialize base Agent with financial analyst configuration
        super().__init__(
            name="FinancialAnalyst",
            system=FINANCIAL_ANALYST_PROMPT,
            tools=tools,
            mcp_servers=mcp_servers or [],
            config=config,
            verbose=verbose,
            client=None,  # Will use default Anthropic client
            message_params={
                "anthropic-api-key": api_key or os.environ.get("ANTHROPIC_API_KEY"),
            } if api_key else {},
        )

        if verbose:
            print(f"[FinancialAgent] Initialized with:")
            print(f"  Model: {model}")
            print(f"  File Tools: {'enabled' if enable_file_tools else 'disabled'}")
            print(f"  Web Search: {'enabled' if enable_web_search else 'disabled'}")
            print(f"  MCP Servers: {len(mcp_servers or [])}")
            print(f"  Total Tools: {len(tools)}")

    async def _agent_loop(self, user_input: str) -> Any:
        """Override agent loop to capture chart data from tool calls."""
        # Reset chart data for new conversation turn
        self.last_chart_data = None

        # Call parent agent loop
        response = await super()._agent_loop(user_input)

        # Extract chart data from message history
        # The chart tool was called during the loop, check history
        for message in self.history.messages:
            if message.get("role") == "assistant":
                for content in message.get("content", []):
                    # Handle both dict and Anthropic SDK object (ToolUseBlock)
                    if isinstance(content, dict):
                        content_type = content.get("type")
                        content_name = content.get("name")
                        content_input = content.get("input")
                    else:
                        # It's an Anthropic SDK object (ToolUseBlock, TextBlock, etc.)
                        content_type = getattr(content, "type", None)
                        content_name = getattr(content, "name", None)
                        content_input = getattr(content, "input", None)

                    if content_type == "tool_use" and content_name == "generate_graph_data":
                        # Found chart generation - store it
                        self.last_chart_data = content_input
                        break

        return response

    async def analyze_with_files(
        self,
        query: str,
        file_paths: Optional[List[str]] = None,
        save_results: bool = False,
        output_path: Optional[str] = None,
    ) -> Any:
        """Analyze financial data with optional file reading and result saving.

        This is a convenience method that wraps the agent's run_async with
        file handling capabilities.

        Args:
            query: The financial analysis query
            file_paths: List of file paths to read and analyze
            save_results: Whether to save analysis results to a file
            output_path: Path to save results (if save_results=True)

        Returns:
            Agent response with analysis and charts
        """
        # Build the user message
        user_message = query

        # Add file reading instructions if provided
        if file_paths:
            file_list = ", ".join(file_paths)
            user_message = (
                f"Please read and analyze the following files: {file_list}\n\n"
                f"{query}"
            )

        # Add save instructions if requested
        if save_results and output_path:
            user_message += (
                f"\n\nAfter completing the analysis, please save the results "
                f"to {output_path} using the file_write tool."
            )

        # Run the agent
        return await self.run_async(user_message)

    def enable_mcp_server(
        self,
        command: str,
        args: Optional[List[str]] = None,
        env: Optional[Dict[str, str]] = None,
    ):
        """Dynamically add an MCP server to the agent.

        Args:
            command: Command to run the MCP server
            args: Command arguments
            env: Environment variables for the server
        """
        server_config = {
            "command": command,
            "args": args or [],
            "env": env or {},
        }
        self.mcp_servers.append(server_config)

        if self.verbose:
            print(f"[FinancialAgent] Added MCP server: {command}")

    def enable_web_search(self, max_uses: int = 5):
        """Dynamically enable web search capability.

        Args:
            max_uses: Maximum number of searches per conversation
        """
        # Check if already enabled
        if any(tool.name == "web_search" for tool in self.tools):
            if self.verbose:
                print("[FinancialAgent] Web search already enabled")
            return

        self.tools.append(
            WebSearchServerTool(
                name="web_search",
                max_uses=max_uses,
            )
        )

        if self.verbose:
            print(f"[FinancialAgent] Enabled web search (max {max_uses} uses)")


# Convenience function for quick agent creation
def create_financial_agent(
    model: str = "claude-opus-4-5-20251101",
    enable_all_features: bool = True,
    verbose: bool = True,
) -> FinancialAgent:
    """Create a fully-featured financial analyst agent.

    Args:
        model: Claude model to use
        enable_all_features: Enable file tools and web search
        verbose: Enable detailed logging

    Returns:
        Configured FinancialAgent instance
    """
    return FinancialAgent(
        model=model,
        enable_file_tools=enable_all_features,
        enable_web_search=enable_all_features,
        verbose=verbose,
    )
