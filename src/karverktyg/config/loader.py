"""Load and validate the kår configuration JSON (§13)."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from karverktyg.config.models import KarConfig


class ConfigError(RuntimeError):
    """Configuration is missing, malformed, or fails validation."""


def load_config(path: str | Path) -> KarConfig:
    p = Path(path)
    if not p.exists():
        raise ConfigError(f"config file not found: {p}")
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ConfigError(f"invalid JSON in {p}: {e}") from e
    try:
        return KarConfig.model_validate(data)
    except ValidationError as e:
        raise ConfigError(f"invalid configuration in {p}:\n{e}") from e
