"""Transform TrueNAS applications into the homelab services JSON format."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

from nabla.integrations.truenas_client import TrueNASReadOnlyAdapter, build_truenas_adapter


def _host_ports(port_config: list[dict[str, Any]]) -> list[int]:
    """Return unique published ports, ignoring duplicate IPv4/IPv6 bindings."""
    return list(
        dict.fromkeys(
            host["host_port"]
            for mapping in port_config
            for host in mapping.get("host_ports", [])
            if isinstance(host.get("host_port"), int)
        )
    )


def _primary_port(app: dict[str, Any], ports: list[int]) -> int | None:
    """Prefer a Web UI portal port, then the first published port."""
    for portal in (app.get("portals") or {}).values():
        urls = portal if isinstance(portal, list) else [portal]
        for url in urls:
            if not isinstance(url, str):
                continue
            parsed = urlsplit(url)
            try:
                portal_port = parsed.port
            except ValueError:
                continue
            if portal_port in ports:
                return portal_port
    return ports[0] if ports else None


def _port_mappings(workloads: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalize TrueNAS port bindings into the homelab JSON shape."""
    return [
        {
            "containerPort": item.get("container_port"),
            "hostPorts": [
                {
                    "hostIp": host.get("host_ip"),
                    "hostPort": host.get("host_port"),
                }
                for host in item.get("host_ports") or []
            ],
            "protocol": item.get("protocol"),
        }
        for item in workloads.get("used_ports") or []
    ]


def app_to_service(app: dict[str, Any], *, internal_host: str | None) -> dict[str, Any]:
    """Create a compact public representation of one TrueNAS application."""
    workloads = app.get("active_workloads") or {}
    mappings = _port_mappings(workloads)
    published_ports = _host_ports(workloads.get("used_ports") or [])
    containers = [
        {
            "id": container.get("id"),
            "serviceName": container.get("service_name"),
            "image": container.get("image"),
            "state": container.get("state"),
            "ports": _port_mappings(
                {"used_ports": container.get("port_config") or []}
            ),
        }
        for container in workloads.get("container_details") or []
    ]

    return {
        "name": app.get("name", "?"),
        "id": app.get("id"),
        "status": app.get("state", app.get("status")),
        "internalHost": internal_host,
        "internalPort": _primary_port(app, published_ports),
        "hostPorts": published_ports,
        "ports": mappings,
        "containers": containers,
        "containerCount": workloads.get("containers", len(containers)),
        "images": workloads.get("images") or [],
        "portals": app.get("portals") or {},
        "version": app.get("version"),
        "humanVersion": app.get("human_version"),
        "latestVersion": app.get("latest_version"),
        "customApp": app.get("custom_app", False),
        "upgradeAvailable": app.get("upgrade_available", False),
        "imageUpdatesAvailable": app.get("image_updates_available", False),
    }


def get_truenas_apps_json(
    adapter: TrueNASReadOnlyAdapter | None = None,
) -> dict[str, Any]:
    """Return installed TrueNAS applications in homelab JSON format."""
    client = adapter or build_truenas_adapter()
    if client is None:
        raise RuntimeError("TrueNAS API credentials are not configured")

    internal_host = client.settings.hostname
    return {
        "version": 2,
        "services": [
            app_to_service(app, internal_host=internal_host)
            for app in client.list_apps()
        ],
    }
