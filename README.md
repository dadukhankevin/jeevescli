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

### Custom Tool Example

Create your own tools by extending the `Tool` class:

```python
from jeevescli.base_cli import Tool
from typing import Dict, Any

class CalculatorTool(Tool):
    stop_token: str = "</calc>"
    stopping: bool = True
    
    @property
    def system_description(self) -> str:
        return """
        <calc>
            <expression>mathematical expression to evaluate</expression>
        </calc>
        
        Use this to perform calculations. Example: <calc><expression>2 + 2 * 3</expression></calc>
        """
    
    def execute(self, data: Dict[str, Any]) -> str:
        expression = data.get('expression', '')
        try:
            result = eval(expression)  # Note: eval() is unsafe for production
            return f"Result: {result}"
        except Exception as e:
            return f"Error: {e}"

# Use your custom tool
tools = [TodoTool(dependencies=[]), CalculatorTool(dependencies=[])]
assistant = Jeeves(client, "You can help with math", tools=tools)
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
