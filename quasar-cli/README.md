# 🚀 QUASAR - AI-Powered CLI Code Editor

An intelligent command-line code editor that can understand your codebase, generate code, fix bugs, and execute tasks using AI.

**📚 [Documentation](https://sunilk240.github.io/quasar-cli/)**

## Installation

```bash
pip install quasar-ai
```

## Setup API Keys

**IMPORTANT**: You must provide your own API keys. QUASAR does not include any API keys.

### Option 1: Using `.env` file (Recommended)

Create a `.env` file in your project directory:

```env
# Groq (recommended - fast inference)
GROQ_API_KEY_1=gsk_your_key_here
GROQ_API_KEY_2=gsk_your_second_key_here

# Cerebras
CEREBRAS_API_KEY_1=csk_your_key_here
CEREBRAS_API_KEY_2=csk_your_second_key_here

# Ollama runs locally - no API key needed
# Default: http://localhost:11434

# Web Search (optional but recommended)
# QUASAR has multiple web tools with fallback support
# Get free key at: https://tavily.com
TAVILY_API_KEY=tvly_your_key_here
```

### Option 2: Using Environment Variables

```bash
# Groq
export GROQ_API_KEY_1="gsk_your_key_here"
export GROQ_API_KEY_2="gsk_your_second_key_here"

# Cerebras
export CEREBRAS_API_KEY_1="csk_your_key_here"
```

### Multiple Keys

You can add multiple keys per provider (e.g., `GROQ_API_KEY_1`, `GROQ_API_KEY_2`, `GROQ_API_KEY_3`). If a key hits rate limits, QUASAR automatically rotates to the next available key.

**Get free API keys:**
- Groq: https://console.groq.com
- Cerebras: https://cloud.cerebras.ai

## Usage

### Interactive Mode (REPL)
```bash
quasar
# or
quasar --interactive
```

### Single Command
```bash
quasar "create a hello.py file that prints Hello World"
quasar "explain main.py"
quasar "fix the bug in utils.py"
quasar "list files in current directory"
```

### Specify Workspace
```bash
quasar --workspace /path/to/project "add tests for api.py"
```

### Custom Model Selection

By default, QUASAR automatically selects the best model. You can override with `--model`:

```bash
quasar --model cerebras/qwen-3-32b "explain this code"
quasar --model groq/llama-3.3-70b-versatile "create a REST API"
quasar --model ollama/qwen2.5-coder:7b "fix the bug"
```

## Project Configuration (.quasar/)

On first run, QUASAR creates a `.quasar/` directory in your workspace with project-specific configuration:

```
.quasar/
├── context.md    # Your project rules & preferences
├── memory.json   # Session history & recent files
├── mcp.json      # MCP server configuration
├── hooks/        # Custom lifecycle hooks (templates provided)
└── backups/      # Automatic file backups
```

### context.md

Customize QUASAR's behavior for your project by editing `.quasar/context.md`:

- **Project Description**: Help QUASAR understand your project goals
- **Code Style**: Your preferred conventions (type hints, naming, etc.)
- **Important Files**: Key files QUASAR should be aware of
- **Project Rules**: Custom rules for QUASAR to follow

### hooks/

Add custom Python hooks to control QUASAR's behavior:
- `PRE_TOOL_USE`: Run before any tool execution
- `POST_TOOL_USE`: Run after tool execution
- `ON_COMPLETE`: Run when task completes

Templates are provided in `.quasar/hooks/` - rename `.template` files to `.py` to activate.

### mcp.json

QUASAR supports [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) for extending tool capabilities with external servers.

```json
{
  "mcpServers": {
    "my-server": {
      "command": ["python", "my_mcp_server.py"],
      "description": "Custom MCP server"
    }
  }
}
```

## Backup & Recovery

QUASAR automatically backs up files before modifying or deleting them.

- **Location**: `.quasar/backups/`
- **Auto-cleanup**: Last 50 backups kept
- **Restore**: Ask QUASAR to "list backups" or "restore backup"

## Security

QUASAR blocks access to sensitive files:
- `.env` files (all variants)
- SSH keys (`.ssh/id_rsa`, etc.)
- AWS credentials (`.aws/credentials`)
- Certificates (`.pem`, `.key`, `.p12`, `.pfx`)

## Updating

```bash
pip install --upgrade quasar-ai
```

