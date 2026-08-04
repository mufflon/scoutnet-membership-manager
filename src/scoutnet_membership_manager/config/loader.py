"""
Load, migrate and validate the single kår-config JSON (§13).

The config is optional: with no file, the tool runs on inferred avdelningar and
the universal routing rule (``default_config``). The file-format version lives at
the file root (``schema_version``); ``migrate`` here just strips editor/comment
keys (``$schema``, ``_comment``) from the kår block before validation.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from scoutnet_membership_manager.config.models import KarConfig


class ConfigError(RuntimeError):
    """Configuration is malformed or fails validation."""


def default_config() -> KarConfig:
    """The zero-config default: no declared avdelningar, everything inferred."""
    return KarConfig()


def json_schema() -> dict:
    """
    The JSON Schema for a kår config, for independent validation (§13).

    Single source of truth: the committed ``docs/scoutnet-membership-manager.schema.json`` is this,
    and a test asserts they match so it never drifts from the model.
    """
    schema = KarConfig.model_json_schema()
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["title"] = "Scoutnet Membership Manager – kår config"
    return schema


def migrate(raw: dict) -> dict:
    """
    Normalise a kår-block dict before validation: drop the ``$schema`` hint and any
    ``_comment`` keys (JSON has no comments, so we use ignorable underscore keys).

    Config-file format migrations key on the file-level ``schema_version``; add
    steps here when the kår block's shape changes so old files keep loading.
    """
    return {k: v for k, v in raw.items() if k != "$schema" and not k.startswith("_")}


def load_config(path: str | Path) -> KarConfig:
    """
    Load the kår config at ``path``; a missing file yields the zero-config default.

    Accepts both the full settings file (the ``kar`` block is taken) and a kar-only
    file such as ``docs/examples/*.json.example``.
    """
    p = Path(path)
    if not p.exists():
        return default_config()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ConfigError(f"invalid JSON in {p}: {e}") from e
    if isinstance(data, dict) and isinstance(data.get("kar"), dict):
        data = data["kar"]  # a full scoutnet-membership-manager.json — take just the kår block
    try:
        return KarConfig.model_validate(migrate(data))
    except ValidationError as e:
        raise ConfigError(f"invalid configuration in {p}:\n{e}") from e
