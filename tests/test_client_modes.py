from __future__ import annotations

import pytest

from scoutnet_membership_manager.scoutnet.client import (
    DEFAULT_FIXTURE,
    FixtureClient,
    ReadOnlyClient,
    ReadWriteClient,
    build_client,
)
from scoutnet_membership_manager.settings import MissingCredentialError, Mode, Settings

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
    assert len(ml) == 182
    # fixture mode is self-contained: organisation_group is synthesised
    agg = client.organisation_group()
    assert agg["membercount"] == 182


def test_fixture_mode_needs_no_credentials():
    settings = Settings(mode=Mode.FIXTURE, entity_id=None, memberlist_key=None)
    client = build_client(settings)
    assert isinstance(client, FixtureClient)


def test_read_only_without_credentials_fails_loudly():
    settings = Settings(mode=Mode.READ_ONLY, entity_id=None, memberlist_key=None)
    with pytest.raises(MissingCredentialError):
        build_client(settings)


def test_write_method_lives_only_on_read_write_client():
    # The single write method exists on ReadWriteClient and NOWHERE else (§6).
    assert hasattr(ReadWriteClient, "update_membership")
    assert not hasattr(FixtureClient, "update_membership")
    assert not hasattr(ReadOnlyClient, "update_membership")


def test_read_write_without_write_key_fails_loudly():
    # A memberlist key is not enough; read_write needs its own write key (§4).
    settings = Settings(
        mode=Mode.READ_WRITE, entity_id="1025", memberlist_key="k", update_membership_key=None
    )
    with pytest.raises(MissingCredentialError):
        build_client(settings)


def test_read_write_builds_client_when_write_key_present():
    settings = Settings(
        mode=Mode.READ_WRITE,
        entity_id="1025",
        memberlist_key="k",
        update_membership_key="w",
    )
    client = build_client(settings)
    assert isinstance(client, ReadWriteClient)
    # Still a read client too (reconciliation / re-read before write, §8).
    assert isinstance(client, ReadOnlyClient)
    client.close()
