from __future__ import annotations

import pytest

from karverktyg.scoutnet.client import (
    DEFAULT_FIXTURE,
    FixtureClient,
    ReadOnlyClient,
    build_client,
)
from karverktyg.settings import MissingCredentialError, Mode, Settings

# Names that would indicate a write path. None may exist on a read client (§6).
FORBIDDEN = (
    "update_membership",
    "register_member",
    "checkin",
    "update",
    "register",
    "write",
    "post",
    "create",
    "delete",
    "cancel",
)


@pytest.mark.parametrize("cls", [FixtureClient, ReadOnlyClient])
def test_no_write_methods_on_read_clients(cls):
    for name in FORBIDDEN:
        assert not hasattr(cls, name), f"{cls.__name__} exposes write-like method {name!r}"


def test_fixture_client_loads_committed_fixture():
    client = FixtureClient(DEFAULT_FIXTURE)
    ml = client.memberlist()
    assert len(ml) == 371
    # fixture mode is self-contained: organisation_group is synthesised
    agg = client.organisation_group()
    assert agg["membercount"] == 371


def test_fixture_mode_needs_no_credentials():
    settings = Settings(mode=Mode.FIXTURE, entity_id=None, memberlist_key=None)
    client = build_client(settings)
    assert isinstance(client, FixtureClient)


def test_read_only_without_credentials_fails_loudly():
    settings = Settings(mode=Mode.READ_ONLY, entity_id=None, memberlist_key=None)
    with pytest.raises(MissingCredentialError):
        build_client(settings)


def test_read_write_mode_is_absent_in_phase_1():
    settings = Settings(mode=Mode.READ_WRITE, entity_id="1025", memberlist_key="k")
    with pytest.raises(NotImplementedError):
        build_client(settings)
