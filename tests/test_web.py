from __future__ import annotations

import pytest

from karverktyg.settings import Mode, Settings
from karverktyg.web import create_app


@pytest.fixture
def client():
    settings = Settings(mode=Mode.FIXTURE, database_url="sqlite://", cohort_year=None)
    return create_app(settings).test_client()


def test_index_served(client):
    r = client.get("/")
    assert r.status_code == 200
    assert b"rverktyg" in r.data  # "Kårverktyg"


def test_liveness_and_readiness(client):
    assert client.get("/healthz").status_code == 200
    assert client.get("/readyz").status_code == 200  # sqlite connects


def test_overview(client):
    d = client.get("/api/overview").get_json()
    assert d["member_count"] == 371
    assert d["current_term"]  # "Höst 2026"


def test_capabilities_reports_mode_and_no_writes(client):
    d = client.get("/api/capabilities").get_json()
    assert d["mode"] == "fixture"
    assert d["read_write_active"] is False
    writes = next(a for a in d["actions"] if a["action"] == "execute_writes")
    assert writes["enabled"] is False


def test_uppflyttning_and_changelist_gate(client):
    d = client.get("/api/uppflyttning").get_json()
    assert d["cohort_year"] == 2026
    assert len(d["ready"]) > 0
    # off-cohort members exist -> export gated until acknowledged (§17)
    assert client.get("/api/uppflyttning/changelist.xlsx").status_code == 409
    ok = client.get("/api/uppflyttning/changelist.xlsx?ack_by=alex")
    assert ok.status_code == 200
    assert ok.data[:2] == b"PK"  # xlsx zip


def test_findings_endpoint(client):
    d = client.get("/api/findings").get_json()
    assert any(f["type"] == "no_avdelning" for f in d["findings"])
    # security findings sort first
    if d["findings"]:
        assert d["findings"][0]["severity"] in ("security", "warning", "info")


def test_dues_endpoint(client):
    d = client.get("/api/dues").get_json()
    assert isinstance(d["avdelningar"], list) and d["avdelningar"]


def test_membership_drafts(client):
    d = client.get("/api/membership/drafts?variant=waiting").get_json()
    drafts = d["drafts"]
    assert len(drafts) == 3  # 2 scouts + 1 ledare in the synthetic sample
    ledare = [x for x in drafts if x["kind"] == "ledare"]
    scouts = [x for x in drafts if x["kind"] == "scout"]
    assert len(ledare) == 1 and len(scouts) == 2
    # ledare draft goes to the person, not a guardian
    assert ledare[0]["to"] == ["cecilia.testledare@example.org"]
    assert any("Spårare" in s["body"] for s in scouts)


def test_templates_get_and_edit(client):
    got = client.get("/api/templates").get_json()["templates"]
    assert any(t["key"] == "scout_request" for t in got)
    r = client.put(
        "/api/templates/scout_request",
        json={"subject": "Hej {{ first_name }}", "body": "Nytt {{ kar }}", "by": "alex"},
    )
    assert r.status_code == 200
    after = client.get("/api/templates").get_json()["templates"]
    scout = next(t for t in after if t["key"] == "scout_request")
    assert scout["subject"] == "Hej {{ first_name }}" and scout["edited"] is True
    assert client.put("/api/templates/nope", json={"subject": "a", "body": "b"}).status_code == 404
