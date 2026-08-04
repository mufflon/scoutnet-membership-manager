from __future__ import annotations

import pytest

from karverktyg.config.models import TransitionKind
from karverktyg.scoutnet.models import Member, MemberList, Role
from karverktyg.uppflyttning import (
    CohortYearConflict,
    ElectedTarget,
    MoveStatus,
    compute_master_set,
    resolve_cohort_year,
)
from karverktyg.uppflyttning.cohort import derive_n_from_term_label


# --- cohort year N + guard (§17) ------------------------------------------
def test_derive_n_from_term_label():
    assert derive_n_from_term_label("Höst 2026") == 2026
    # both seasons name the coming-autumn cohort (tool always runs before camp)
    assert derive_n_from_term_label("Vår 2026") == 2026
    assert derive_n_from_term_label(None) is None
    assert derive_n_from_term_label("2026") is None  # no season keyword


def test_resolve_cohort_year_guard():
    assert resolve_cohort_year(None, "Höst 2026") == 2026
    assert resolve_cohort_year(None, "Vår 2026") == 2026  # spring planning, same N
    assert resolve_cohort_year(2026, "Höst 2026") == 2026
    with pytest.raises(CohortYearConflict):
        resolve_cohort_year(2025, "Höst 2026")  # config vs live disagree -> refuse
    with pytest.raises(CohortYearConflict):
        resolve_cohort_year(None, None)  # unknowable -> refuse


# --- engine ----------------------------------------------------------------
def _mk(member_no, unit, code, troop, birth_year, roles=()):
    m = Member(
        member_no=member_no,
        unit=unit,
        unit_type_code=code,
        unit_troop_id=troop,
        birth_year=birth_year,
    )
    m.roles = list(roles)
    return m


def _synthetic():
    # codes: sparare 2, upptackare 3, aventyrare 4. troop ids arbitrary.
    return MemberList(
        members=[
            _mk("s_move", "Hajarna", 2, 100, 2016),  # age 10 -> Upptäckare
            _mk("s_stay", "Hajarna", 2, 100, 2017),  # age 9 -> stays
            _mk("u_resident", "Kämparna", 3, 200, 2015),  # populates index; age 11 stays
            _mk("u_move", "Kämparna", 3, 200, 2014),  # age 12 -> merge to Vikingarna
            _mk("a_resident", "Vikingarna", 4, 300, 2013),
            _mk("a_move", "Vikingarna", 4, 300, 2011),  # age 15 -> Utmanare (pending)
            _mk(
                "s_leader",
                "Hajarna",
                2,
                100,
                2016,
                roles=[Role("troop", 999, 3, "other_leader", "Ledare")],
            ),  # leader -> not auto-shifted
            _mk(
                "s_func",
                "Hajarna",
                2,
                100,
                2016,
                roles=[Role("group", 1025, 24, "material_responsible", "Materielansvarig")],
            ),  # non-leader function -> still moves, flagged
            _mk("s_offcohort", "Hajarna", 2, 100, 2010),  # age 16, two+ steps -> off_cohort
        ]
    )


def test_master_set_moves(config):
    ms = compute_master_set(_synthetic(), config, config_cohort_year_n=2026)
    assert ms.cohort_year == 2026
    by_no = {e.member_no: e for e in ms.entries}

    # same-weekday: Hajarna(Mon) -> Kämparna(Mon), target resolved
    assert by_no["s_move"].status is MoveStatus.READY
    assert by_no["s_move"].transition is TransitionKind.SAME_WEEKDAY
    assert by_no["s_move"].target_avdelning == "Kämparna"
    assert by_no["s_move"].target_troop_id == 200

    # merge -> Vikingarna
    assert by_no["u_move"].status is MoveStatus.READY
    assert by_no["u_move"].target_avdelning == "Vikingarna"

    # new_cohort_avdelning has no cohort_year target -> pending, not empty move
    assert by_no["a_move"].status is MoveStatus.PENDING_TARGET
    assert by_no["a_move"].target_troop_id is None

    # a leader is not auto-shifted; a non-leader functionary still moves (flagged)
    assert by_no["s_leader"].status is MoveStatus.EXCLUDED
    assert by_no["s_func"].status is MoveStatus.READY
    assert "funktion" in by_no["s_func"].note
    assert by_no["s_offcohort"].status is MoveStatus.OFF_COHORT

    # younger cohorts and residents stay put (no entry)
    assert "s_stay" not in by_no
    assert "u_resident" not in by_no


def test_ambiguous_merge_needs_per_member_target(config):
    """Two candidate Äventyrare avdelningar and no flow hint -> must select per member."""
    from karverktyg.config.models import KarConfig

    raw = config.model_dump(mode="json")
    raw["avdelningar"].append({"name": "Sjörövarna", "bracket": "aventyrare", "weekday": 4})
    cfg = KarConfig.model_validate(raw)

    ms = compute_master_set(_synthetic(), cfg, config_cohort_year_n=2026)
    e = {x.member_no: x for x in ms.entries}["u_move"]  # Upptäckare -> Äventyrare merge
    assert e.status is MoveStatus.PENDING_TARGET
    assert e.target_avdelning is None
    assert e.off_cohort is False
    assert "per medlem" in e.note


def test_misplaced_member_routes_per_person(config):
    """An off-cohort member assigned a target becomes READY yet stays in 'misplaced'."""
    from karverktyg.roster import build_troop_index
    from karverktyg.uppflyttning import MISPLACED_GROUP, scope_master_set
    from karverktyg.uppflyttning.overrides import Override, apply_overrides

    ml = _synthetic()
    ms = compute_master_set(ml, config, config_cohort_year_n=2026)
    off = {e.member_no: e for e in ms.entries}["s_offcohort"]
    assert off.status is MoveStatus.OFF_COHORT and off.off_cohort is True

    index = build_troop_index(ml, config)
    apply_overrides(ms, [Override("s_offcohort", target_avdelning="Kämparna", by="op")], index)

    routed = {e.member_no: e for e in ms.entries}["s_offcohort"]
    assert routed.status is MoveStatus.READY and routed.target_troop_id is not None
    assert routed.off_cohort is True  # stable flag — does not jump into an age transition
    scoped = scope_master_set(ms, MISPLACED_GROUP)
    assert "s_offcohort" in {e.member_no for e in scoped.entries}


def test_structural_misplacements_join_misplaced_group(config):
    """No-avdelning and under-18-in-Ledare members are routable in 'misplaced'."""
    from karverktyg.uppflyttning import MISPLACED_GROUP, scope_master_set

    ml = MemberList(
        members=[
            _mk("led_resident", "Ledare", 7, 10172, 1980),  # adult leader, stays put
            _mk("led_minor", "Ledare", 7, 10172, 2012),  # 14 in 2026 -> misplaced
            _mk("no_avd", "", None, None, 2015),  # no avdelning -> misplaced
        ]
    )
    ms = compute_master_set(ml, config, config_cohort_year_n=2026)
    by_no = {e.member_no: e for e in ms.entries}

    assert "led_resident" not in by_no  # an adult correctly in Ledare is not surfaced
    assert by_no["led_minor"].status is MoveStatus.OFF_COHORT
    assert by_no["led_minor"].off_cohort is True
    assert "Ledare" in by_no["led_minor"].note
    assert by_no["no_avd"].status is MoveStatus.OFF_COHORT
    assert by_no["no_avd"].off_cohort is True
    assert "avdelning" in by_no["no_avd"].note.lower()

    scoped = {e.member_no for e in scope_master_set(ms, MISPLACED_GROUP).entries}
    assert {"led_minor", "no_avd"} <= scoped


def test_elected_target_resolves_new_cohort(config):
    ms = compute_master_set(
        _synthetic(),
        config,
        config_cohort_year_n=2026,
        elected_target=ElectedTarget(avdelning="Fniss", troop_id=500),
    )
    e = {x.member_no: x for x in ms.entries}["a_move"]
    assert e.status is MoveStatus.READY
    assert e.target_avdelning == "Fniss"
    assert e.target_troop_id == 500


def test_master_set_on_fixture_is_sane(memberlist, config):
    """Order-of-magnitude check (§17): a full move is ~83 members, four chunks."""
    ms = compute_master_set(memberlist, config, config_cohort_year_n=None)
    moving = len(ms.ready()) + len(ms.pending()) + len(ms.excluded())
    assert 60 <= moving <= 110, moving
    # every ready move has a resolved target troop_id
    assert all(e.target_troop_id is not None for e in ms.ready())
    # Äventyrare->Utmanare stays pending until cohort_year is filled in
    assert all(e.transition is TransitionKind.NEW_COHORT_AVDELNING for e in ms.pending())
