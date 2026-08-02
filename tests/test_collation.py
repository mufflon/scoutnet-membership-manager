from __future__ import annotations

from karverktyg.collation import sorted_sv


def test_aao_sort_after_z():
    names = ["Öland", "Alfa", "Ängel", "Bravo", "Åke", "Zeta"]
    assert sorted_sv(names) == ["Alfa", "Bravo", "Zeta", "Åke", "Ängel", "Öland"]


def test_case_insensitive():
    assert sorted_sv(["bravo", "Alfa"]) == ["Alfa", "bravo"]


def test_sort_by_key():
    items = [{"n": "Öst"}, {"n": "Ada"}]
    assert sorted_sv(items, key=lambda d: d["n"]) == [{"n": "Ada"}, {"n": "Öst"}]
