"""Tiny async client for the Playground Dashboard API (v1)."""

from __future__ import annotations

import asyncio
from typing import Any

import aiohttp

from .const import API_PATH, REQUEST_TIMEOUT


class ApiError(Exception):
    """Generic API error (server error, bad response, ...)."""


class CannotConnect(ApiError):
    """Network, TLS or timeout error."""


class AuthError(ApiError):
    """Missing, invalid or revoked token (401)."""


class ForbiddenError(ApiError):
    """The key lacks the required scope (403)."""


class BusyError(ApiError):
    """Another host action is already running (409)."""


class NotReadyError(ApiError):
    """The server just started and has no sample yet (503)."""


class RateLimitedError(ApiError):
    """Too many invalid tokens from this IP (429)."""


def normalize_url(url: str) -> str:
    """Strip whitespace, trailing slashes and a trailing /api/v1."""
    url = url.strip().rstrip("/")
    if url.lower().endswith(API_PATH):
        url = url[: -len(API_PATH)].rstrip("/")
    return url


class PlaygroundDashboardApi:
    """Client for one dashboard instance."""

    def __init__(self, session: aiohttp.ClientSession, url: str, api_key: str) -> None:
        """Initialize the client."""
        self._session = session
        self._base = normalize_url(url) + API_PATH
        self._api_key = api_key

    async def _request(self, method: str, path: str) -> dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Accept": "application/json",
        }
        try:
            async with asyncio.timeout(REQUEST_TIMEOUT):
                async with self._session.request(
                    method, f"{self._base}{path}", headers=headers
                ) as resp:
                    if resp.status in (200, 202):
                        return await resp.json(content_type=None)
                    message = await self._error_message(resp)
        except (TimeoutError, aiohttp.ClientError) as err:
            raise CannotConnect(f"Error communicating with dashboard: {err}") from err
        except ValueError as err:
            raise ApiError(f"Invalid response from dashboard: {err}") from err

        status = resp.status
        text = f"HTTP {status}: {message}"
        if status == 401:
            raise AuthError(text)
        if status == 403:
            raise ForbiddenError(text)
        if status == 409:
            raise BusyError(text)
        if status == 429:
            raise RateLimitedError(text)
        if status == 503:
            raise NotReadyError(text)
        raise ApiError(text)

    @staticmethod
    async def _error_message(resp: aiohttp.ClientResponse) -> str:
        try:
            body = await resp.json(content_type=None)
        except (aiohttp.ClientError, ValueError):
            return resp.reason or "unknown error"
        if isinstance(body, dict) and body.get("error"):
            return str(body["error"])
        return resp.reason or "unknown error"

    async def ping(self) -> dict[str, Any]:
        """Validate the token; returns key name/scopes and hostname."""
        return await self._request("GET", "/ping")

    async def state(self) -> dict[str, Any]:
        """Return the full state."""
        return await self._request("GET", "/state")

    async def action(self, name: str) -> dict[str, Any]:
        """Queue a host action (check, upgrade, reboot)."""
        return await self._request("POST", f"/actions/{name}")
