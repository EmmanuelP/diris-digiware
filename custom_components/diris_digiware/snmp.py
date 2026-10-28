# SPDX-License-Identifier: AGPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Emmanuel Pacaud <emmanuel.pacaud@free.fr>

"""Asynchronous SNMP access for DIRIS Digiware devices."""

from __future__ import annotations

from collections.abc import AsyncIterator

from pysnmp.error import PySnmpError
from pysnmp.hlapi.v3arch.asyncio import (
    ContextData,
    ObjectIdentity,
    ObjectType,
    SnmpEngine,
    UdpTransportTarget,
    UsmUserData,
    usmAesCfb128Protocol,
    usmHMACSHAAuthProtocol,
    walk_cmd,
)


class SnmpCommunicationError(Exception):
    """Raised when an SNMP request fails."""


class SnmpClient:
    """Read indexed columns from a device using SNMPv3 authPriv."""

    def __init__(
        self, host: str, port: int, username: str, auth_key: str, priv_key: str
    ) -> None:
        self._host = host
        self._port = port
        self._username = username
        self._auth_key = auth_key
        self._priv_key = priv_key
        self._engine = SnmpEngine()
        self._target: UdpTransportTarget | None = None

    async def __aenter__(self) -> SnmpClient:
        """Create the asynchronous UDP transport target."""
        try:
            self._target = await UdpTransportTarget.create(
                (self._host, self._port), timeout=3, retries=1
            )
        except (PySnmpError, OSError, TimeoutError) as err:
            raise SnmpCommunicationError(
                f"Unable to create the SNMP transport: {err}"
            ) from err
        return self

    async def __aexit__(self, *_: object) -> None:
        """Release the transport dispatcher."""
        self._engine.close_dispatcher()

    async def walk(self, oid: str) -> dict[tuple[int, ...], int | str]:
        """Walk an OID column and return its indexed values."""
        if self._target is None:
            raise RuntimeError("SNMP client must be entered before use")

        base_oid = tuple(int(part) for part in oid.split("."))
        values: dict[tuple[int, ...], int | str] = {}
        try:
            results: AsyncIterator = walk_cmd(
                self._engine,
                UsmUserData(
                    self._username,
                    self._auth_key,
                    self._priv_key,
                    authProtocol=usmHMACSHAAuthProtocol,
                    privProtocol=usmAesCfb128Protocol,
                ),
                self._target,
                ContextData(),
                ObjectType(ObjectIdentity(oid)),
                lexicographicMode=False,
            )
            async for indication, status, index, bindings in results:
                if indication:
                    raise SnmpCommunicationError(str(indication))
                if status:
                    raise SnmpCommunicationError(
                        f"SNMP error {status.prettyPrint()} at varbind {index}"
                    )

                for object_name, value in bindings:
                    object_oid = tuple(int(part) for part in object_name)
                    if object_oid[: len(base_oid)] != base_oid:
                        continue
                    suffix = object_oid[len(base_oid) :]
                    if not suffix:
                        continue
                    value_text = value.prettyPrint()
                    try:
                        values[suffix] = int(value_text)
                    except ValueError:
                        values[suffix] = value_text
        except SnmpCommunicationError:
            raise
        except (PySnmpError, OSError, TimeoutError) as err:
            raise SnmpCommunicationError(f"Unable to read OID {oid}: {err}") from err
        return values
