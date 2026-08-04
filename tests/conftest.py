from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from scoutnet_membership_manager.config import load_config
from scoutnet_membership_manager.scoutnet.parse import parse_memberlist

ROOT = Path(__file__).resolve().parent.parent

# App-level tests build Settings() directly; point them at the committed Finn
# config so they exercise weekday routing. Individual tests can still override
# SCOUTNET_CONFIG_PATH.
os.environ.setdefault("SCOUTNET_CONFIG_PATH", str(ROOT / "scoutnet-membership-manager.json"))
# The kår's id (Finn = 1025) — used to reject it as an avdelning troop_id (§17).
os.environ.setdefault("SCOUTNET_ENTITY_ID", "1025")


@pytest.fixture
def config():
    return load_config(ROOT / "scoutnet-membership-manager.json")


@pytest.fixture
def memberlist_raw():
    return json.loads((ROOT / "fixtures" / "memberlist.demo.json").read_text("utf-8"))


@pytest.fixture
def memberlist(memberlist_raw):
    return parse_memberlist(memberlist_raw)
