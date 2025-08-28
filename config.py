import json
import os
from typing import Dict, Optional


CONFIG_DIR_NAME = "jeevescli"
CONFIG_FILE_NAME = "config.json"


def _get_config_dir() -> str:
    xdg_home = os.environ.get("XDG_CONFIG_HOME")
    if xdg_home:
        return os.path.join(xdg_home, CONFIG_DIR_NAME)
    # Default to ~/.config on macOS/Linux
    return os.path.join(os.path.expanduser("~/.config"), CONFIG_DIR_NAME)


def get_config_path() -> str:
    return os.path.join(_get_config_dir(), CONFIG_FILE_NAME)


def _ensure_dir_exists(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def load_config() -> Dict[str, Optional[str]]:
    """Load persisted config. Falls back to env vars. Returns keys:
    model, provider, base_url, api_key
    """
    cfg_path = get_config_path()
    data: Dict[str, Optional[str]] = {
        "model": None,
        "provider": None,
        "base_url": None,
        "api_key": None,
    }

    # Load env defaults first
    env_api_key = os.getenv("API_KEY")
    
    env_base_url = os.getenv("BASE_URL")

    data["api_key"] = env_api_key or ""
    data["base_url"] = env_base_url or ""

    # Overlay file config
    try:
        with open(cfg_path, "r", encoding="utf-8") as f:
            file_data = json.load(f)
            if isinstance(file_data, dict):
                for key in data.keys():
                    if key in file_data and file_data[key]:
                        data[key] = file_data[key]
    except FileNotFoundError:
        pass
    except Exception:
        # Ignore malformed config; user can overwrite via /api
        pass

    return data


def save_config(values: Dict[str, Optional[str]]) -> str:
    """Persist provided values merged with existing config. Returns file path."""
    current = load_config()
    # Merge
    for key, value in values.items():
        if key in current:
            current[key] = value

    cfg_dir = _get_config_dir()
    _ensure_dir_exists(cfg_dir)
    cfg_path = get_config_path()
    with open(cfg_path, "w", encoding="utf-8") as f:
        json.dump(current, f, indent=2)
    return cfg_path


def format_config_for_display(cfg: Dict[str, Optional[str]]) -> str:
    def mask(value: Optional[str]) -> str:
        if not value:
            return "(not set)"
        if len(value) <= 6:
            return "******"
        return value[:3] + "…" + value[-3:]

    lines = [
        f"model:     {cfg.get('model') or '(not set)'}",
        f"provider:  {cfg.get('provider') or '(not set)'}",
        f"base_url:  {cfg.get('base_url') or '(not set)'}",
        f"api_key:   {mask(cfg.get('api_key'))}",
    ]
    return "\n".join(lines)


def build_extra_body(provider: Optional[str]) -> dict:
    if not provider:
        return {}
    # Prefer the given provider; allow fallbacks
    return {
        "provider": {
            "order": [provider],
            "allow_fallbacks": True,
        }
    }


