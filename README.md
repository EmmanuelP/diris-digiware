# Socomec DIRIS Digiware

Home Assistant integration for reading active energy and instantaneous active
power from Socomec DIRIS Digiware devices over SNMPv3 authPriv (HMAC-SHA
authentication and AES-CFB-128 privacy).

## Installation

1. Add this repository to HACS as a custom integration and install **Socomec
   DIRIS Digiware**, or copy `custom_components/diris_digiware` into your Home
   Assistant `custom_components` directory.
2. Restart Home Assistant.
3. Go to **Settings → Devices & services → Add integration** and select
   **Socomec DIRIS Digiware**.
4. Enter the device host, SNMP port, SNMP username, authentication key, and
   privacy key. Keys are entered using password fields and stored with the
   Home Assistant config entry. Home Assistant does not encrypt config-entry
   data at rest, so protect its configuration directory and backups.

The integration creates one Home Assistant device for each named circuit,
grouping its active-energy (kWh) and instantaneous active-power (W) sensors.
Energy includes the documented 1/10 Wh residual counter when available and is
kept non-decreasing across polls.

## Polling interval

The device is polled every 30 seconds by default. Change the **Polling interval
(seconds)** option in the integration's options to choose a different period.
Intervals shorter than 30 seconds are rejected, and the coordinator enforces
the same 30-second minimum as a guard.

## Created devices and entities

The integration uses each circuit's `circuitName` value as the start of both
sensor names. Examples from the supplied SNMP walk include:

- `Q13 - CENTRE  DE CALCUL`
- `Q5 - CHAUFFAGE BAT 4`
- `A-20 -CHAUFFAGE - L1`

For example, the device `Q5 - CHAUFFAGE BAT 4` contains:

```text
Q5 - CHAUFFAGE BAT 4 (device)
  Q5 - CHAUFFAGE BAT 4 Active energy (kWh)
  Q5 - CHAUFFAGE BAT 4 Active power (W)
```

Each named circuit has these entities:

| Entity | Device class | State class | Unit | Details |
| --- | --- | --- | --- | --- |
| Active energy | `energy` | `total_increasing` | kWh | Includes the 1/10 Wh residual counter when available; display precision is 4 decimal places. |
| Active power | `power` | `measurement` | W | Instantaneous total active power. |

Each circuit is a separate Home Assistant device named after its `circuitName`,
grouping its active-energy and active-power sensors. Device identifiers combine
the config-entry ID and circuit row indexes, so duplicate circuit names and
circuits on different gateways remain distinct.

Unique IDs combine the config-entry ID, a slugified circuit name, the SNMP
table row indexes, and the measurement key. This keeps sensors for circuits
with duplicate names distinct. Home Assistant generates entity IDs from the
sensor names; those entity IDs can be changed in the entity settings.

### Applying device grouping to an existing installation

After updating, reload the integration from **Settings → Devices & services**
using the integration entry's menu, or restart Home Assistant. Existing sensors
move from the shared gateway device to their respective circuit devices.
Sensor names, unique IDs, and existing entity IDs are preserved, so automations
and dashboards referencing those entity IDs do not need to be changed.

## License

This project is licensed under the
[GNU Affero General Public License v3.0 or later](LICENSE)
(`AGPL-3.0-or-later`).

The files in `docs/` are vendor reference material from Socomec and are not
covered by this license.

## Development

Install the project's test dependencies, then run:

```sh
ruff check .
pytest
```

Tests use Home Assistant's custom-component pytest fixtures and mock all SNMP
requests.
