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
    assert cfg.avdelningar  # every example declares avdelningar


def test_committed_schema_matches_model():
    committed = json.loads((ROOT / "docs" / "karverktyg.schema.json").read_text("utf-8"))
    assert committed == json_schema(), (
        "docs/karverktyg.schema.json is stale — regenerate it from json_schema()"
    )


def test_validate_config_cli_accepts_full_file_and_examples():
    from karverktyg.cli import main

    # the committed full karverktyg.json (settings + kar) and a kar-only example
    assert main(["validate-config", str(ROOT / "karverktyg.json")]) == 0
    assert main(["validate-config", str(EXAMPLES[0])]) == 0


def test_settings_loads_committed_config(monkeypatch):
    monkeypatch.setenv("SCOUTNET_CONFIG_PATH", str(ROOT / "karverktyg.json"))
    from karverktyg.settings import Settings

    s = Settings()
    assert s.kar.name == "Scoutkåren Finn" and len(s.kar.avdelningar) == 14
    assert s.entity_id == "1025" and s.schema_version == 1
