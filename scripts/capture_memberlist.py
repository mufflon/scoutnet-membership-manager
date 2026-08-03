#!/usr/bin/env python3
"""Phase 0 capture: one live GET /group/memberlist call.

Throwaway spike script (CLAUDE.md §7). Stdlib only, no dependencies — run it
with a bare `python3`. It makes a single live call, writes the raw JSON to a
gitignored directory, and prints ONLY the structure of the response: key names,
value types, list lengths and counts. It never prints a single value, so its
stdout is safe to paste back here.

Usage:

    SCOUTNET_ENTITY_ID=<internal entity id> \\
    SCOUTNET_API_KEY=<memberlist api key> \\
        python3 scripts/capture_memberlist.py

Environment variables:

    SCOUTNET_ENTITY_ID   (required) HTTP Basic username. The body's INTERNAL
                         entity ID, which may NOT equal the visible kår number
                         (CLAUDE.md §4). Find it in the group home-page URL or
                         the example URLs on the Webbkoppling page.
    SCOUTNET_API_KEY     (required) HTTP Basic password. The per-endpoint key
                         for /group/memberlist specifically — keys are per
                         endpoint, valid nowhere else.
    SCOUTNET_BASE_URL    (optional) Default https://scoutnet.se/api
                         Test server: https://s1.test.custard.no/api
    SCOUTNET_VARIANT     (optional) active | waiting | awaiting_approval.
                         Default active. `waiting` and `awaiting_approval`
                         return those members INSTEAD of active ones, so each
                         is a separate call (CLAUDE.md §4).

Nothing secret is printed. Credentials are read from the environment only and
never echoed.
"""

from __future__ import annotations

import base64
import json
import os
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

REQUIRED_VARS = ("SCOUTNET_ENTITY_ID", "SCOUTNET_API_KEY")
DEFAULT_BASE_URL = "https://scoutnet.se/api"
VARIANTS = {
    "active": {},
    "waiting": {"waiting": "1"},
    "awaiting_approval": {"awaiting_approval": "1"},
}
CAPTURES_DIR = Path(__file__).resolve().parent.parent / "captures"
REQUEST_TIMEOUT_S = 60


def die(msg: str, code: int = 2) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(code)


def read_config() -> tuple[str, str, str, str, dict[str, str]]:
    missing = [v for v in REQUIRED_VARS if not os.environ.get(v)]
    if missing:
        die(
            "missing required environment variable(s): " + ", ".join(missing) + "\n\nRun it like:\n"
            "    SCOUTNET_ENTITY_ID=<entity id> SCOUTNET_API_KEY=<key> \\\n"
            "        python3 scripts/capture_memberlist.py\n\n"
            "See the module docstring for what each variable is."
        )
    entity_id = os.environ["SCOUTNET_ENTITY_ID"].strip()
    api_key = os.environ["SCOUTNET_API_KEY"].strip()
    base_url = os.environ.get("SCOUTNET_BASE_URL", DEFAULT_BASE_URL).strip().rstrip("/")

    variant = os.environ.get("SCOUTNET_VARIANT", "active").strip().lower()
    if variant not in VARIANTS:
        die(f"SCOUTNET_VARIANT must be one of {sorted(VARIANTS)}, got {variant!r}")
    return entity_id, api_key, base_url, variant, VARIANTS[variant]


def build_ssl_context() -> ssl.SSLContext:
    """Verified TLS. Some Python installs (conda, python.org without the cert
    installer) ship no usable CA bundle, so prefer certifi's when it is
    importable; fall back to the system defaults otherwise. Verification is
    never disabled — this call carries real personal data."""
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def fetch(base_url: str, entity_id: str, api_key: str, params: dict[str, str]) -> bytes:
    url = f"{base_url}/group/memberlist"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    token = base64.b64encode(f"{entity_id}:{api_key}".encode()).decode("ascii")
    req = urllib.request.Request(url, method="GET")
    req.add_header("Authorization", f"Basic {token}")
    req.add_header("Accept", "application/json")
    try:
        ctx = build_ssl_context()
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_S, context=ctx) as resp:
            return resp.read()
    except urllib.error.HTTPError as e:
        hint = {
            401: " — check SCOUTNET_ENTITY_ID (internal entity id, not the kår "
            "number) and that the key is the memberlist key.",
            400: " — the request was rejected; check the variant/params.",
        }.get(e.code, "")
        die(f"HTTP {e.code} {e.reason} from {url}{hint}", code=1)
    except urllib.error.URLError as e:
        hint = ""
        if "CERTIFICATE_VERIFY" in str(e.reason):
            hint = (
                "\n  TLS cert verification failed — your Python has no CA bundle. "
                "Fix by installing certifi in this env (`pip install certifi`, it is "
                "then used automatically), or run with "
                'SSL_CERT_FILE="$(python3 -m certifi)" prefixed.'
            )
        die(f"could not reach {url}: {e.reason}{hint}", code=1)


def type_name(v: object) -> str:
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "bool"
    if isinstance(v, dict):
        return "object"
    if isinstance(v, list):
        return "array"
    if isinstance(v, str):
        return "string"
    if isinstance(v, (int, float)):
        return "number"
    return type(v).__name__


class FieldStats:
    """Structural aggregate for one member field. Holds no values — only key
    names, type names, and counts/lengths."""

    def __init__(self) -> None:
        self.present_in = 0
        self.wrapper_keysets: Counter[str] = Counter()
        self.value_types: Counter[str] = Counter()
        self.raw_value_types: Counter[str] = Counter()
        self.unwrapped_types: Counter[str] = Counter()
        self.list_lengths: list[int] = []

    def observe(self, field_value: object) -> None:
        self.present_in += 1
        if isinstance(field_value, dict):
            self.wrapper_keysets["{" + ",".join(sorted(field_value)) + "}"] += 1
            if "value" in field_value:
                inner = field_value["value"]
                self.value_types[type_name(inner)] += 1
                if isinstance(inner, list):
                    self.list_lengths.append(len(inner))
            if "raw_value" in field_value:
                self.raw_value_types[type_name(field_value["raw_value"])] += 1
        else:
            # Field not wrapped in {value, raw_value}. Permitted and worth noting.
            self.unwrapped_types[type_name(field_value)] += 1
            if isinstance(field_value, list):
                self.list_lengths.append(len(field_value))


def analyse(payload: object) -> None:
    print("=" * 72)
    print("STRUCTURE (no values printed)")
    print("=" * 72)

    if not isinstance(payload, dict):
        print(f"Top-level JSON is {type_name(payload)}, expected object. Stopping.")
        return

    print(f"\nTop-level keys: {sorted(payload)}")
    for k in sorted(payload):
        print(f"  {k!r}: {type_name(payload[k])}")

    data = payload.get("data")
    labels = payload.get("labels")

    if not isinstance(data, dict):
        print(f"\n'data' is {type_name(data)}, expected object keyed by member_no.")
        return

    members = data
    member_count = len(members)
    print(f"\nMember entries in 'data': {member_count}")
    print(
        "(top-level keys are member numbers; a dict cannot hold duplicate keys, "
        "so a member cannot appear twice at this level — any multi-membership "
        "must show up as list-typed fields below)"
    )

    # Are member_no keys mirrored by a member_no field inside each entry?
    entry_types: Counter[str] = Counter()
    fields: dict[str, FieldStats] = {}
    for entry in members.values():
        entry_types[type_name(entry)] += 1
        if not isinstance(entry, dict):
            continue
        for fname, fval in entry.items():
            fields.setdefault(fname, FieldStats()).observe(fval)

    print(f"Member-entry value types: {dict(entry_types)}")

    print(f"\nDistinct field names across all members: {len(fields)}")
    print(f"{'field':<32} {'present':>8}/{member_count:<6} shape")
    print("-" * 72)
    for fname in sorted(fields):
        st = fields[fname]
        bits: list[str] = []
        wrappers = ", ".join(f"{ks}×{n}" for ks, n in st.wrapper_keysets.most_common())
        if wrappers:
            bits.append(f"wrapper={wrappers}")
        if st.value_types:
            bits.append(f"value:{dict(st.value_types)}")
        if st.raw_value_types:
            bits.append(f"raw_value:{dict(st.raw_value_types)}")
        if st.unwrapped_types:
            bits.append(f"UNWRAPPED:{dict(st.unwrapped_types)}")
        if st.list_lengths:
            bits.append(
                f"list_len[min={min(st.list_lengths)},max={max(st.list_lengths)},"
                f"n_lists={len(st.list_lengths)}]"
            )
        flag = "  <-- multi-valued" if st.list_lengths and max(st.list_lengths) > 1 else ""
        print(f"{fname:<32} {st.present_in:>8}/{member_count:<6} {'; '.join(bits)}{flag}")

    # Labels
    print()
    if isinstance(labels, dict):
        label_keys = set(labels)
        data_field_keys = set(fields)
        print(f"'labels' keys: {len(label_keys)}")
        only_in_data = sorted(data_field_keys - label_keys)
        only_in_labels = sorted(label_keys - data_field_keys)
        print(f"  field keys with NO label: {only_in_data or 'none'}")
        print(f"  label keys with NO data field: {only_in_labels or 'none'}")
    else:
        print(f"'labels' is {type_name(labels)} (expected object).")

    print("\n" + "=" * 72)
    print(
        "Field NAMES above are safe to share. Do NOT paste the raw capture "
        "file — it contains real personal data and is gitignored."
    )
    print("=" * 72)


def main() -> None:
    entity_id, api_key, base_url, variant, params = read_config()

    print(f"GET {base_url}/group/memberlist  (variant={variant})")
    print(f"Auth: HTTP Basic as entity id {'*' * len(entity_id)} (hidden)")
    raw = fetch(base_url, entity_id, api_key, params)

    CAPTURES_DIR.mkdir(exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out = CAPTURES_DIR / f"memberlist-{variant}-{stamp}.raw.json"
    out.write_bytes(raw)
    print(f"Raw JSON written to: {out}  ({len(raw)} bytes)")
    print("This file is gitignored (captures/ and *.raw.json). Keep it local.\n")

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as e:
        die(f"response is not valid JSON: {e}. Raw file saved at {out} for inspection.")

    analyse(payload)


if __name__ == "__main__":
    main()
