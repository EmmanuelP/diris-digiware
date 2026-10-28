# Decision log

Format: date, decision, rationale, alternatives rejected.

## 2026-10-28 – Energy precision from the residual counter
- Energy = engTotalEnergyActivePos (kWh) + engTotalEnergyActiveResidualPos / 10000
  (residual is in 1/10 Wh).
- The two reads are not atomic, so a per-circuit `max(current, last)` keeps the
  value monotonic (required by `TOTAL_INCREASING`).
- Rejected: using the kWh counter alone (coarse), trusting the residual to be in
  sync with the kWh value.

## 2026-10-28 – SNMPv3 with credentials in the config entry
- Auth hmac-sha, privacy aes-cfb-128, set by the user in the UI flow.
- Home Assistant does not encrypt config entries at rest; this is documented in
  the README.
- Rejected: SNMPv2c community string (the project rules require v3).

## 2026-10-28 – Several devices via several config entries
- Config-entry unique_id is `host:port`; no multi-device logic inside one entry.
- Rejected: one entry holding a list of hosts (harder to manage in the UI).

## 2026-10-28 – Configurable polling interval, 30 s minimum
- Options flow with `vol.Range(min=30)`; the coordinator also clamps the value.
- Rationale: avoid overloading the device and keep a safe lower bound.

## 2026-10-28 – Entity naming from circuitName
- Name is `<circuitName> Active energy|Active power`; unique_id is built from
  the entry id, the slugified name, the modbus address and the line.
- Rows from the circuit, energy and power tables are joined on the
  (modbusAddress, line) index pair.

## 2026-10-28 – Licensing
- Code: AGPL-3.0-or-later, with SPDX headers in `custom_components/` and `tests/`.
- Vendor MIB and walk in `docs/` are not covered by this license and carry no
  header.
