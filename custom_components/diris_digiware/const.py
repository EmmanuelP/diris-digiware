# SPDX-License-Identifier: AGPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Emmanuel Pacaud <emmanuel.pacaud@free.fr>

"""Constants for the Socomec DIRIS Digiware integration."""

from typing import Final

DOMAIN: Final = "diris_digiware"
DEFAULT_PORT: Final = 161
DEFAULT_SCAN_INTERVAL: Final = 30
MIN_SCAN_INTERVAL: Final = 30
CONF_SCAN_INTERVAL: Final = "scan_interval"

CIRCUIT_NAME_OID: Final = "1.3.6.1.4.1.4555.10.10.20.1.85054"
ACTIVE_ENERGY_OID: Final = "1.3.6.1.4.1.4555.10.10.20.12.1.30000"
ACTIVE_ENERGY_RESIDUAL_OID: Final = "1.3.6.1.4.1.4555.10.10.20.12.1.30001"
ACTIVE_POWER_OID: Final = "1.3.6.1.4.1.4555.10.10.20.20.1.80003"
