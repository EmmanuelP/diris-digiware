# Socomec DIRIS Digiware

Home Assistant integration for reading energy counters and instantaneous power
from Socomec DIRIS Digiware devices over SNMPv3 authPriv (HMAC-SHA
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
grouping its energy and power sensors. Only active energy and active power are
enabled by default. Energy counters include the documented 1/10 unit residual
counter when available and are kept non-decreasing across polls.

## Polling interval

The device is polled every 30 seconds by default. Change the **Polling interval
(seconds)** option in the integration's options to choose a different period.
Intervals shorter than 30 seconds are rejected, and the coordinator enforces
the same 30-second minimum as a guard.

Circuit names are reread on every poll. Newly discovered named circuits
automatically get a device and their sensors, without reloading the integration.
Circuits that temporarily disappear are not deleted; their existing sensors
resume reporting when they return.

## Created devices and entities

The integration uses each circuit's `circuitName` value as the start of every
sensor name. Examples from the supplied SNMP walk include:

- `Q13 - CENTRE  DE CALCUL`
- `Q5 - CHAUFFAGE BAT 4`
- `A-20 -CHAUFFAGE - L1`

For example, the device `Q5 - CHAUFFAGE BAT 4` contains:

```text
Q5 - CHAUFFAGE BAT 4 (device)
  Q5 - CHAUFFAGE BAT 4 Active energy (kWh)
  Q5 - CHAUFFAGE BAT 4 Active power (W)
  Q5 - CHAUFFAGE BAT 4 Active energy production (kWh)     [disabled]
  Q5 - CHAUFFAGE BAT 4 Reactive energy (kvarh)            [disabled]
  Q5 - CHAUFFAGE BAT 4 Reactive energy production (kvarh) [disabled]
  Q5 - CHAUFFAGE BAT 4 Apparent energy (kVAh)             [disabled]
  Q5 - CHAUFFAGE BAT 4 Reactive power (var)               [disabled]
  Q5 - CHAUFFAGE BAT 4 Apparent power (VA)                [disabled]
```

Each named circuit has these entities:

| Entity | Enabled by default | Device class | State class | Unit | Details |
| --- | --- | --- | --- | --- | --- |
| Active energy | yes | `energy` | `total_increasing` | kWh | Total positive (consumed) active energy. |
| Active energy production | no | `energy` | `total_increasing` | kWh | Total negative (produced) active energy. |
| Reactive energy | no | `reactive_energy` | `total_increasing` | kvarh | Total positive reactive energy. |
| Reactive energy production | no | `reactive_energy` | `total_increasing` | kvarh | Total negative reactive energy. |
| Apparent energy | no | none | `total_increasing` | kVAh | Total apparent energy. Home Assistant has no apparent-energy device class. |
| Active power | yes | `power` | `measurement` | W | Instantaneous total active power (signed). |
| Reactive power | no | `reactive_power` | `measurement` | var | Instantaneous total reactive power (signed). |
| Apparent power | no | `apparent_power` | `measurement` | VA | Instantaneous total apparent power. |

Energy counters include the 1/10 unit residual counter when available and use
a display precision of 4 decimal places.

Disabled sensors cost nothing: the integration only queries the SNMP columns
of enabled sensors. Enable a sensor from its entity settings; Home Assistant
reloads the integration shortly afterwards and polling of that measurement
starts.

Each circuit is a separate Home Assistant device named after its `circuitName`,
grouping its sensors. Device identifiers combine
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

Tests use Home Assistant's custom-component pytest fixtures and mock SNMP
requests, except for a local loopback SNMPv3 regression test. That test exercises
authentication, encrypted responses, and repeated walks with the real library
while checking that MIB files are not read on the event loop. No physical device
or external network access is required.

The SNMP engine and bundled MIBs are initialized in a worker thread to avoid
blocking Home Assistant's event loop. Network requests remain asynchronous.

Measurement OIDs are also checked against the supplied
[SNMP walk](docs/snmpwalk.txt): circuit names and measurements use different
OID subtrees.
