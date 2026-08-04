"""
Application settings (CLAUDE.md §6, §13).

All configuration is environment-driven through pydantic-settings. Secrets
(API keys, DB password) come from the environment only and never from the repo
(Hard rule #1). ``require_live_credentials`` fails loudly when a key needed for
the active mode is missing.
"""

from __future__ import annotations

import enum
import hashlib
import os
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import (
    BaseSettings,
    JsonConfigSettingsSource,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

from karverktyg.config.models import SCHEMA_VERSION, KarConfig


class Mode(enum.StrEnum):
    """
    Deployment-level capability switch (§6). Enforced at client construction:
    in the wrong mode the write methods do not exist on the client object.
    """

    FIXTURE = "fixture"
    READ_ONLY = "read_only"
    READ_WRITE = "read_write"


class MissingCredentialError(RuntimeError):
    """Raised at startup when a key required by the active mode is absent."""


# Fingerprint method for endpoint keys (§12) — kept as constants so the UI can
# state exactly how to reproduce it. Fingerprint = ALGO(key UTF-8 bytes) hex,
# truncated to CHARS characters.
FINGERPRINT_ALGO = "sha256"
FINGERPRINT_CHARS = 8


def _truncated_hash(secret: SecretStr | None) -> str | None:
    """
    Return a short, non-reversible fingerprint of a key for the capabilities page
    (§12) — never the key itself.
    """
    if secret is None:
        return None
    digest = hashlib.new(FINGERPRINT_ALGO, secret.get_secret_value().encode()).hexdigest()
    return digest[:FINGERPRINT_CHARS]


class Settings(BaseSettings):
    """Settings."""

    model_config = SettingsConfigDict(
        env_prefix="SCOUTNET_",
        env_file=".env",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Mode --------------------------------------------------------------
    mode: Mode = Mode.READ_ONLY

    # --- Scoutnet API ------------------------------------------------------
    base_url: str = "https://scoutnet.se/api"
    entity_id: str | None = None  # HTTP Basic username = internal entity id
    # Keys are per endpoint (§4). Read-only Phase 1 uses these two.
    memberlist_key: SecretStr | None = None
    organisation_group_key: SecretStr | None = None
    # Write key (§4, Phase 2). Required only in read_write mode; a separate
    # per-endpoint key for POST /organisation/update/membership.
    update_membership_key: SecretStr | None = None
    http_timeout_s: float = 30.0

    # --- Database (§9) -----------------------------------------------------
    # None => fixture mode uses an ephemeral in-memory SQLite (no infrastructure).
    # Set it (e.g. to Postgres) to make fixture-mode state persist; required for
    # read_only / read_write.
    database_url: str | None = None

    # --- Kår identity (§13) ------------------------------------------------
    kar_name: str = "Scoutkåren Finn"

    # --- Uppflyttning config (§13, §17) ------------------------------------
    # The single non-secret config file (karverktyg.json) provides mode,
    # cohort_year, entity_id and the kår below; the API keys come from the
    # environment only (apikeys.conf → env/Secret). See settings_customise_sources.
    config_path: Path = Path("karverktyg.json")
    # The config-file schema version, so a file can be verified against (and
    # migrated to) the current schema. Lives at the file root, not inside `kar`.
    schema_version: int = SCHEMA_VERSION
    # The kår: name + avdelningar (§13). Empty => avdelningar inferred from data.
    kar: KarConfig = KarConfig()
    # Cohort year N. None => derive from the live term, guarded by the config
    # cross-check (§17). Set explicitly in production.
    cohort_year: int | None = None

    # --- Write knobs (Phase 2; present so config is stable across phases) ---
    # Default 1: one member per request needs no atomicity guarantee (§8,
    # HANDOVER §4). Raising it is a deliberate decision requiring observed
    # evidence of the endpoint's partial-failure behaviour.
    chunk_size: int = 1
    chunk_delay_s: float = 1.0
    snapshot_retention_days: int = 30
    # Full-memberlist snapshot volume (§8). Required for a bulk run in
    # read_write; enforced at the executor, not here, since read_write can
    # start (e.g. a dry run) before any bulk write.
    snapshot_dir: Path | None = None
    # Member-number allowlist for the write testing stages (§8, HANDOVER §4).
    # The executor refuses any member_no not on this list. Numbers only, never
    # names (hard rule 6). Empty list => nothing may be written (fail closed).
    write_allowlist: list[str] = []

    # --- App ---------------------------------------------------------------
    app_version: str = "0.1.0"
    build_number: str = "dev"

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """
        Read the non-secret config JSON, with env (the keys) taking precedence.

        Order: explicit init args > environment (the API keys from apikeys.conf) >
        .env > the karverktyg.json file > file secrets. SCOUTNET_CONFIG_PATH picks
        the file; a missing file simply contributes nothing (the app then infers).
        """
        path = Path(os.environ.get("SCOUTNET_CONFIG_PATH", "karverktyg.json"))
        sources: list[PydanticBaseSettingsSource] = [init_settings, env_settings, dotenv_settings]
        if path.is_file():
            sources.append(JsonConfigSettingsSource(settings_cls, json_file=path))
        sources.append(file_secret_settings)
        return tuple(sources)

    def require_live_credentials(self) -> None:
        """
        Fail loudly when the active mode needs live keys but they are absent
        (Hard rule #1). ``fixture`` needs none.
        """
        if self.mode is Mode.FIXTURE:
            return
        missing: list[str] = []
        if not self.entity_id:
            missing.append("SCOUTNET_ENTITY_ID")
        if self.memberlist_key is None:
            missing.append("SCOUTNET_MEMBERLIST_KEY")
        # read_write additionally needs its own per-endpoint write key (§4).
        if self.mode is Mode.READ_WRITE and self.update_membership_key is None:
            missing.append("SCOUTNET_UPDATE_MEMBERSHIP_KEY")
        if missing:
            raise MissingCredentialError(
                f"mode={self.mode.value} requires live credentials, missing: " + ", ".join(missing)
            )

    def endpoint_key_fingerprints(self) -> dict[str, str | None]:
        """
        Presence + truncated hash per endpoint key, for the capabilities
        page (§12). Never exposes a key.
        """
        return {
            "group/memberlist": _truncated_hash(self.memberlist_key),
            "organisation/group": _truncated_hash(self.organisation_group_key),
            "organisation/update/membership": _truncated_hash(self.update_membership_key),
        }
