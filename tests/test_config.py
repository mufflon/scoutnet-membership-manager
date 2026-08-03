from __future__ import annotations

import pytest
from pydantic import ValidationError

from karverktyg.config import TransitionKind
from karverktyg.config.models import Bracket, KarConfig


def test_default_config_loads(config):
    assert config.name == "Scoutkåren Finn"
    assert config.group_id == "1025"
    assert config.placeholder is True
    assert len(config.avdelningar) == 14
    assert len(config.brackets) == 6


def test_ledare_is_the_only_18plus(config):
    assert config.eighteen_plus_avdelningar() == ["Ledare"]


def test_same_weekday_targets_resolve(config):
    hajarna = config.avdelning("Hajarna")
    assert hajarna.bracket is Bracket.SPARARE
    assert hajarna.weekday == 0
    assert config.avdelning(hajarna.default_target).weekday == 0  # matched weekday


def test_transition_kinds(config):
    assert config.rule(Bracket.SPARARE).transition is TransitionKind.SAME_WEEKDAY
    assert config.rule(Bracket.UPPTACKARE).transition is TransitionKind.MERGE
    assert config.rule(Bracket.AVENTYRARE).transition is TransitionKind.NEW_COHORT_AVDELNING
    assert config.rule(Bracket.UTMANARE).transition is TransitionKind.NEVER_AUTO


def _base_config() -> dict:
    return {
        "name": "T",
        "group_id": "1",
        "brackets": [
            {"bracket": "sparare", "age_min": 8, "age_max": 9, "transition": "same_weekday"},
            {"bracket": "utmanare", "transition": "never_auto", "structural_checks": False},
        ],
        "avdelningar": [
            {"name": "A", "bracket": "sparare", "weekday": 0, "default_target": "A"},
        ],
    }


def test_duplicate_cohort_year_rejected():
    cfg = _base_config()
    cfg["avdelningar"] = [
        {"name": "U1", "bracket": "utmanare", "cohort_year": 2020},
        {"name": "U2", "bracket": "utmanare", "cohort_year": 2020},
    ]
    with pytest.raises(ValidationError):
        KarConfig.model_validate(cfg)


def test_same_weekday_without_weekday_rejected():
    cfg = _base_config()
    cfg["avdelningar"] = [{"name": "A", "bracket": "sparare"}]
    with pytest.raises(ValidationError):
        KarConfig.model_validate(cfg)


def test_unknown_default_target_rejected():
    cfg = _base_config()
    cfg["avdelningar"] = [
        {"name": "A", "bracket": "sparare", "weekday": 0, "default_target": "Nonexistent"},
    ]
    with pytest.raises(ValidationError):
        KarConfig.model_validate(cfg)
