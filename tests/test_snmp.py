# SPDX-License-Identifier: AGPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Emmanuel Pacaud <emmanuel.pacaud@free.fr>

"""Tests for SNMPv3 transport configuration."""

import pytest
from pysnmp.hlapi.v3arch.asyncio import (
    UsmUserData,
    usmAesCfb128Protocol,
    usmHMACSHAAuthProtocol,
)

from custom_components.diris_digiware import snmp


@pytest.mark.asyncio
async def test_walk_uses_snmpv3_auth_priv(monkeypatch) -> None:
    """Use the configured user and fixed HMAC-SHA/AES-CFB-128 protocols."""
    calls = {}

    async def create_target(address, **kwargs):
        assert address == ("meter.local", 161)
        return object()

    async def walk_cmd(*args, **kwargs):
        calls["auth_data"] = args[1]
        calls["options"] = kwargs
        if False:
            yield None

    monkeypatch.setattr(snmp.UdpTransportTarget, "create", create_target)
    monkeypatch.setattr(snmp, "walk_cmd", walk_cmd)

    async with snmp.SnmpClient(
        "meter.local", 161, "diris-user", "auth-secret", "priv-secret"
    ) as client:
        assert await client.walk("1.3.6.1.4.1.4555") == {}

    auth_data = calls["auth_data"]
    assert isinstance(auth_data, UsmUserData)
    assert auth_data.userName == "diris-user"
    assert auth_data.authentication_key == "auth-secret"
    assert auth_data.privacy_key == "priv-secret"
    assert auth_data.authentication_protocol == usmHMACSHAAuthProtocol
    assert auth_data.privacy_protocol == usmAesCfb128Protocol
