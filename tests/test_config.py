from __future__ import annotations

import pytest
from pydantic import ValidationError

from karverktyg.config import TransitionKind
from karverktyg.config.loader import default_config
from karverktyg.config.models import BRACKETS, Bracket, KarConfig, transition_for


def test_config_loads(config):
    assert config.name == "Scoutkåren Finn"
    assert len(config.avdelningar) == 14


def test_ledare_is_the_only_18plus(config):
    assert config.eighteen_plus_avdelningar() == ["Ledare"]


def test_national_bracket_ladder():
    rules = {b.bracket: b for b in BRACKETS}
    assert rules[Bracket.SPARARE].age_min == 8 and rules[Bracket.SPARARE].age_max == 9
    assert rules[Bracket.UTMANARE].age_max == 19  # national decision: Utmanare tops at 19
    assert rules[Bracket.ROVER].structural_checks is False


def test_transition_groups_by_source_bracket():
    assert transition_for(Bracket.SPARARE) is TransitionKind.SAME_WEEKDAY
    assert transition_for(Bracket.UPPTACKARE) is TransitionKind.MERGE
    assert transition_for(Bracket.AVENTYRARE) is TransitionKind.NEW_COHORT_AVDELNING


def test_same_weekday_target_resolves(config, memberlist):
    from karverktyg.roster import build_troop_index
    from karverktyg.uppflyttning.engine import infer_target_name

    index = build_troop_index(memberlist, config)
    # Hajarna (Mon) -> the Mon Upptäckare (Kämparna), by same-weekday inference.
    assert infer_target_name("Hajarna", config, index) == "Kämparna"


def test_no_config_default_is_empty():
    c = default_config()
    assert c.avdelningar == []


def test_unknown_target_rejected():
    with pytest.raises(ValidationError):
        KarConfig.model_validate(
            {
                "version": 1,
                "name": "T",
                "avdelningar": [{"name": "A", "bracket": "sparare", "target": "Nonexistent"}],
            }
        )


def test_duplicate_avdelning_name_rejected():
    with pytest.raises(ValidationError):
        KarConfig.model_validate(
            {
                "version": 1,
                "avdelningar": [
                    {"name": "A", "bracket": "sparare"},
                    {"name": "A", "bracket": "upptackare"},
                ],
            }
        )
