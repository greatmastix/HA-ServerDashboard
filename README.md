# Playground Dashboard for Home Assistant

> [!WARNING]
> **This repository is not useful to anyone but me.**
>
> It is a Home Assistant integration for my own private, self-built server dashboard. That dashboard is not
> published anywhere, so there's nothing for this integration to connect to on your end. It's public only so I
> can install it via HACS. No support, no feature requests, no guarantees.

A [Home Assistant](https://www.home-assistant.io/) custom integration for the self-hosted
**Playground Dashboard** server dashboard. It polls the dashboard's `/api/v1/state` endpoint and exposes host
metrics, Docker containers, public sites, pending system updates and (optionally) host maintenance actions.

## Installation (HACS)

1. In HACS open the menu (⋮) → **Custom repositories**.
2. Add `https://github.com/greatmastix/HA-ServerDashboard` with category **Integration**.
3. Install **Playground Dashboard** and restart Home Assistant.
4. **Settings → Devices & services → Add integration → Playground Dashboard**.

Manual install: copy `custom_components/playground_dashboard` into your `config/custom_components/` folder.

## Creating an API key

In the dashboard click **API keys** and create a key (the full token is shown only once; it looks like
`pgd_<12 hex>_<43 chars>`).

- Every key can **read**.
- Tick **control** only if you want the *Check for updates*, *Install updates* and *Reboot* buttons (and the
  install action on the update entity). Without `control` those entities aren't created.

If a key is revoked, Home Assistant shows a re-authentication prompt where you paste a new key.

## Configuration

| Field | Description |
|---|---|
| Dashboard URL | Base URL of your dashboard, e.g. `https://dashboard.example.com` (a trailing `/api/v1` is stripped) |
| API key | The token from above |
| Verify SSL certificate | Leave on unless you use a self-signed certificate |

**Options** (Configure button): polling interval (default 30 s, minimum 10 s), and toggles for container and
site entities. While a host action is running the integration polls every 5 s.

## Entities

One device per server (named after its hostname). Each container gets its own sub-device.

**Host sensors:** CPU, Load (1 min; 5/15 min disabled by default), Memory used (%), Memory used (bytes)\*,
Swap used (only if swap exists), Disk used (%), Disk free, Disk read/write\*, Network in/out,
Network total in/out\*, CPU IOwait/steal\*, Last boot, Containers running, Sites up, Cert min days left,
Pending updates (package list in attributes), Pending security updates, Last host job.

**Host binary sensors:** Reboot required, Maintenance running, Service `<name>` (caddy, dockerd, …).

**Per container:** Running, Health (only if the container has a healthcheck; *on* = problem), CPU\*, Memory\*.

**Per site:** Site `<name>` (connectivity; attributes: url, aliases, http_status, response_ms, error,
failing_host), Site `<name>` cert expiry.

**Update:** System packages (on when apt has pending updates; release notes list the packages; install runs
`apt full-upgrade` if the key has `control`).

**Buttons** (`control` only): Check for updates, Install updates, Reboot.

\* disabled by default.

New containers and sites are picked up automatically (containers once they're at least a minute old, so one-off
`docker run` containers don't create devices). When a container, site or service disappears from the dashboard,
its entities (and the container's device) are removed from Home Assistant; they're recreated if it comes back.

## Example automations

Entity IDs below assume a server named `myhost`; adjust to yours.

```yaml
automation:
  - alias: "Server needs a reboot"
    trigger:
      - platform: state
        entity_id: binary_sensor.myhost_reboot_required
        to: "on"
    action:
      - service: notify.notify
        data:
          message: >
            myhost needs a reboot
            ({{ state_attr('binary_sensor.myhost_reboot_required', 'reboot_packages') | join(', ') }}).

  - alias: "Site down"
    trigger:
      - platform: state
        entity_id:
          - binary_sensor.myhost_site_dashboard
          - binary_sensor.myhost_site_shortener
        to: "off"
        for: "00:02:00"
    action:
      - service: notify.notify
        data:
          message: >
            {{ trigger.to_state.name }} is down:
            HTTP {{ trigger.to_state.attributes.http_status }}
            {{ trigger.to_state.attributes.error or '' }}
            ({{ trigger.to_state.attributes.failing_host or trigger.to_state.attributes.url }})

  - alias: "TLS certificate expiring soon"
    trigger:
      - platform: numeric_state
        entity_id: sensor.myhost_cert_min_days_left
        below: 14
    action:
      - service: notify.notify
        data:
          message: "A TLS certificate on myhost expires in {{ states('sensor.myhost_cert_min_days_left') }} days."
```

## Development

```bash
python3.13 -m venv .venv && . .venv/bin/activate
pip install -r requirements_test.txt
pytest
```
