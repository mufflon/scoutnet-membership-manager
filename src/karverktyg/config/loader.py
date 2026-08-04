"""
Load, migrate and validate the single kår-config JSON (§13).

The config is optional: with no file, the tool runs on inferred avdelningar and
the universal routing rule (``default_config``). A present file carries a
``version``; ``migrate`` brings older versions forward before validation, and a
stray ``$schema`` reference (for editor/independent validation) is ignored.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from karverktyg.config.models import CONFIG_VERSION, KarConfig


class ConfigError(RuntimeError):
    """Configuration is malformed or fails validation."""


def default_config() -> KarConfig:
    """The zero-config default: no declared avdelningar, everything inferred."""
    return KarConfig()


def json_schema() -> dict:
    """
    The JSON Schema for a kår config, for independent validation (§13).

    Single source of truth: the committed ``docs/karverktyg.schema.json`` is this,
    and a test asserts they match so it never drifts from the model.
    """
    schema = KarConfig.model_json_schema()
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["title"] = "karverktyg kår-config"
    return schema


def migrate(raw: dict) -> dict:
    """
    Bring a raw config dict forward to the current version (§13).

    Each step upgrades one version to the next; add a branch here whenever the
    schema changes so old files keep loading. Unknown/newer versions pass through
    to validation, which reports the mismatch.
    """
    raw = dict(raw)
    raw.pop("$schema", None)  # editor/CLI validation hint, not a model field
    version = raw.get("version", CONFIG_VERSION)
    # (No migrations yet — v1 is the first versioned schema.)
    raw["version"] = version
    return raw


def load_config(path: str | Path) -> KarConfig:
    """Load the config at ``path``; a missing file yields the zero-config default."""
    p = Path(path)
    if not p.exists():
        return default_config()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ConfigError(f"invalid JSON in {p}: {e}") from e
    try:
        return KarConfig.model_validate(migrate(data))
    except ValidationError as e:
        raise ConfigError(f"invalid configuration in {p}:\n{e}") from e
