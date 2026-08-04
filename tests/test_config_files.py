from __future__ import annotations

import json
from pathlib import Path

import pytest

from karverktyg.config.loader import json_schema, load_config

ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = sorted((ROOT / "docs" / "examples").glob("*.json.example"))


@pytest.mark.parametrize("path", EXAMPLES, ids=lambda p: p.name)
def test_example_config_loads_and_validates(path):
    cfg = load_config(path)
    assert cfg.version == 1
    assert cfg.avdelningar  # every example declares avdelningar


def test_committed_schema_matches_model():
    committed = json.loads((ROOT / "docs" / "karverktyg.schema.json").read_text("utf-8"))
    assert committed == json_schema(), (
        "docs/karverktyg.schema.json is stale — regenerate it from json_schema()"
    )
