from __future__ import annotations

from pathlib import Path

import yaml

from .config import WATCHLIST_PATH


def watchlist_names(path: Path | None = None) -> set[str]:
    path = path or WATCHLIST_PATH
    if not path.exists():
        return set()
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    out: set[str] = set()
    for item in data.get("companies") or []:
        if isinstance(item, str):
            out.add(item.lower())
        elif isinstance(item, dict) and item.get("name"):
            out.add(str(item["name"]).lower())
    return out


def is_watchlist_company(company: str) -> bool:
    return (company or "").strip().lower() in watchlist_names()
