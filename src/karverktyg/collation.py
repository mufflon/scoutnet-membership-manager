"""Swedish collation (CLAUDE.md §2).

å, ä and ö sort *after* z, not as variants of a and o. Primary path is
PyICU with locale sv_SE; when PyICU is not installed (it needs system ICU) we
fall back to a deterministic pure-Python key that preserves the å/ä/ö-after-z
rule. We never rely on default byte ordering.

Postgres-side sorting uses an explicit ``sv-SE-x-icu`` collation elsewhere;
this module is the Python-side equivalent used for in-memory name lists.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Callable, Iterable

# Sentinels that sort after 'z' in codepoint order ('z' == U+007A < U+007B ...).
_SWEDISH_TAIL = {"å": "{", "ä": "|", "ö": "}"}

try:  # pragma: no cover - exercised only where PyICU is installed
    import icu

    _COLLATOR = icu.Collator.createInstance(icu.Locale("sv_SE"))
except Exception:  # ImportError, or ICU data missing
    _COLLATOR = None


def _fallback_key(value: str) -> tuple:
    """Deterministic sv_SE-ish key without ICU. Casefold, push å/ä/ö past z,
    then strip remaining combining marks so other accents order sensibly."""
    folded = value.casefold()
    out: list[str] = []
    for ch in folded:
        if ch in _SWEDISH_TAIL:
            out.append(_SWEDISH_TAIL[ch])
        else:
            decomposed = unicodedata.normalize("NFKD", ch)
            out.append("".join(c for c in decomposed if not unicodedata.combining(c)))
    return tuple(ord(c) for c in "".join(out))


def sort_key(value: str) -> object:
    """Sort key for a single string under Swedish collation."""
    if value is None:
        value = ""
    if _COLLATOR is not None:  # pragma: no cover
        return _COLLATOR.getSortKey(value)
    return _fallback_key(value)


def using_icu() -> bool:
    """Whether the ICU collator is active (surfaced on the capabilities page)."""
    return _COLLATOR is not None


def sorted_sv[T](items: Iterable[T], key: Callable[[T], str] = str) -> list[T]:
    """Sort ``items`` by a Swedish-collated string extracted via ``key``."""
    return sorted(items, key=lambda item: sort_key(key(item)))
