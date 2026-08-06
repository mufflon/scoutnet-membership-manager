"""
Troop-id index shared by the findings and uppflyttning engines.

troop_id is resolved from ``unit.raw_value`` across the live memberlist (§4,
Phase 0 Part B), with config ``troop_id`` overrides for an avdelning too empty
to appear in the response (§17).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from scoutnet_membership_manager.config.models import Bracket, KarConfig
from scoutnet_membership_manager.scoutnet.models import MemberList


@dataclass
class TroopIndex:
    """TroopIndex."""

    name_to_id: dict[str, int] = field(default_factory=dict)
    id_to_name: dict[int, str] = field(default_factory=dict)
    id_to_bracket: dict[int, Bracket] = field(default_factory=dict)

    def ids_for_bracket(self, bracket: Bracket) -> set[int]:
        """Ids for bracket."""
        return {tid for tid, b in self.id_to_bracket.items() if b is bracket}

    def bracket_of(self, name: str) -> Bracket | None:
        """The bracket of an avdelning by name, from the data."""
        tid = self.name_to_id.get(name)
        return self.id_to_bracket.get(tid) if tid is not None else None


def build_troop_index(memberlist: MemberList, config: KarConfig) -> TroopIndex:
    """
    Build the avdelning-name -> troop_id -> bracket index from the **live**
    memberlist (§4). Both the id (``unit.raw_value``) and the bracket
    (``unit_type``) come from the data, so avdelningar are inferred without any
    config. The config is only an overlay: it can name the bracket of an avdelning
    too empty to appear in the data (e.g. a brand-new one).
    """
    name_to_id: dict[str, int] = {}
    id_to_bracket: dict[int, Bracket] = {}
    for m in memberlist.members:
        if m.unit and m.unit_troop_id is not None:
            name_to_id.setdefault(m.unit, m.unit_troop_id)
            if m.unit_troop_id not in id_to_bracket and m.bracket is not None:
                id_to_bracket[m.unit_troop_id] = m.bracket

    # Overlay: declared avdelningar fill in a bracket the data could not (empty ones).
    for a in config.avdelningar:
        tid = name_to_id.get(a.name)
        if tid is not None:
            id_to_bracket.setdefault(tid, a.bracket)

    id_to_name = {tid: name for name, tid in name_to_id.items()}
    return TroopIndex(name_to_id=name_to_id, id_to_name=id_to_name, id_to_bracket=id_to_bracket)


@dataclass
class PatrolInfo:
    """One patrull within an avdelning, as seen in the live memberlist."""

    patrol_id: int
    name: str
    size: int  # current active members placed in it


@dataclass
class PatrolIndex:
    """
    Which patruller exist in each avdelning, derived from the live memberlist
    (§4). A patrull is only visible when at least one member is placed in it —
    ``GET /body_key_list`` (the only body enumerator) is not available to this
    kår, and an empty patrull therefore cannot be discovered. So a "known"
    patrull always has ``size >= 1``, exactly the ones an uppflyttning can place
    movers into automatically.
    """

    by_troop: dict[int, list[PatrolInfo]] = field(default_factory=dict)

    def first_known_patrol(self, troop_id: int | None) -> PatrolInfo | None:
        """
        The patrull movers into ``troop_id`` should be placed in, or ``None`` when
        the avdelning has no known patrull (then the operator sets both avdelning
        and patrull by hand, as today). Deterministic: the lowest ``patrol_id``,
        i.e. the first patrull created. We deliberately do not load-balance —
        everyone lands in one patrull and the avdelning's leaders redistribute.
        """
        patrols = self.by_troop.get(troop_id) if troop_id is not None else None
        return patrols[0] if patrols else None


def build_patrol_index(memberlist: MemberList) -> PatrolIndex:
    """
    Group the live memberlist into patruller per avdelning (§4). Only patruller
    with at least one placed member appear — empty ones are undiscoverable.
    """
    counts: dict[int, dict[int, tuple[str, int]]] = {}
    for m in memberlist.members:
        if m.unit_troop_id is None or m.patrol_id is None:
            continue
        troop = counts.setdefault(m.unit_troop_id, {})
        name, size = troop.get(m.patrol_id, (m.patrol or "", 0))
        troop[m.patrol_id] = (name or (m.patrol or ""), size + 1)
    by_troop: dict[int, list[PatrolInfo]] = {}
    for troop_id, patrols in counts.items():
        by_troop[troop_id] = [
            PatrolInfo(patrol_id=pid, name=name, size=size)
            for pid, (name, size) in sorted(patrols.items())
        ]
    return PatrolIndex(by_troop=by_troop)
