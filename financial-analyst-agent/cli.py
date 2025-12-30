"""CLI interface for the Enhanced Financial Analyst Agent.

This demonstrates the advanced features of the agent including:
- File reading/writing
- Interactive analysis
- Result saving
- MCP server integration (optional)
"""

import asyncio
import os
import sys
from pathlib import Path

from agent.financial_agent import FinancialAgent, create_financial_agent


async def interactive_mode():
    """Run the agent in interactive CLI mode."""
    print("=" * 70)
    print("Financial Analyst Agent - CLI Mode")
    print("=" * 70)
    print("\nFeatures:")
    print("  • Chart generation (6 types)")
    print("  • File reading and writing")
    print("  • Web search (if enabled)")
    print("  • MCP server integration")
    print("\nCommands:")
    print("  'exit' or 'quit' - Exit the program")
    print("  'save <path>' - Save the last analysis to a file")
    print("  'read <path>' - Read and analyze a file")
    print("  'enable-search' - Enable web search")
    print("=" * 70)

    # Create agent with all features enabled
    agent = create_financial_agent(
        model="claude-opus-4-5-20251101",
        enable_all_features=True,
        verbose=True,
    )

    last_response = None

    while True:
        try:
            # Get user input
            user_input = input("\nYou: ").strip()

            if not user_input:
                continue

            # Handle commands
            if user_input.lower() in ["exit", "quit"]:
                print("\nGoodbye!")
                break

            elif user_input.lower().startswith("save "):
                # Save last response to file
                if not last_response:
                    print("No analysis to save yet. Try asking a question first!")
                    continue

                output_path = user_input[5:].strip()
                if not output_path:
                    print("Please specify a file path: save <path>")
                    continue

                try:
                    # Extract text from response
                    text_content = ""
                    for block in last_response.content:
                        if block.type == "text":
                            text_content = block.text

                    # Write to file
                    Path(output_path).write_text(text_content)
                    print(f"✓ Saved analysis to {output_path}")
                except Exception as e:
                    print(f"✗ Error saving file: {e}")
                continue

            elif user_input.lower().startswith("read "):
                # Read and analyze a file
                file_path = user_input[5:].strip()
                if not file_path:
                    print("Please specify a file path: read <path>")
                    continue

                if not Path(file_path).exists():
                    print(f"✗ File not found: {file_path}")
                    continue

                # Use the agent's file analysis capability
                query = f"Please read and analyze the file at {file_path}"
                user_input = query

            elif user_input.lower() == "enable-search":
                agent.enable_web_search(max_uses=5)
                continue

            # Run the agent
            print("\n[Agent is thinking...]")
            response = await agent.run_async(user_input)
            last_response = response

            # Display response
            print("\nAgent:")
            for block in response.content:
                if block.type == "text":
                    print(block.text)
                elif block.type == "tool_use":
                    if block.name == "generate_graph_data":
                        print(f"\n[Chart generated: {block.input.get('config', {}).get('title', 'Untitled')}]")
                        print(f"[Chart type: {block.input.get('chartType', 'unknown')}]")

        except KeyboardInterrupt:
            print("\n\nInterrupted. Type 'exit' to quit.")
            continue
        except Exception as e:
            print(f"\n✗ Error: {e}")
            import traceback
            traceback.print_exc()
            continue


async def analyze_file(file_path: str, output_path: str = None):
    """Analyze a single file and optionally save results."""
    print(f"Analyzing file: {file_path}")

    if not Path(file_path).exists():
        print(f"Error: File not found: {file_path}")
        return

    agent = FinancialAgent(
        enable_file_tools=True,
        verbose=True,
    )

    # Analyze with file reading
    response = await agent.analyze_with_files(
        query="Please analyze this data and create relevant visualizations",
        file_paths=[file_path],
        save_results=bool(output_path),
        output_path=output_path,
    )

    # Display results
    print("\nAnalysis:")
    for block in response.content:
        if block.type == "text":
            print(block.text)

    if output_path:
        print(f"\n✓ Results saved to {output_path}")


async def demo_mode():
    """Run a demo showing the agent's capabilities."""
    print("=" * 70)
    print("Financial Analyst Agent - Demo Mode")
    print("=" * 70)

    agent = create_financial_agent(verbose=True)

    demos = [
        "Create a pie chart showing portfolio allocation: 60% stocks, 30% bonds, 10% cash",
        "Show me a line chart of quarterly revenue: Q1 $1.2M, Q2 $1.5M, Q3 $1.8M, Q4 $2.1M",
        "Generate a bar chart comparing product sales: Product A $450K, Product B $650K, Product C $380K",
    ]

    for i, demo_query in enumerate(demos, 1):
        print(f"\n\nDemo {i}/3")
        print(f"Query: {demo_query}")
        print("-" * 70)

        response = await agent.run_async(demo_query)

        for block in response.content:
            if block.type == "text":
                print(f"\nResponse: {block.text}")
            elif block.type == "tool_use" and block.name == "generate_graph_data":
                chart_config = block.input.get("config", {})
                print(f"\n✓ Chart Generated:")
                print(f"  Title: {chart_config.get('title', 'Untitled')}")
                print(f"  Type: {block.input.get('chartType', 'unknown')}")
                print(f"  Data points: {len(block.input.get('data', []))}")

        await asyncio.sleep(1)  # Pause between demos

    print("\n" + "=" * 70)
    print("Demo complete!")


def main():
    """Main entry point for the CLI."""
    if len(sys.argv) > 1:
        command = sys.argv[1]

        if command == "demo":
            asyncio.run(demo_mode())
        elif command == "analyze":
            if len(sys.argv) < 3:
                print("Usage: python cli.py analyze <file_path> [output_path]")
                sys.exit(1)

            file_path = sys.argv[2]
            output_path = sys.argv[3] if len(sys.argv) > 3 else None
            asyncio.run(analyze_file(file_path, output_path))
        else:
            print(f"Unknown command: {command}")
            print("Usage: python cli.py [interactive|demo|analyze <file>]")
            sys.exit(1)
    else:
        # Default to interactive mode
        asyncio.run(interactive_mode())


if __name__ == "__main__":
    # Check for API key
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("Error: ANTHROPIC_API_KEY environment variable not set")
        print("Please set it before running:")
        print("  export ANTHROPIC_API_KEY=your-api-key-here")
        sys.exit(1)

    main()
