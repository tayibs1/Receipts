"""Shared setup: project root, .env loading, key status. Never prints key values."""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
KEYS = ("ANTHROPIC_API_KEY", "LINKUP_API_KEY")


def load_env(path: Path | None = None) -> None:
    """Load KEY=VALUE lines into os.environ (existing variables win)."""
    path = path or ROOT / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        v = v.strip().strip('"').strip("'")
        if v:
            os.environ.setdefault(k.strip(), v)


def key_status() -> dict[str, bool]:
    return {name: bool(os.environ.get(name)) for name in KEYS}


def print_key_status() -> None:
    for name, found in key_status().items():
        print(f"{name}: {'key found' if found else 'MISSING'}")
