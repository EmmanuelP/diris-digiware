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

The integration creates active-energy (kWh) and active-power (W) sensors for
each named circuit. Energy includes the documented 1/10 Wh residual counter
when available and is kept non-decreasing across polls.

## Polling interval

The device is polled every 30 seconds by default. Change the **Polling interval
(seconds)** option in the integration's options to choose a different period.
Intervals shorter than 30 seconds are rejected, and the coordinator enforces
the same 30-second minimum as a guard.

## Created entities

The integration uses each circuit's `circuitName` value as the start of both
sensor names. Examples from the supplied SNMP walk include:

- `Q13 - CENTRE  DE CALCUL`
- `Q5 - CHAUFFAGE BAT 4`
- `A-20 -CHAUFFAGE - L1`

For `Q5 - CHAUFFAGE BAT 4`, the two sensor names are:

- `Q5 - CHAUFFAGE BAT 4 Active energy`
- `Q5 - CHAUFFAGE BAT 4 Active power`

Each named circuit has these entities:

| Entity | Device class | State class | Unit | Details |
| --- | --- | --- | --- | --- |
| Active energy | `energy` | `total_increasing` | kWh | Includes the 1/10 Wh residual counter when available; display precision is 4 decimal places. |
| Active power | `power` | `measurement` | W | Instantaneous total active power. |

Unique IDs combine the config-entry ID, a slugified circuit name, the SNMP
table row indexes, and the measurement key. This keeps sensors for circuits
with duplicate names distinct. Home Assistant generates entity IDs from the
sensor names; those entity IDs can be changed in the entity settings.

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
