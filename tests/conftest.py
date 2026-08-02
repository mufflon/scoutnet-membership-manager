from __future__ import annotations

import json
from pathlib import Path

import pytest

from karverktyg.config import load_config
from karverktyg.scoutnet.parse import parse_memberlist

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def config():
    return load_config(ROOT / "config" / "karverktyg.default.json")


@pytest.fixture
def memberlist_raw():
    return json.loads((ROOT / "fixtures" / "memberlist.scrubbed.json").read_text("utf-8"))


@pytest.fixture
def memberlist(memberlist_raw):
    return parse_memberlist(memberlist_raw)
