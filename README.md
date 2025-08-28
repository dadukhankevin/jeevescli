```
    ░█████ ░██████████ ░██████████ ░██    ░██ ░██████████   ░██████   
      ░██  ░██         ░██         ░██    ░██ ░██          ░██   ░██  
      ░██  ░██         ░██         ░██    ░██ ░██         ░██         
      ░██  ░█████████  ░█████████  ░██    ░██ ░█████████   ░████████  
░██   ░██  ░██         ░██          ░██  ░██  ░██                 ░██ 
░██   ░██  ░██         ░██           ░██░██   ░██          ░██   ░██  
 ░██████   ░██████████ ░██████████    ░███    ░██████████   ░██████   
```                                                              

# Jeeves
## About

Most coding assistants keep growing message histories and context windows, which is inefficient. Jeeves only keeps the latest message in context. This design focuses on the current task and relevant code, not the entire project history.

Despite this, Jeeves can still plan, manage TODO lists, and solve problems over multiple steps without needing conversation history.

Jeeves uses `pysublime` for code search and retrieval. It embeds code line by line and clusters results to return only the most relevant segments, reducing noise and missing content.

## Installation

Install Jeeves from PyPI:

```bash
pip install jeevescli
```

Now `jeeves` is available globally from any directory.

### Development Installation

For development or to get the latest features:

```bash
git clone https://github.com/dadukhankevin/jeevescli
cd jeevescli
pip install -e .
```

## Usage
1. Set API key: `/api api_key sk-your-key-here`
2. Run `jeeves` from anywhere
3. Profit

### Configure API at runtime
Use the in-CLI `/api` command to view or change model/provider/base_url/api_key. Settings persist to `~/.config/jeevescli/config.json` and apply immediately.

Examples:

```text
/api                # show current settings and config file location
/api show           # same as above

/api model openai/gpt-oss-120b provider Groq
/api base_url https://api.example.com/openai/v1 api_key sk-xxxx

# You can also use key=value form
/api model=gpt-4o-mini provider=Cerebras

# Unset a value
/api provider unset
```

Notes:
- Values set via `/api` override environment variables and are remembered across runs.
- Env vars `API_KEY` and `BASE_URL` are used as defaults if nothing is persisted.

## Creating Your Own Assistant

You can use Jeeves as a library to create your own AI assistants. Here's a minimal example:

### Basic Assistant

```python
from openai import OpenAI
from jeevescli.base_cli import Jeeves, TodoTool
from jeevescli.tools import ReadFileTool, SetFileContentTool

# Set up OpenAI client
client = OpenAI(api_key="your-api-key-here")

# Define available tools
tools = [
    TodoTool(dependencies=[]),
    ReadFileTool(dependencies=[]),
    SetFileContentTool(dependencies=[])
]

# Create your assistant
assistant = Jeeves(
    client=client,
    prime_directive="You are a helpful coding assistant.",
    model="gpt-4.1",
    tools=tools,
    on_chunk=lambda x: print(x, end="", flush=True)
)

# Use the assistant
assistant.prime_directive = "Help me write a Python script"
assistant.respond_once()
```

## How to Create Custom Tools

Tools are the core extension mechanism in Jeeves. Each tool defines an XML interface that the AI can use to perform specific actions.

### Tool Structure

Every tool must inherit from the `Tool` base class and implement these key components:

```python
from jeevescli.base_cli import Tool
from typing import Dict, Any, List

class MyTool(Tool):
    # Required: XML closing tag that signals tool completion
    stop_token: str = "</my_tool>"
    
    # Required: Whether this tool stops AI generation (True) or continues (False)
    stopping: bool = True
    
    # Optional: Other tools this tool depends on
    dependencies: List[Tool] = []
    
    @property
    def system_description(self) -> str:
        """XML format description shown to the AI"""
        return """
        <my_tool>
            <param1>description of parameter 1</param1>
            <param2>description of parameter 2</param2>
        </my_tool>
        
        Explain what this tool does and provide examples.
        """
    
    @property
    def status_prompt(self) -> str:
        """Optional: Current state info shown to AI (e.g., "3 files open")"""
        return ""
    
    def execute(self, data: Dict[str, Any]) -> str:
        """Process the tool call and return a result message"""
        param1 = data.get('param1', '')
        param2 = data.get('param2', '')
        # Your tool logic here
        return "Tool execution result"
```

### Tool Types

**Stopping Tools** (`stopping=True`): AI waits for tool completion before continuing
- File operations, terminal commands, calculations
- Use when the result affects next AI response

**Non-stopping Tools** (`stopping=False`): AI continues while tool runs in background  
- Logging, notifications, state updates
- Use for side effects that don't need immediate feedback

### Example: File Search Tool

```python
import os
import glob
from jeevescli.base_cli import Tool
from typing import Dict, Any

class FileSearchTool(Tool):
    stop_token: str = "</search_files>"
    stopping: bool = True
    
    @property
    def system_description(self) -> str:
        return """
        <search_files>
            <pattern>file pattern (e.g., *.py, **/*.js, src/**)</pattern>
            <max_results>maximum number of files to return (optional, default 10)</max_results>
        </search_files>
        
        Search for files matching a glob pattern. Use ** for recursive search.
        Examples:
        - <search_files><pattern>*.py</pattern></search_files>
        - <search_files><pattern>src/**/*.js</pattern><max_results>20</max_results></search_files>
        """
    
    def execute(self, data: Dict[str, Any]) -> str:
        pattern = data.get('pattern', '')
        max_results = int(data.get('max_results', 10))
        
        if not pattern:
            return "Error: No search pattern provided"
        
        try:
            files = glob.glob(pattern, recursive=True)[:max_results]
            if not files:
                return f"No files found matching pattern: {pattern}"
            
            result = f"Found {len(files)} files:\n"
            for file in files:
                size = os.path.getsize(file) if os.path.isfile(file) else 0
                result += f"  {file} ({size} bytes)\n"
            
            return result
        except Exception as e:
            return f"Error searching files: {e}"
```

### Example: Stateful Tool with Status

```python
class NotesTool(Tool):
    stop_token: str = "</notes>"
    stopping: bool = False  # Non-stopping tool
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.notes: List[str] = []
    
    @property
    def system_description(self) -> str:
        return """
        <notes>
            <add>note content to add</add>
            <remove>note content to remove</remove>
            <clear>true</clear>
        </notes>
        
        Manage a list of notes. You can add notes, remove specific notes, or clear all notes.
        """
    
    @property
    def status_prompt(self) -> str:
        if not self.notes:
            return "Notes: (empty)"
        
        status = f"Notes ({len(self.notes)}):\n"
        for i, note in enumerate(self.notes[-5:], 1):  # Show last 5
            status += f"  {i}. {note}\n"
        return status
    
    def execute(self, data: Dict[str, Any]) -> str:
        add_note = data.get('add')
        remove_note = data.get('remove')
        clear_all = data.get('clear')
        
        if clear_all:
            count = len(self.notes)
            self.notes.clear()
            return f"Cleared {count} notes"
        
        if add_note:
            self.notes.append(add_note)
            return f"Added note: {add_note}"
        
        if remove_note and remove_note in self.notes:
            self.notes.remove(remove_note)
            return f"Removed note: {remove_note}"
        
        return "No action taken"
```

### Best Practices

1. **Clear XML Interface**: Make parameter names and structure intuitive
2. **Good Examples**: Show common usage patterns in `system_description`
3. **Error Handling**: Return helpful error messages, don't raise exceptions
4. **State Management**: Use `status_prompt` to show current state to AI
5. **Dependencies**: List tools that must be available for this tool to work
6. **Performance**: Keep `execute()` fast; use background tasks for slow operations

### Using Your Tools

```python
# Create tools with any initialization needed
search_tool = FileSearchTool(dependencies=[])
notes_tool = NotesTool(dependencies=[])

# Add to assistant
tools = [TodoTool(dependencies=[]), search_tool, notes_tool]
assistant = Jeeves(client, "You are a helpful assistant", tools=tools)
```

### Key Components

- **Jeeves**: Main assistant class that handles conversation flow
- **Tool**: Base class for creating custom tools with XML-based interfaces
- **TodoTool**: Built-in task management
- **FindLikeTool**: Semantic code search using embeddings
- **ReadFileTool/SetFileContentTool**: File operations
- **TerminalTool**: Execute shell commands

The assistant automatically:
- Manages conversation context (stateless design)
- Parses and executes tool calls
- Provides tool status in prompts
- Handles streaming responses
