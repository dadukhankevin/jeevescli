import shlex
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

from .base_cli import Jeeves
from .config import (
    load_config,
    save_config,
    get_config_path,
)


@dataclass
class CommandContext:
    jeeves: Jeeves
    default_model: str
    apply_config: Callable[[Jeeves, Dict[str, Optional[str]], str], None]


@dataclass
class Command:
    name: str
    summary: str
    usage: str
    handler: Callable[[CommandContext, List[str]], None]


class CommandRouter:
    def __init__(self) -> None:
        self._commands: Dict[str, Command] = {}

    def register(self, command: Command) -> None:
        self._commands[command.name] = command

    def dispatch(self, ctx: CommandContext, raw: str) -> bool:
        if not raw.startswith("/"):
            return False
        parts = shlex.split(raw)
        cmd = parts[0][1:]
        args = parts[1:]
        if cmd in self._commands:
            self._commands[cmd].handler(ctx, args)
            return True
        print(f"Unknown command: /{cmd}. Try /help")
        return True

    def help_text(self) -> str:
        lines = ["Available commands:"]
        for name in sorted(self._commands.keys()):
            lines.append(f"  /{name}")
        lines.append("Use '/help <name>' for usage.")
        return "\n".join(lines)

    def get(self, name: str) -> Optional[Command]:
        return self._commands.get(name)


def _handle_api(ctx: CommandContext, _args: List[str]) -> None:
    cfg = load_config()
    current_model = cfg.get("model") or "(not set)"
    current_provider = cfg.get("provider") or "(not set)"
    current_base_url = cfg.get("base_url") or "(not set)"
    current_api_key = cfg.get("api_key")
    api_key_display = "(hidden)" if current_api_key else "(not set)"

    print("\nAPI configuration (choose a number to edit):")
    print(f"  1) model:    {current_model}")
    print(f"  2) provider: {current_provider}")
    print(f"  3) base_url: {current_base_url}")
    print(f"  4) api_key:  {api_key_display}")
    print(f"     file:     {get_config_path()}")

    try:
        choice = input("Select 1-4 (Enter to cancel): ").strip()
    except EOFError:
        choice = ""

    if choice not in {"1", "2", "3", "4"}:
        return

    key_map = {
        "1": "model",
        "2": "provider",
        "3": "base_url",
        "4": "api_key",
    }
    selected_key = key_map[choice]

    # Prompt for new value
    if selected_key == "api_key":
        try:
            import getpass
            new_value = getpass.getpass("New api_key (Enter to keep, 'unset' to clear): ").strip()
        except (EOFError, KeyboardInterrupt):
            new_value = ""
    else:
        new_value = input(f"New {selected_key} (Enter to keep, 'unset' to clear): ").strip()

    if new_value == "":
        print("No changes.")
        return

    if new_value.lower() in {"unset", "none", "-"}:
        updated_values: Dict[str, Optional[str]] = {selected_key: None}
    else:
        updated_values = {selected_key: new_value}

    path = save_config(updated_values)
    updated = load_config()
    ctx.apply_config(ctx.jeeves, updated, ctx.default_model)

    # Show concise confirmation
    after_model = updated.get("model") or "(not set)"
    after_provider = updated.get("provider") or "(not set)"
    after_base_url = updated.get("base_url") or "(not set)"
    after_api_key = "(hidden)" if updated.get("api_key") else "(not set)"
    print("\nUpdated.")
    print(f"  1) model:    {after_model}")
    print(f"  2) provider: {after_provider}")
    print(f"  3) base_url: {after_base_url}")
    print(f"  4) api_key:  {after_api_key}")
    print(f"  saved to:    {path}\n")


def _handle_help(router: CommandRouter, args: List[str]) -> None:
    if not args:
        print(router.help_text())
        return
    name = args[0].lstrip("/")
    cmd = router.get(name)
    if not cmd:
        print(f"No such command '/{name}'.")
        return
    print(f"/{cmd.name} — {cmd.summary}\nUsage:\n  {cmd.usage}")


def register_builtin_commands(router: CommandRouter) -> None:
    router.register(
        Command(
            name="api",
            summary="Show or set model, provider, base_url, api_key",
            usage="/api [show] | [model <val>] [provider <val>] [base_url <val>] [api_key <val>]",
            handler=_handle_api,
        )
    )

    def help_handler(_ctx: CommandContext, args: List[str]) -> None:
        _handle_help(router, args)

    router.register(
        Command(
            name="help",
            summary="List available commands or show help for one",
            usage="/help [command]",
            handler=help_handler,
        )
    )


