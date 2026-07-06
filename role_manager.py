# role_manager.py
import json
import os
from .config import ROLES_FILE, SYSTEM_PROMPT_OVERRIDE

_ROLE_PROMPTS = None

def load_role_prompts() -> dict:
    global _ROLE_PROMPTS
    if _ROLE_PROMPTS is None:
        if not os.path.exists(ROLES_FILE):
            _ROLE_PROMPTS = {"default": "Ты — полезный помощник. Отвечай на русском языке."}
        else:
            with open(ROLES_FILE, "r", encoding="utf-8") as f:
                _ROLE_PROMPTS = json.load(f)
    return _ROLE_PROMPTS

def get_system_prompt(role_name: str) -> str:
    if SYSTEM_PROMPT_OVERRIDE:
        return SYSTEM_PROMPT_OVERRIDE
    prompts = load_role_prompts()
    return prompts.get(role_name.lower(), prompts.get("default", "Ты — полезный помощник. Отвечай на русском языке."))
