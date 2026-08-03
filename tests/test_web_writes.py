"""
Write-endpoint wiring (Phase 2, §6/§8): read_write gating, dry-run, background
execute + server-side status polling, snapshots, and undo — end to end through
the Flask app with an injected read+write fixture double (no network).
"""

from __future__ import annotations

import json

from karverktyg.db import WriteRun, get_session
from karverktyg.scoutnet.client import FixtureClient
from karverktyg.settings import Mode, Settings
from karverktyg.web import create_app


def _member(mno: str, unit: str, troop_id: int, unit_type: int, dob: str) -> dict:
    return {
        "member_no": {"value": mno},
        "first_name": {"value": "Test"},
        "last_name": {"value": mno},
        "date_of_birth": {"value": dob},
        "status": {"value": "Aktiv", "raw_value": "2"},
        "unit": {"value": unit, "raw_value": str(troop_id)},
        "unit_type": {"value": unit, "raw_value": str(unit_type)},
    }


def _write_fixture(path, members: list[dict], term: str = "Höst 2026") -> None:
    data = {m["member_no"]["value"]: m for m in members}
    path.write_text(
        json.dumps({"data": data, "labels": {"current_term": term, "prev_term": "Vår 2026"}}),
        encoding="utf-8",
    )


class FixtureReadWrite:
    """Reads a committed fixture; applies troop moves to an in-memory overlay."""

    def __init__(self, path):
        self._base = FixtureClient(path)
        self.overrides: dict[str, int] = {}

    def memberlist(self, variant: str = "active", *, fresh: bool = False):  # noqa: ARG002
        ml = self._base.memberlist(variant)
        for m in ml.members:
            if m.member_no in self.overrides:
                m.unit_troop_id = self.overrides[m.member_no]
        return ml

    def update_membership(self, payload: dict) -> dict:
        for mno, fields in payload.items():
            if "troop_id" in fields:
                self.overrides[mno] = fields["troop_id"]
        return {"status": "ok"}

    def close(self) -> None:
        pass


# The memberlist reflects last year's placement, so a mover is one who has aged
# a step past their bracket: a 2016-born (age 10 at N=2026) still in Spårare
# moves up to Upptäckare (Hajarna -> Kämparna). The 2017-born (age 9) still fits
# Spårare and stays; the Kämparna member resolves the target troop_id.
_MOVERS = [
    _member("1001", "Hajarna", 20001, 2, "2016-05-01"),  # aged into Upptäckare -> moves
    _member("1002", "Hajarna", 20001, 2, "2017-05-01"),  # still Spårare -> stays
    _member("1003", "Kämparna", 30001, 3, "2016-05-01"),  # Upptäckare, stays; gives Kämparna its id
]


def _rw_app(tmp_path, allowlist=("1001", "1002", "1003")):
    fx = tmp_path / "fx.json"
    _write_fixture(fx, _MOVERS)
    double = FixtureReadWrite(fx)
    settings = Settings(
        mode=Mode.READ_WRITE,
        entity_id="1025",
        memberlist_key="mk",
        update_membership_key="wk",
        snapshot_dir=tmp_path / "snaps",
        write_allowlist=list(allowlist),
        chunk_delay_s=0,
        database_url="sqlite://",
        cohort_year=2026,
    )
    app = create_app(settings, client=double)
    return app, double


# --- gating ----------------------------------------------------------------


def test_write_endpoints_require_read_write():
    c = create_app(Settings(mode=Mode.FIXTURE, database_url="sqlite://")).test_client()
    assert c.post("/api/uppflyttning/run", json={"mode": "dry_run"}).status_code == 403
    assert c.get("/api/write/runs").status_code == 403
    assert c.get("/api/write/runs/x").status_code == 403
    assert c.get("/api/write/snapshots").status_code == 403
    assert c.post("/api/write/runs/x/resume").status_code == 403
    assert c.post("/api/write/runs/x/undo").status_code == 403


# --- dry-run ---------------------------------------------------------------


def test_dry_run_reports_the_move_without_sending(tmp_path):
    app, double = _rw_app(tmp_path)
    c = app.test_client()

    dry = c.post("/api/uppflyttning/run", json={"mode": "dry_run"}).get_json()

    assert dry["run_state"] == "dry_run" and dry["run_id"] is None
    will = {p["member_no"] for p in dry["preflight"] if p["category"] == "will_apply"}
    assert will == {"1001"}
    assert dry["chunks"][0]["payload"] == {"1001": {"status": "confirmed", "troop_id": 30001}}
    assert double.overrides == {}  # nothing sent
    snaps_dir = tmp_path / "snaps"
    assert not snaps_dir.exists() or list(snaps_dir.glob("*.json")) == []  # no snapshot on dry-run


# --- execute + poll + snapshot + undo --------------------------------------


def test_execute_run_polls_done_and_is_undoable(tmp_path):
    app, double = _rw_app(tmp_path)
    c = app.test_client()

    started = c.post("/api/uppflyttning/run", json={"mode": "execute"})
    assert started.status_code == 202
    run_id = started.get_json()["run_id"]
    app.config["RUN_MANAGER"].wait(timeout=5)  # let the background run finish

    status = c.get(f"/api/write/runs/{run_id}").get_json()
    assert status["state"] == "done"
    assert status["journal"] == {"done": 1}
    assert status["undo_available"] is True
    assert double.overrides["1001"] == 30001  # actually moved

    snaps = c.get("/api/write/snapshots").get_json()["snapshots"]
    assert len(snaps) == 1 and snaps[0]["run_id"] == run_id

    undo = c.post(f"/api/write/runs/{run_id}/undo").get_json()  # dry-run undo
    assert any(
        p["member_no"] == "1001" and p["category"] == "will_apply" for p in undo["preflight"]
    )

    # Purge the snapshot -> undo becomes unavailable.
    c.delete(f"/api/write/snapshots/{snaps[0]['id']}")
    assert c.post(f"/api/write/runs/{run_id}/undo").status_code == 409


def test_execute_refused_when_a_run_is_already_running(tmp_path):
    app, _ = _rw_app(tmp_path)
    c = app.test_client()
    with get_session(app.config["SESSIONMAKER"]) as s:
        s.add(WriteRun(id="busy", kind="uppflyttning", mode="execute", state="running"))

    assert c.post("/api/uppflyttning/run", json={"mode": "execute"}).status_code == 409


def test_execute_refused_for_off_allowlist_member(tmp_path):
    app, _ = _rw_app(tmp_path, allowlist=("9999",))  # 1001 not allowed
    c = app.test_client()
    assert c.post("/api/uppflyttning/run", json={"mode": "execute"}).status_code == 400


def test_dry_run_previews_regardless_of_allowlist(tmp_path):
    # A dry-run writes nothing, so it must preview the plan even when nobody is on
    # the allowlist; only the execute is gated (§8).
    app, _ = _rw_app(tmp_path, allowlist=("9999",))
    c = app.test_client()
    dry = c.post("/api/uppflyttning/run", json={"mode": "dry_run"})
    assert dry.status_code == 200 and "preflight" in dry.get_json()
    assert c.post("/api/uppflyttning/run", json={"mode": "execute"}).status_code == 400


def test_unknown_run_is_404(tmp_path):
    app, _ = _rw_app(tmp_path)
    c = app.test_client()
    assert c.get("/api/write/runs/nope").status_code == 404


def test_verify_single_member_dry_run_and_execute(tmp_path):
    app, double = _rw_app(tmp_path)
    c = app.test_client()

    info = c.get("/api/write/verify").get_json()
    assert any(a["member_no"] == "1001" for a in info["allowlist"])
    assert any(a["avdelning"] == "Hajarna" for a in info["avdelningar"])

    dry = c.post("/api/write/verify", json={"member_no": "1001", "target_troop_id": 99999})
    d = dry.get_json()
    assert d["run_state"] == "dry_run"
    assert d["chunks"][0]["payload"] == {"1001": {"status": "confirmed", "troop_id": 99999}}
    assert double.overrides == {}  # dry-run writes nothing

    started = c.post(
        "/api/write/verify", json={"member_no": "1001", "target_troop_id": 99999, "mode": "execute"}
    )
    assert started.status_code == 202
    app.config["RUN_MANAGER"].wait(timeout=5)
    assert double.overrides["1001"] == 99999


def test_verify_refuses_off_allowlist_and_gates_on_mode(tmp_path):
    app, _ = _rw_app(tmp_path, allowlist=("1001",))
    c = app.test_client()
    # 1002 is not on the allowlist -> 400
    assert (
        c.post(
            "/api/write/verify", json={"member_no": "1002", "target_troop_id": 99999}
        ).status_code
        == 400
    )
    # gated outside read_write
    fx = create_app(Settings(mode=Mode.FIXTURE, database_url="sqlite://")).test_client()
    assert (
        fx.post("/api/write/verify", json={"member_no": "1001", "target_troop_id": 1}).status_code
        == 403
    )
    assert fx.get("/api/write/verify").status_code == 403
