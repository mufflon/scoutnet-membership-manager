"""
Troop-id index shared by the findings and uppflyttning engines.

troop_id is resolved from ``unit.raw_value`` across the live memberlist (§4,
Phase 0 Part B), with config ``troop_id`` overrides for an avdelning too empty
to appear in the response (§17).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from karverktyg.config.models import Bracket, KarConfig
from karverktyg.scoutnet.models import MemberList


@dataclass
class TroopIndex:
    """TroopIndex."""

    name_to_id: dict[str, int] = field(default_factory=dict)
    id_to_name: dict[int, str] = field(default_factory=dict)
    id_to_bracket: dict[int, Bracket] = field(default_factory=dict)

    def ids_for_bracket(self, bracket: Bracket) -> set[int]:
        """Ids for bracket."""
        return {tid for tid, b in self.id_to_bracket.items() if b is bracket}


def build_troop_index(memberlist: MemberList, config: KarConfig) -> TroopIndex:
    """Build troop index."""
    name_to_id: dict[str, int] = {}
    # Live: first observed unit.raw_value per unit name.
    for m in memberlist.members:
        if m.unit and m.unit_troop_id is not None:
            name_to_id.setdefault(m.unit, m.unit_troop_id)
    # Config overrides for avdelningar with no members in the response.
    for a in config.avdelningar:
        if a.troop_id is not None:
            name_to_id.setdefault(a.name, a.troop_id)

    id_to_name = {tid: name for name, tid in name_to_id.items()}
    id_to_bracket: dict[int, Bracket] = {}
    for name, tid in name_to_id.items():
        a = config.avdelning(name)
        if a is not None:
            id_to_bracket[tid] = a.bracket
    return TroopIndex(name_to_id=name_to_id, id_to_name=id_to_name, id_to_bracket=id_to_bracket)
