"""Fixtures for Playground Dashboard tests."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.playground_dashboard.const import CONF_HOSTNAME, CONF_SCOPES, DOMAIN

URL = "https://dashboard.example.com"
API = f"{URL}/api/v1"
# Fake token that matches the format regex; not a real key.
TOKEN = "pgd_0123456789ab_" + "A" * 43
TOKEN2 = "pgd_ba9876543210_" + "B" * 43

FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str) -> dict[str, Any]:
    """Load a JSON fixture (fresh copy)."""
    return copy.deepcopy(json.loads((FIXTURES / name).read_text()))


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable custom integrations in all tests."""
    return


@pytest.fixture
def state() -> dict[str, Any]:
    """The /state fixture."""
    return load("state.json")


@pytest.fixture
def ping() -> dict[str, Any]:
    """The /ping fixture."""
    return load("ping.json")


def make_entry(scopes: list[str] | None = None, options: dict | None = None) -> MockConfigEntry:
    """Create a config entry."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="myhost",
        unique_id="myhost",
        data={
            "url": URL,
            "api_key": TOKEN,
            "verify_ssl": True,
            CONF_SCOPES: scopes if scopes is not None else ["read", "control"],
            CONF_HOSTNAME: "myhost",
        },
        options=options or {},
    )
