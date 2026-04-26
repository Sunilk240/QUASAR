#!/usr/bin/env python
"""
QUASAR CLI - Terminal-based AI Code Editor

Usage:
    quasar "your prompt here"           # Single command mode
    quasar --interactive                # REPL mode
    quasar --help                       # Show help
"""

import asyncio
import os
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.syntax import Syntax
from rich.text import Text

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from services.agent.orchestrator import Orchestrator
from services.agent.models import CredentialManager

# Version
__version__ = "2.0.1"

def version_callback(value: bool):
    """Show version and exit."""
    if value:
        console.print(f"[bold cyan]QUASAR[/bold cyan] v{__version__}")
        raise typer.Exit()

app = typer.Typer(
    name="quasar",
    help="🚀 QUASAR - AI-powered CLI code editor",
    add_completion=False,
)
console = Console()

# Global orchestrator and selected model
_orchestrator: Optional[Orchestrator] = None
_selected_model: Optional[str] = None


def get_orchestrator() -> Orchestrator:
    """Get or create orchestrator instance."""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = Orchestrator()
    return _orchestrator


def check_api_keys() -> bool:
    """
    Check provider configuration and show startup status.

    Ollama is ALWAYS available as a fallback.
    Up to 4 independent custom slots (CUSTOM_1_*, CUSTOM_2_*, etc.) are shown
    if configured. We never block startup — bad URLs surface at query time.
    """
    import os

    ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    ollama_status = f"[green]ollama[/green] ({ollama_url})"

    # Show all 4 custom slots
    slot_parts = []
    any_custom_configured = False
    for n in [1, 2, 3, 4]:
        base_url = os.getenv(f"CUSTOM_{n}_BASE_URL", "").strip()
        model    = os.getenv(f"CUSTOM_{n}_MODEL", "").strip()
        if base_url and model:
            slot_parts.append(f"[green]slot{n}[/green] ({base_url} / {model})")
            any_custom_configured = True
        else:
            slot_parts.append(f"[dim]slot{n}:off[/dim]")

    custom_summary = " | ".join(slot_parts)
    console.print(f"[dim]✓ Providers: {ollama_status}[/dim]")
    console.print(f"[dim]  Custom slots: {custom_summary}[/dim]")

    if not any_custom_configured:
        console.print(
            "[dim yellow]  ⚠ No custom slots configured. "
            "Set CUSTOM_1_BASE_URL + CUSTOM_1_MODEL + CUSTOM_1_API_KEY_1 to add a provider.[/dim yellow]"
        )

    return True  # Ollama is always the fallback; never block startup



async def process_query(query: str, workspace: str, selected_model: Optional[str] = None) -> None:
    """Process a single query and stream the response with rich visual feedback."""
    # Issue 3: Reset the ConfirmationGate before each query so stale state from
    # a previous abnormally-terminated query (e.g. Ctrl-C mid-confirmation) is
    # cleared. Any leaked awaiter is unblocked with a deny before being released.
    from services.agent.tools.confirmation_gate import get_confirmation_gate as _gcg
    _gcg().reset()

    orchestrator = get_orchestrator()
    orchestrator.set_workspace(workspace)

    # Load MCP servers if not already loaded
    if orchestrator.mcp_manager and not orchestrator.mcp_tools:
        mcp_count = await orchestrator.load_mcp_servers()
        if mcp_count > 0:
            console.print(f"[dim]🔌 Loaded {mcp_count} MCP server(s) with {len(orchestrator.mcp_tools)} tools[/dim]")

    response_text = ""
    current_tool = None
    plan_shown = False

    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        task_id = progress.add_task("Thinking...", total=None)
        
        try:
            async for chunk in orchestrator.process_stream(query=query, selected_model=selected_model):
                chunk_type = chunk.get("type", "")
                
                if chunk_type == "classification":
                    task_type = chunk.get("task_type", "unknown")
                    confidence = chunk.get("confidence", 0)
                    progress.update(task_id, description=f"[cyan]Task: {task_type} ({confidence:.0%})[/cyan]")
                
                elif chunk_type == "thinking":
                    # Show thinking in dim italic
                    content = chunk.get("content", "")
                    if content:
                        progress.stop()
                        console.print(f"[dim italic]💭 {content}[/dim italic]")
                        progress.start()
                
                elif chunk_type == "plan":
                    # Show structured plan
                    if not plan_shown:
                        progress.stop()
                        steps = chunk.get("steps", [])
                        console.print("\n[bold cyan]📋 Plan:[/bold cyan]")
                        for i, step in enumerate(steps, 1):
                            console.print(f"  [cyan]{i}.[/cyan] {step}")
                        console.print()
                        plan_shown = True
                        progress.start()

                elif chunk_type == "plan_generated":
                    # P7: Pre-task plan — shown before the agentic loop begins
                    plan_text = chunk.get("plan", "")
                    if plan_text and not plan_shown:
                        progress.stop()
                        console.print(
                            Panel(
                                f"[dim]{plan_text}[/dim]",
                                title="[bold dim cyan]📋 Execution Plan[/bold dim cyan]",
                                border_style="dim cyan",
                                padding=(0, 1),
                            )
                        )
                        console.print()
                        plan_shown = True
                        progress.start()
                
                elif chunk_type == "iteration":
                    current = chunk.get("current", 1)
                    max_iter = chunk.get("max", 30)
                    remaining = chunk.get("remaining", 0)
                    progress.update(task_id, description=f"[yellow]Iteration {current}/{max_iter} ({remaining} left)[/yellow]")
                
                elif chunk_type == "iteration_warning":
                    # Warning when iterations running low
                    remaining = chunk.get("remaining", 0)
                    message = chunk.get("message", "")
                    progress.stop()
                    console.print(f"[yellow]⚠️ {message}[/yellow]")
                    progress.start()
                
                elif chunk_type == "tool_start":
                    tool_name = chunk.get("tool", "unknown")
                    current_tool = tool_name
                    progress.update(task_id, description=f"[blue]🔧 {tool_name}...[/blue]")
                
                elif chunk_type == "tool_progress":
                    # Progress during long-running tools
                    tool = chunk.get("tool", "")
                    prog = chunk.get("progress", 0)
                    message = chunk.get("message", "")
                    progress.update(task_id, description=f"[blue]🔧 {tool}: {message} ({prog:.0%})[/blue]")
                
                elif chunk_type == "tool_complete":
                    tool_name = chunk.get("tool", current_tool or "tool")
                    success = chunk.get("success", True)
                    icon = "✓" if success else "✗"
                    color = "green" if success else "red"
                    console.print(f"  [{color}]{icon}[/{color}] {tool_name}")
                    current_tool = None
                
                elif chunk_type == "observation":
                    # Model's interpretation of tool result
                    observation = chunk.get("observation", "")
                    if observation:
                        console.print(f"[dim]   → {observation}[/dim]")
                
                elif chunk_type == "file_changed":
                    # File system changes
                    path = chunk.get("path", "")
                    action = chunk.get("action", "")
                    lines = chunk.get("lines", 0)
                    
                    icons = {"created": "📝", "modified": "✏️", "deleted": "🗑️"}
                    icon = icons.get(action, "📄")
                    console.print(f"  {icon} {action.capitalize()}: [green]{path}[/green] ({lines} lines)")
                
                elif chunk_type == "command_output":
                    # Terminal command output
                    output = chunk.get("output", "")
                    is_error = chunk.get("is_error", False)
                    if output:
                        color = "red" if is_error else "dim"
                        console.print(f"[{color}]{output}[/{color}]")
                
                elif chunk_type == "message":
                    # Progress/observation messages
                    msg = chunk.get("content", "")
                    if msg:
                        # Check if it's a progress message (starts with emoji or special chars)
                        if msg.startswith(("⚠️", "✓", "→", "💭", "📋")):
                            progress.stop()
                            console.print(f"[dim]{msg}[/dim]")
                            progress.start()
                        else:
                            progress.update(task_id, description=f"[dim]{msg[:60]}...[/dim]" if len(msg) > 60 else f"[dim]{msg}[/dim]")
                
                elif chunk_type == "debug":
                    # Debug messages (only show if verbose mode)
                    # For now, skip debug messages in normal mode
                    pass

                elif chunk_type == "file_tree_updated":
                    # Acknowledged — context_manager now tracks file changes (P10)
                    # file_changed events show the details to the user
                    pass

                elif chunk_type == "command_confirmation_required":
                    # ─────────────────────────────────────────────────────
                    # run_command needs user approval.
                    # Execution HOLDS here until the user responds.
                    # No auto-approve, no auto-deny, no timeout.
                    # ─────────────────────────────────────────────────────
                    cmd = chunk.get("command", "")
                    reason = chunk.get("reason", "")

                    progress.stop()
                    console.print()
                    console.print(
                        Panel(
                            f"[bold yellow]⚡ run_command wants to execute:[/bold yellow]\n\n"
                            f"  [bold white]{cmd}[/bold white]\n\n"
                            f"[dim]Reason: {reason}[/dim]\n\n"
                            "[green]y[/green] = Allow   [red]n[/red] = Deny",
                            title="[bold yellow]Command Confirmation Required[/bold yellow]",
                            border_style="yellow",
                        )
                    )

                    # Await input without blocking the event loop
                    # run_in_executor runs console.input() in a thread,
                    # allowing the event loop to process the gate.wait_for_decision()
                    # coroutine in the executor concurrently.
                    _loop = asyncio.get_event_loop()
                    try:
                        user_choice = await _loop.run_in_executor(
                            None,
                            lambda: console.input(
                                "[bold green]>[/bold green] Allow? [[green]y[/green]/[red]n[/red]]: "
                            ).strip().lower()
                        )
                    except (EOFError, KeyboardInterrupt):
                        user_choice = "n"

                    from services.agent.tools.confirmation_gate import get_confirmation_gate as _get_conf_gate
                    _gate = _get_conf_gate()
                    if user_choice in ("y", "yes", "allow", "a", "1"):
                        console.print("[green]✓ Allowed — executing command...[/green]")
                        _gate.approve()
                    else:
                        console.print("[red]✗ Denied — command will not run.[/red]")
                        _gate.deny()

                    console.print()
                    progress.start()

                
                elif chunk_type == "token":
                    # Streaming response text - collect it
                    token = chunk.get("content", "")
                    response_text += token
                    # Stop the spinner when we start getting response
                    if response_text and len(response_text) < 10:
                        progress.stop()
                
                elif chunk_type == "error":
                    error_msg = chunk.get("message", "Unknown error")
                    console.print(f"[red]❌ Error: {error_msg}[/red]")
                    return
                
                elif chunk_type == "done":
                    # Final summary
                    model = chunk.get("model", "unknown")
                    provider = chunk.get("provider", "unknown")
                    tools_used = chunk.get("tools_used", [])
                    tool_count = chunk.get("tool_calls_count", 0)
                    iterations = chunk.get("iterations", 1)
                    loop_detected = chunk.get("loop_detected", False)
                    max_iterations_reached = chunk.get("max_iterations_reached", False)
                    
                    # Print the response
                    if response_text:
                        console.print()
                        console.print(Markdown(response_text))
                    
                    # Print summary
                    console.print()
                    summary = f"[dim]Model: {provider}/{model}"
                    if tool_count > 0:
                        summary += f" | Tools: {tool_count}"
                    if iterations > 1:
                        summary += f" | Iterations: {iterations}"
                    if loop_detected:
                        summary += " | [yellow]Loop detected[/yellow]"
                    if max_iterations_reached:
                        summary += " | [yellow]Max iterations reached[/yellow]"
                    summary += "[/dim]"
                    console.print(summary)
                    return
        
        except KeyboardInterrupt:
            console.print("\n[yellow]Cancelled[/yellow]")
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")


def run_repl(workspace: str, selected_model: Optional[str] = None) -> None:
    """Run interactive REPL mode with a persistent event loop.
    
    Uses a single asyncio event loop for the entire session so that
    MCP server connections (TCP) survive between queries instead of
    being torn down and rebuilt on every input.
    """
    # One persistent loop for the whole REPL session
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    model_info = f"\n[dim]Model: {selected_model}[/dim]" if selected_model else ""
    console.print(Panel(
        "[bold cyan]🚀 QUASAR AI Editor[/bold cyan]\n\n"
        f"[dim]Workspace: {workspace}[/dim]"
        f"{model_info}\n\n"
        "Type your requests, or:\n"
        "  [green]/help[/green]  - Show commands\n"
        "  [green]/quit[/green]  - Exit",
        border_style="cyan"
    ))

    while True:
        try:
            console.print()
            query = console.input("[bold green]>[/bold green] ").strip()

            if not query:
                continue

            # Handle special commands
            if query.lower() in ["/quit", "/exit", "/q"]:
                console.print("[dim]Goodbye![/dim]")
                break
            elif query.lower() == "/help":
                console.print(Panel(
                    "[bold]Commands:[/bold]\n"
                    "  /quit, /exit, /q - Exit REPL\n"
                    "  /help - Show this help\n\n"
                    "[bold]Examples:[/bold]\n"
                    '  "Create a hello.py file"\n'
                    '  "Explain main.py"\n'
                    '  "Fix the bug in utils.py"\n'
                    '  "List files in current directory"',
                    title="Help",
                    border_style="blue"
                ))
                continue

            # Process query on the persistent loop — MCP connections survive
            loop.run_until_complete(process_query(query, workspace, selected_model))

        except KeyboardInterrupt:
            console.print("\n[dim]Use /quit to exit[/dim]")
        except EOFError:
            console.print("\n[dim]Goodbye![/dim]")
            break

    loop.close()


@app.command()
def main(
    query: Optional[str] = typer.Argument(None, help="Query to process"),
    interactive: bool = typer.Option(False, "--interactive", "-i", help="Run in interactive REPL mode"),
    workspace: str = typer.Option(None, "--workspace", "-w", help="Workspace directory (default: current dir)"),
    model: str = typer.Option(None, "--model", "-m", help="Model to use (format: provider/model-name, e.g., cerebras/qwen-3-32b)"),
    version: Optional[bool] = typer.Option(None, "--version", "-v", callback=version_callback, is_eager=True, help="Show version and exit"),
):
    """
    🚀 QUASAR - AI-powered CLI code editor
    
    Examples:
        quasar "create a hello.py file"
        quasar "explain main.py"
        quasar --interactive
    """
    # Set workspace
    if workspace is None:
        workspace = os.getcwd()
    workspace = str(Path(workspace).resolve())
    
    # Check for API keys
    if not check_api_keys():
        raise typer.Exit(1)
    
    if interactive or query is None:
        # REPL mode
        run_repl(workspace, model)
    else:
        # Single command mode
        asyncio.run(process_query(query, workspace, model))


if __name__ == "__main__":
    app()
