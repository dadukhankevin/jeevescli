from typing import Optional, Dict
from .base_cli import Jeeves, TodoTool
from .tools import FindLikeTool, SetFileContentTool, ReadFileTool
from .terminal_tool import TerminalTool
from openai import OpenAI
import dotenv
from .config import (
    load_config,
    build_extra_body,
)
from .commands import CommandRouter, CommandContext, register_builtin_commands

dotenv.load_dotenv()


def _build_client(cfg: Dict[str, Optional[str]]):
    return OpenAI(
        api_key=cfg.get("api_key"),
        base_url=cfg.get("base_url"),
    )

banner = """

    ░█████ ░██████████ ░██████████ ░██    ░██ ░██████████   ░██████   
      ░██  ░██         ░██         ░██    ░██ ░██          ░██   ░██  
      ░██  ░██         ░██         ░██    ░██ ░██         ░██         
      ░██  ░█████████  ░█████████  ░██    ░██ ░█████████   ░████████  
░██   ░██  ░██         ░██          ░██  ░██  ░██                 ░██ 
░██   ░██  ░██         ░██           ░██░██   ░██          ░██   ░██  
 ░██████   ░██████████ ░██████████    ░███    ░██████████   ░██████   
                                                                      
                                                                      
Stateless, small context, high leverage AI assistant.
"""

tools = [
    TodoTool(dependencies=[]),
    FindLikeTool(folder="."),
    SetFileContentTool(dependencies=[]),
    ReadFileTool(dependencies=[]),
    TerminalTool(dependencies=[])
]

def _apply_cfg(jeeves: Jeeves, cfg: Dict[str, Optional[str]], default_model: str) -> None:
    # Hot-reload client and settings on the existing instance
    jeeves.client = _build_client(cfg)
    jeeves.model = cfg.get("model") or default_model
    jeeves.extra_body = build_extra_body(cfg.get("provider"))

def main():
    cfg = load_config()
    default_model = "qwen/qwen3-code"
    client = _build_client(cfg)
    print(banner)
    jeeves = Jeeves(
        client,
        prime_directive="Ask user what to do.",
        model=cfg.get("model") or default_model,
        extra_body=build_extra_body(cfg.get("provider")),
        on_chunk=lambda x: print(x, end="", flush=True),
        tools=tools,
    )

    # Command router
    router = CommandRouter()
    register_builtin_commands(router)
    ctx = CommandContext(jeeves=jeeves, default_model=default_model, apply_config=_apply_cfg)

    while True:
        inp = input("Enter a prompt (or /help): ").strip()
        if not inp:
            # Reuse existing prime directive if user presses Enter
            if jeeves.prime_directive:
                jeeves.respond_once()
                print()
            continue
        if inp.startswith("/"):
            router.dispatch(ctx, inp)
            continue
        # Non-command: set directive then run a single response
        jeeves.prime_directive = inp
        jeeves.respond_once()
        print()


if __name__ == "__main__":
    main()
