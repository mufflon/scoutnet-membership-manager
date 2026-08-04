from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from karverktyg.config import load_config
from karverktyg.scoutnet.parse import parse_memberlist

ROOT = Path(__file__).resolve().parent.parent

# App-level tests build Settings() directly; point them at the committed Finn
# example so they exercise weekday routing (the operational karverktyg.json is
# gitignored). Individual tests can still override SCOUTNET_CONFIG_PATH.
os.environ.setdefault("SCOUTNET_CONFIG_PATH", str(ROOT / "docs" / "examples" / "finn.json.example"))
# The kår's id (Finn = 1025) — used to reject it as an avdelning troop_id (§17).
os.environ.setdefault("SCOUTNET_ENTITY_ID", "1025")


@pytest.fixture
def config():
    return load_config(ROOT / "docs" / "examples" / "finn.json.example")


@pytest.fixture
def memberlist_raw():
    return json.loads((ROOT / "fixtures" / "memberlist.demo.json").read_text("utf-8"))


@pytest.fixture
def memberlist(memberlist_raw):
    return parse_memberlist(memberlist_raw)
