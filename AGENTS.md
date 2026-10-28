# Project: Home Assistant custom integration for Socomec DIRIS Digiware (SNMP)
- Domain: `diris_digiware`; HACS-compatible custom integration.
- Use a UI config flow only (no YAML). Use `DataUpdateCoordinator` for polling.
- Use an async SNMP library (`pysnmp`/`pysnmp-lextudio`), declared in manifest `requirements`. Never block the event loop.
- SNMP version is v3. User should be able to configure host, port (default: 161), username, auth_key (auth_protocol is hmac-sha) and priv_key (priv_protocol is aes-cfb-128). Store credentials securely.
- OIDs come only from docs/ (MIB, snmpwalk). Never invent OIDs; ask if missing.
- Sensors must set device_class, state_class and native_unit_of_measurement.
- Follow the Home Assistant developer docs and the quality scale (Bronze first).
- Include pytest tests using `pytest-homeassistant-custom-component`, with SNMP mocked.
- Run ruff and pytest after each change.
- Create entities for active energy (engTotalEnergyActivePos) and instant active power (instTotalPowerActive).
- If possible, improve energy precision by using the residual counter in dWh stored in engTotalEnergyActiveResidualPos, taking care about the fact reading of engTotalEnergyActivePos and engTotalEnergyActiveResidualPos is not atomic, residual reading is not always in sync with the kWh value, index should always be increasing.
- All counters are listed in circuitName values. Use this string to build the entity name and unique_id.
## Decision log
- Record every non-trivial design decision in `docs/decisions.md` before
  finishing a task: what was decided, why, and the alternatives rejected.
- Read `docs/decisions.md` at the start of a session and do not contradict an
  existing decision without asking the user; if a decision changes, add a new
  entry that supersedes the old one instead of deleting it.
- Keep entries short (a few lines), dated, and newest last.
- Do not record routine changes; use commit messages for those.