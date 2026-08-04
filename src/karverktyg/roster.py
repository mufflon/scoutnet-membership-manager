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
