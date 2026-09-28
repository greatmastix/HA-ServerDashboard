"""Constants for the Playground Dashboard integration."""

from __future__ import annotations

import re
from datetime import timedelta
from typing import Final

DOMAIN: Final = "playground_dashboard"

CONF_SCOPES: Final = "scopes"
CONF_HOSTNAME: Final = "hostname"
CONF_CONTAINERS: Final = "containers"
CONF_SITES: Final = "sites"

DEFAULT_SCAN_INTERVAL: Final = 30
MIN_SCAN_INTERVAL: Final = 10
MAX_SCAN_INTERVAL: Final = 3600

# Poll interval while a host action is queued/running.
FAST_SCAN_INTERVAL: Final = timedelta(seconds=5)
# How long to poll fast after pressing a button, even if `busy` isn't set yet.
ACTION_BOOST: Final = timedelta(seconds=30)

REQUEST_TIMEOUT: Final = 10
API_PATH: Final = "/api/v1"

SCOPE_READ: Final = "read"
SCOPE_CONTROL: Final = "control"

ACTION_CHECK: Final = "check"
ACTION_UPGRADE: Final = "upgrade"
ACTION_REBOOT: Final = "reboot"

TOKEN_RE: Final = re.compile(r"^pgd_[0-9a-f]{12}_[A-Za-z0-9_-]{43}$")
