from __future__ import annotations

from karverktyg.scoutnet.client import FixtureClient, ScoutnetError
from karverktyg.settings import Mode, Settings
from karverktyg.web.apicheck import api_check


class _Stub:
    """Minimal read client for exercising the read_only probe branches."""

    def __init__(self, members: list | None = None, exc: Exception | None = None) -> None:
        self._members = members or []
        self._exc = exc

    def memberlist(self, variant: str = "active") -> list:  # noqa: ARG002 - interface shape
        if self._exc is not None:
            raise self._exc
        return self._members

    def organisation_group(self) -> dict:
        return {"membercount": len(self._members)}


def test_api_check_fixture_is_green_and_labelled():
    r = api_check(Settings(mode=Mode.FIXTURE), FixtureClient())
    assert r["fixture"] is True
    assert r["all_ok"] is True
    assert {c["status"] for c in r["checks"]} == {"fixture"}


def test_api_check_read_only_ok_and_disabled():
    s = Settings(
        mode=Mode.READ_ONLY, entity_id="1", memberlist_key="k", organisation_group_key=None
    )
    r = api_check(s, _Stub(members=[1, 2, 3]))
    by = {c["endpoint"]: c for c in r["checks"]}
    assert by["group/memberlist"]["status"] == "ok"
    assert "3 medlemmar" in by["group/memberlist"]["detail"]
    assert by["organisation/group"]["status"] == "disabled"  # blank key = intentionally off
    assert r["all_ok"] is True  # disabled is not a failure


def test_api_check_read_only_failure_is_flagged():
    s = Settings(
        mode=Mode.READ_ONLY, entity_id="1", memberlist_key="bad", organisation_group_key="y"
    )
    r = api_check(s, _Stub(exc=ScoutnetError("401 Unauthorized for /group/memberlist")))
    by = {c["endpoint"]: c for c in r["checks"]}
    assert by["group/memberlist"]["status"] == "fail"
    assert "401" in by["group/memberlist"]["detail"]
    assert r["all_ok"] is False
