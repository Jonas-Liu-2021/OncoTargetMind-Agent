"""LLM client — DeepSeek API."""

import os
import sys
import requests

MODELS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models")

DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-v4-flash"


def _load_dotenv() -> dict[str, str]:
    """Load .env file from project root."""
    env_file = os.path.join(os.path.dirname(MODELS_DIR), ".env")
    result = {}
    if os.path.isfile(env_file):
        with open(env_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    k, v = line.split("=", 1)
                    result[k.strip().lstrip("﻿")] = v.strip().strip('"').strip("'")
    return result


def _get_deepseek_key() -> str | None:
    """Return DeepSeek API key from env var or .env file."""
    key = os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("DEEPSEEK_KEY")
    if key:
        return key
    return _load_dotenv().get("DEEPSEEK_API_KEY") or _load_dotenv().get("DEEPSEEK_KEY")


def generate_response(messages: list[dict], max_new_tokens: int = 512) -> str:
    """Send chat messages to DeepSeek API and return the response."""
    key = _get_deepseek_key()
    if not key:
        raise RuntimeError("DEEPSEEK_API_KEY not found. Set it in environment or .env file.")

    resp = requests.post(
        f"{DEEPSEEK_BASE_URL}/v1/chat/completions",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={
            "model": DEEPSEEK_MODEL,
            "messages": messages,
            "max_tokens": max_new_tokens,
            "temperature": 0.1,
            "top_p": 0.9,
            "stream": False,
        },
        timeout=60,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"DeepSeek API error {resp.status_code}: {resp.text[:500]}")

    data = resp.json()
    return data["choices"][0]["message"]["content"].strip()
