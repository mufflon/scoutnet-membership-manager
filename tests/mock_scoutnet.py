"""
Stage-1 mock Scoutnet server (CLAUDE.md §8), driven through httpx.MockTransport.

The request contract is **read from the vendored OpenAPI spec** rather than
hand-written, so the mock cannot silently drift from what the real endpoint
accepts. It replays memberlist reads from in-memory state and validates
``update/membership`` bodies against the spec-derived enum/required, applying the
troop move on success. Failures can be simulated to exercise the executor's
stop/resume/failure paths. No network — this is a transport, not a socket.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import yaml

_SPEC = Path(__file__).resolve().parent.parent / "vendor" / "openapi" / "bundled.yaml"

_HTTP_OK = 200
_HTTP_BAD_REQUEST = 400
_HTTP_UNAUTHORIZED = 401
_HTTP_NOT_FOUND = 404


def _resolve(spec: dict, node: dict) -> dict:
    """Follow an internal ``$ref`` one hop (the bundled spec keeps internal refs)."""
    if isinstance(node, dict) and "$ref" in node:
        cur: object = spec
        for part in node["$ref"].lstrip("#/").split("/"):
            cur = cur[part]
        return cur
    return node


def load_update_membership_contract() -> dict:
    """
    Extract the ``update/membership`` request contract from the vendored spec:
    the required fields, the ``status`` enum and which fields are integers.
    """
    spec = yaml.safe_load(_SPEC.read_text("utf-8"))
    paths = spec["paths"]
    key = next(p for p in paths if "update/membership" in p)
    schema = paths[key]["post"]["requestBody"]["content"]["application/json"]["schema"]
    entry = _resolve(spec, schema.get("additionalProperties", {}))
    props = {k: _resolve(spec, v) for k, v in entry.get("properties", {}).items()}
    return {
        "required": list(entry.get("required", [])),
        "status_enum": set(props.get("status", {}).get("enum", [])),
        "integer_fields": {k for k, v in props.items() if v.get("type") == "integer"},
    }


def validate_update_body(body: object, contract: dict) -> dict[str, str]:
    """
    Validate a body against the spec-derived contract. Returns per-member error
    strings (empty when valid), mirroring the real 400 shape (§4). Member keys
    must be numeric — member numbers are numeric; a non-numeric key is malformed.
    """
    if not isinstance(body, dict):
        return {"_": "body must be an object keyed by member number"}
    errors: dict[str, str] = {}
    for member_no, entry in body.items():
        if not (isinstance(member_no, str) and member_no.isdigit()):
            errors[member_no] = "member key is not a numeric member number"
        elif not isinstance(entry, dict):
            errors[member_no] = "entry must be an object"
        elif [f for f in contract["required"] if f not in entry]:
            errors[member_no] = "missing required field(s)"
        elif entry.get("status") not in contract["status_enum"]:
            errors[member_no] = f"status {entry.get('status')!r} not in enum"
        else:
            bad_int = [
                f
                for f in contract["integer_fields"]
                if f in entry and not isinstance(entry[f], int)
            ]
            if bad_int:
                errors[member_no] = f"{bad_int[0]} must be an integer"
    return errors


class MockScoutnet:
    """In-memory Scoutnet behind an httpx.MockTransport."""

    def __init__(
        self,
        members: dict[str, dict],
        *,
        fail_on: set[str] | None = None,
        fail_status: int = _HTTP_BAD_REQUEST,
    ) -> None:
        self._members = {k: dict(v) for k, v in members.items()}
        self.contract = load_update_membership_contract()
        self.fail_on = set(fail_on or ())
        self.fail_status = fail_status
        self.requests: list[tuple[str, str]] = []  # (method, path)

    def transport(self) -> httpx.MockTransport:
        """A transport to hand to ReadWriteClient(settings, transport=...)."""
        return httpx.MockTransport(self._handle)

    def _handle(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        self.requests.append((request.method, path))
        if "authorization" not in {k.lower() for k in request.headers}:
            return httpx.Response(_HTTP_UNAUTHORIZED, json={"error": "missing auth"})
        if request.method == "GET" and path.endswith("/group/memberlist"):
            return httpx.Response(_HTTP_OK, json=self._wrapped_memberlist())
        if request.method == "GET" and path.endswith("/organisation/group"):
            return httpx.Response(_HTTP_OK, json={"membercount": len(self._members), "stats": {}})
        if request.method == "POST" and path.endswith("/organisation/update/membership"):
            return self._update(request)
        return httpx.Response(_HTTP_NOT_FOUND, json={"error": f"no route for {path}"})

    def _update(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        errors = validate_update_body(body, self.contract)
        if errors:  # per-member error strings, like the real 400 (§4)
            return httpx.Response(_HTTP_BAD_REQUEST, json=errors)
        hit = [m for m in body if m in self.fail_on]
        if hit:  # simulated operational failure for stop/resume/failure tests
            return httpx.Response(self.fail_status, json=dict.fromkeys(hit, "simulated failure"))
        for member_no, fields in body.items():
            if member_no in self._members and "troop_id" in fields:
                self._members[member_no]["troop_id"] = fields["troop_id"]
        return httpx.Response(_HTTP_OK, json={"status": "ok"})

    def _wrapped_memberlist(self) -> dict:
        data = {}
        for member_no, st in self._members.items():
            fields: dict = {
                "member_no": {"value": member_no},
                "status": {"value": "Aktiv", "raw_value": st.get("status", "2")},
            }
            if st.get("troop_id") is not None:
                fields["unit"] = {"value": st.get("unit", "Avd"), "raw_value": str(st["troop_id"])}
            if st.get("patrol_id") is not None:
                fields["patrol"] = {"value": "P", "raw_value": str(st["patrol_id"])}
            if st.get("leader"):
                tid = str(st.get("troop_id") or 999)
                fields["roles"] = {
                    "value": {
                        "troop": {
                            tid: {"1": {"role_id": 1, "role_key": "leader", "role_name": "L"}}
                        }
                    }
                }
            data[member_no] = fields
        return {"data": data, "labels": {"current_term": "Höst 2026", "prev_term": "Vår 2026"}}

    def troop_of(self, member_no: str) -> int | None:
        """Current troop_id of a member in the mock's state."""
        return self._members[member_no].get("troop_id")
