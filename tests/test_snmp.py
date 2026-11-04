# SPDX-License-Identifier: AGPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Emmanuel Pacaud <emmanuel.pacaud@free.fr>

"""Tests for SNMPv3 transport configuration."""

import asyncio
import threading
from unittest.mock import AsyncMock, Mock

import pytest
from pysnmp.carrier.asyncio.dgram import udp
from pysnmp.entity import config
from pysnmp.entity.rfc3413 import cmdrsp, context
from pysnmp.error import PySnmpError
from pysnmp.hlapi.v3arch.asyncio import (
    SnmpEngine,
    UsmUserData,
    usmAesCfb128Protocol,
    usmHMACSHAAuthProtocol,
)
from pysnmp.smi.builder import DirMibSource

from custom_components.diris_digiware import snmp
from custom_components.diris_digiware.const import CIRCUIT_NAME_OID


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
    assert calls["options"]["lookupMib"] is False


@pytest.mark.parametrize("error", [PySnmpError("MIB load failed"), OSError("disk")])
async def test_engine_initialization_failure_is_reported(monkeypatch, error):
    """Report worker initialization errors through the normal connection path."""
    monkeypatch.setattr(
        snmp.UdpTransportTarget, "create", AsyncMock(return_value=object())
    )
    monkeypatch.setattr(snmp.SnmpClient, "_create_engine", Mock(side_effect=error))
    client = snmp.SnmpClient(
        "meter.local", 161, "diris-user", "auth-secret", "priv-secret"
    )
    with pytest.raises(snmp.SnmpCommunicationError, match="initialize"):
        async with client:
            pytest.fail("Initialization should have failed")
    assert client._engine is None
    assert client._target is None


async def test_cancelled_walk_closes_dispatcher(monkeypatch):
    """Cancellation still releases the initialized engine and transport."""
    monkeypatch.setattr(
        snmp.UdpTransportTarget, "create", AsyncMock(return_value=object())
    )

    async def cancelled_walk(*args, **kwargs):
        raise asyncio.CancelledError
        yield

    monkeypatch.setattr(snmp, "walk_cmd", cancelled_walk)
    with pytest.raises(asyncio.CancelledError):
        async with snmp.SnmpClient(
            "meter.local", 161, "diris-user", "auth-secret", "priv-secret"
        ) as client:
            close = Mock(wraps=client._engine.close_dispatcher)
            monkeypatch.setattr(client._engine, "close_dispatcher", close)
            await client.walk(CIRCUIT_NAME_OID)
    close.assert_called_once()
    assert client._engine is None
    assert client._target is None


async def test_real_snmpv3_walk_does_not_read_mibs_on_event_loop(
    monkeypatch, socket_enabled
):
    """Exercise discovery, authPriv and response processing with real pysnmp."""
    column = tuple(int(part) for part in CIRCUIT_NAME_OID.split("."))

    def create_agent():
        engine = SnmpEngine()
        builder = engine.get_mib_builder()
        builder.load_modules()
        config.add_v3_user(
            engine,
            "diris-user",
            usmHMACSHAAuthProtocol,
            "auth-secret",
            usmAesCfb128Protocol,
            "priv-secret",
        )
        config.add_vacm_user(engine, 3, "diris-user", "authPriv", column)
        scalar, instance = builder.import_symbols(
            "SNMPv2-SMI", "MibScalar", "MibScalarInstance"
        )
        (display_string,) = builder.import_symbols("SNMPv2-TC", "DisplayString")
        builder.export_symbols(
            "TEST-CIRCUIT",
            scalar(column + (3,), display_string()).setMaxAccess("read-only"),
            instance(column + (3,), (1,), display_string("Main circuit")),
        )
        agent_context = context.SnmpContext(engine)
        cmdrsp.NextCommandResponder(engine, agent_context)
        return engine

    agent = await asyncio.to_thread(create_agent)
    transport = udp.UdpAsyncioTransport().open_server_mode(("127.0.0.1", 0))
    config.add_transport(agent, udp.DOMAIN_NAME, transport)
    try:
        await transport._lport
        port = transport.transport.get_extra_info("sockname")[1]
        loop_thread = threading.get_ident()
        original_read = DirMibSource.read
        reads = []

        def guarded_read(self, *args, **kwargs):
            assert threading.get_ident() != loop_thread, "MIB I/O on event loop"
            reads.append(args)
            return original_read(self, *args, **kwargs)

        monkeypatch.setattr(DirMibSource, "read", guarded_read)
        async with asyncio.timeout(10):
            async with snmp.SnmpClient(
                "127.0.0.1", port, "diris-user", "auth-secret", "priv-secret"
            ) as client:
                engine = client._engine
                close = Mock(wraps=engine.close_dispatcher)
                monkeypatch.setattr(engine, "close_dispatcher", close)
                assert await client.walk(CIRCUIT_NAME_OID) == {(3, 1): "Main circuit"}
                assert await client.walk(CIRCUIT_NAME_OID) == {(3, 1): "Main circuit"}
        assert reads
        close.assert_called_once()
        assert client._engine is None
    finally:
        agent.close_dispatcher()
