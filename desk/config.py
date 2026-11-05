"""Load settings.yaml and .env into an attribute-style object."""
from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent


def _ns(obj):
    if isinstance(obj, dict):
        return SimpleNamespace(**{k: _ns(v) for k, v in obj.items()})
    if isinstance(obj, list):
        return [_ns(v) for v in obj]
    return obj


def load_settings(path: str | Path | None = None) -> SimpleNamespace:
    load_dotenv(ROOT / ".env")
    path = Path(path or os.getenv("DESK_SETTINGS", ROOT / "config" / "settings.yaml"))
    with open(path, encoding="utf-8") as f:
        settings = _ns(yaml.safe_load(f))

    if settings.mode not in ("paper", "live"):
        raise ValueError(f"mode must be paper or live, got {settings.mode!r}")
    if settings.mode == "live" and os.getenv("ALLOW_LIVE") != "1":
        raise RuntimeError("mode: live needs ALLOW_LIVE=1 in .env. Finish the paper month first.")
    return settings


def resolve(path: str) -> Path:
    """Paths in settings are relative to the project root."""
    p = Path(path)
    return p if p.is_absolute() else ROOT / p
