# Available Tools

This document describes the tools available to nanobot.

## File Operations

### read_file
Read the contents of a file.
```
read_file(path: str) -> str
```

### write_file
Write content to a file (creates parent directories if needed).
```
write_file(path: str, content: str) -> str
```

### edit_file
Edit a file by replacing specific text.
```
edit_file(path: str, old_text: str, new_text: str) -> str
```

### list_dir
List contents of a directory.
```
list_dir(path: str) -> str
```

## Shell Execution

### exec
Execute a shell command and return output.
```
exec(command: str, working_dir: str = None) -> str
```

**Safety Notes:**
- Commands have a configurable timeout (default 60s)
- Dangerous commands are blocked (rm -rf, format, dd, shutdown, etc.)
- Output is truncated at 10,000 characters
- Shell write operations (>, >>, tee, cp, mv, sed -i) targeting `protectedPaths` are blocked

## Web Access

### web_search
Search the web using Brave Search API.
```
web_search(query: str, count: int = 5) -> str
```

Returns search results with titles, URLs, and snippets. Requires `tools.web.search.apiKey` in config.

### web_fetch
Fetch and extract main content from a URL.
```
web_fetch(url: str, extractMode: str = "markdown", maxChars: int = 50000) -> str
```

**Notes:**
- Content is extracted using readability
- Supports markdown or plain text extraction
- Output is truncated at 50,000 characters by default

## Communication

### message
Send a message to the user (used internally).
```
message(content: str, channel: str = None, chat_id: str = None) -> str
```

## Background Tasks

### spawn
Spawn a subagent to handle a task in the background.
```
spawn(task: str, label: str = None) -> str
```

Use for complex or time-consuming tasks that can run independently. The subagent will complete the task and report back when done.

## Scheduled Reminders (Cron)

Use the `exec` tool to create scheduled reminders with `nanobot cron add`:

### Set a recurring reminder
```bash
# Every day at 9am
nanobot cron add --name "morning" --message "Good morning! ☀️" --cron "0 9 * * *"

# Every 2 hours
nanobot cron add --name "water" --message "Drink water! 💧" --every 7200
```

### Set a one-time reminder
```bash
# At a specific time (ISO format)
nanobot cron add --name "meeting" --message "Meeting starts now!" --at "2025-01-31T15:00:00"
```

### Manage reminders
```bash
nanobot cron list              # List all jobs
nanobot cron remove <job_id>   # Remove a job
```

## Heartbeat Task Management

The `HEARTBEAT.md` file in the workspace is checked every 30 minutes.
Use file operations to manage periodic tasks:

### Add a heartbeat task
```python
# Append a new task
edit_file(
    path="HEARTBEAT.md",
    old_text="## Example Tasks",
    new_text="- [ ] New periodic task here\n\n## Example Tasks"
)
```

### Remove a heartbeat task
```python
# Remove a specific task
edit_file(
    path="HEARTBEAT.md",
    old_text="- [ ] Task to remove\n",
    new_text=""
)
```

### Rewrite all tasks
```python
# Replace the entire file
write_file(
    path="HEARTBEAT.md",
    content="# Heartbeat Tasks\n\n- [ ] Task 1\n- [ ] Task 2\n"
)
```

---

## Adding Custom Tools (Self-Extending)

You can create your own custom tools at runtime! Place Python files in your workspace's `tools/` directory and they will be **automatically loaded** on the next message — no restart needed.

### How to create a custom tool

1. Create a `.py` file in `{workspace}/tools/` (e.g. `tools/my_tool.py`)
2. Define exactly **one** class that inherits from `nanobot.agent.tools.base.Tool`
3. Implement the required properties and method: `name`, `description`, `parameters`, `execute`
4. The tool will be available immediately on the next message

### Template

```python
from typing import Any
from nanobot.agent.tools.base import Tool

class MyCustomTool(Tool):
    @property
    def name(self) -> str:
        return "my_tool"  # unique name, must not conflict with built-in tools

    @property
    def description(self) -> str:
        return "Describe what this tool does."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "param1": {
                    "type": "string",
                    "description": "Description of param1"
                }
            },
            "required": ["param1"]
        }

    async def execute(self, param1: str, **kwargs: Any) -> str:
        # Your tool logic here
        return f"Result: {param1}"
```

### Rules and restrictions

- **One tool per file** — only the first `Tool` subclass found is loaded
- **Files starting with `_` are skipped** (e.g. `_helpers.py`)
- **Cannot override built-in tools** — if the tool name conflicts with an existing tool, it is rejected
- **Safety scan** — before loading, the source code is scanned for forbidden patterns. Files containing any of the following are **rejected**:
  - `subprocess`, `os.system()`, `os.popen()`, `os.exec*()`, `os.spawn*()`
  - `os.remove()`, `os.unlink()`, `os.rmdir()`, `shutil.rmtree()`
  - `open()`, `pathlib.Path()`
  - `eval()`, `exec()`, `compile()`, `__import__()`, `importlib`
  - `ctypes`, `socket`
- **Protected paths enforced** — custom tools receive the same `protectedPaths` restrictions as built-in tools
- For file I/O, use the built-in `read_file` / `write_file` / `edit_file` tools instead of direct Python file operations

### Example: Timestamp tool

Create `{workspace}/tools/timestamp.py`:

```python
from datetime import datetime
from typing import Any
from nanobot.agent.tools.base import Tool

class TimestampTool(Tool):
    @property
    def name(self) -> str:
        return "timestamp"

    @property
    def description(self) -> str:
        return "Get the current UTC timestamp."

    @property
    def parameters(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}}

    async def execute(self, **kwargs: Any) -> str:
        return datetime.utcnow().isoformat() + "Z"
```

This tool will be available on the next message you send.
