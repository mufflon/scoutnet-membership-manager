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


def _find(data, member_no):
    for grp in ("ready", "pending", "off_cohort", "excluded", "kept"):
        for e in data[grp]:
            if e["member_no"] == member_no:
                return e
    return None


def test_uppflyttning_target_election(client):
    d = client.get("/api/uppflyttning").get_json()
    assert d["elected_target"] is None
    assert len(d["pending"]) > 0  # Äventyrare→Utmanare pending until elected
    candidates = d["utmanare_candidates"]
    assert candidates
    r = client.post(
        "/api/uppflyttning/target", json={"avdelning": candidates[0]["avdelning"], "by": "t"}
    )
    assert r.status_code == 200
    d2 = client.get("/api/uppflyttning").get_json()
    assert d2["elected_target"]["avdelning"] == candidates[0]["avdelning"]
    assert len(d2["pending"]) < len(d["pending"])  # some resolved to ready


def test_uppflyttning_member_target_override(client):
    d = client.get("/api/uppflyttning").get_json()
    m = d["ready"][0]
    other = next(a["avdelning"] for a in d["avdelningar"] if a["avdelning"] != m["target"])
    assert (
        client.post(
            "/api/uppflyttning/decision",
            json={"member_no": m["member_no"], "target_avdelning": other, "by": "t"},
        ).status_code
        == 200
    )
    e = _find(client.get("/api/uppflyttning").get_json(), m["member_no"])
    assert e["target"] == other and e["override"] is True
    # clearing reverts to the computed default
    assert (
        client.delete("/api/uppflyttning/decision?member_no=" + m["member_no"]).status_code == 200
    )
    assert _find(client.get("/api/uppflyttning").get_json(), m["member_no"])["override"] is False


def test_uppflyttning_acknowledge(client):
    d = client.get("/api/uppflyttning").get_json()
    pool = d["off_cohort"] + d["excluded"]
    assert pool  # the fixture has excluded leaders / off-cohort adults
    m = pool[0]
    assert (
        client.post(
            "/api/uppflyttning/decision",
            json={"member_no": m["member_no"], "acknowledged": True, "by": "t"},
        ).status_code
        == 200
    )
    assert _find(client.get("/api/uppflyttning").get_json(), m["member_no"])["acknowledged"] is True


def test_uppflyttning_keep_in_place(client):
    d = client.get("/api/uppflyttning").get_json()
    m = d["ready"][0]
    assert m["default_target"]  # a ready move exposes its computed default (★ in the UI)
    client.post(
        "/api/uppflyttning/decision",
        json={"member_no": m["member_no"], "target_avdelning": "", "stay_until": d["cohort_year"]},
    )
    e = _find(client.get("/api/uppflyttning").get_json(), m["member_no"])
    assert e["stay"] is True and e["status"] == "override_stay"


def test_uppflyttning_reset(client):
    d = client.get("/api/uppflyttning").get_json()
    assert d["decisions_count"] == 0 and d["elected_target"] is None
    m = (d["off_cohort"] + d["excluded"])[0]
    client.post(
        "/api/uppflyttning/decision", json={"member_no": m["member_no"], "acknowledged": True}
    )
    client.post(
        "/api/uppflyttning/target", json={"avdelning": d["utmanare_candidates"][0]["avdelning"]}
    )
    mid = client.get("/api/uppflyttning").get_json()
    assert mid["decisions_count"] >= 1 and mid["elected_target"] is not None
    assert client.post("/api/uppflyttning/reset").status_code == 200
    after = client.get("/api/uppflyttning").get_json()
    assert after["decisions_count"] == 0 and after["elected_target"] is None


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
