from __future__ import annotations

import os
from typing import Any


DEFAULT_MODEL = "gemini-2.5-flash-lite"
DEFAULT_API_VERSION = "2025-10"


def load_dotenv(path: str = ".env") -> None:
    """Tiny .env loader so the free rules mode has no package dependencies."""
    if not os.path.exists(path):
        return

    with open(path, "r", encoding="utf-8") as env_file:
        for raw_line in env_file:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            os.environ.setdefault(key, value)


def get_app_settings() -> dict[str, Any]:
    return {
        "max_products": int(os.getenv("MAX_PRODUCTS", "10")),
        "provider": os.getenv("AI_PROVIDER", "gemini"),
        "model": os.getenv("AI_MODEL", os.getenv("OPENAI_MODEL", DEFAULT_MODEL)),
        "api_version": os.getenv("SHOPIFY_API_VERSION", DEFAULT_API_VERSION),
    }


load_dotenv()
