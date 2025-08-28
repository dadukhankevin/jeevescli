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
