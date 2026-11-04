"""Evidence-aware connection matrix, built only from existing health-board data.

States describe individual observed layers, never global service availability.
No additional network access is performed by this projection.
"""

from __future__ import annotations

from typing import Any

from nabla.api.platform_health_diagnostics import utc_now

_DIAGNOSTIC_CATEGORIES = frozenset({
    "access_protected", "rate_limited", "http_failure", "http_rejected",
    "origin_unverified", "probe_timeout", "probe_error",
    "unexpected_content", "unexpected_json", "nxdomain", "no_a_answer",
    "dns_rcode_error", "invalid_dns_payload", "public_dns_observed",
    "anonymous_api_observed", "access_redirect", "authentication_rejected",
    "timeout", "connection_failed", "invalid_response", "query_failed",
    "truenas_auth", "truenas_access", "tunnel_attention",
})


def _data(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _row(
    identifier: str, label: str, state: str, source: str, detail: str,
    *, observed_at: str | None = None, status: int | None = None,
    category: str | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "id": identifier,
        "label": label,
        "state": state,
        "source": source,
        "detail": detail,
        "observed_at": observed_at,
    }
    if type(status) is int:
        result["http_status"] = status
    if category in _DIAGNOSTIC_CATEGORIES:
        result["diagnostic_category"] = category
    return result


def _truenas_rows(homelab: dict[str, Any]) -> list[dict[str, Any]]:
    truenas = _data(homelab.get("truenas"))
    api = _data(truenas.get("api"))
    public = _data(truenas.get("public"))
    internal = _data(truenas.get("internal"))
    observed_at = homelab.get("checked_at")

    api_reachable = api.get("reachable")
    api_category = (
        "truenas_auth"
        if api.get("phase") == "authentication" else
        "truenas_access"
        if api.get("stage") == "source_allowlist" else None
    )
    api_state = (
        "ok" if api_reachable is True else
        "warn" if api_reachable is False else "unknown"
    )
    public_state = public.get("state")
    https_state = (
        "ok" if public_state == "ok" else
        "warn" if public_state == "warn" else
        "fail" if public_state == "fail" else "unknown"
    )
    lan_state = (
        "ok" if internal.get("state") == "ok" else
        "warn" if internal.get("state") == "fail" else "unknown"
    )
    lan_detail = (
        "Direct TCP listener observed; not API authentication"
        if lan_state == "ok" else
        "LAN probe disabled or no valid observation"
        if not truenas.get("internal_probe_enabled") else
        "Direct TCP evidence unavailable or failed; inspect LAN listener"
    )
    return [
        _row("truenas_api", "TrueNAS authenticated API", api_state,
             "truenas_api_observer",
             "API reachable; management method results require separate checks"
             if api_state == "ok" else
             "API not confirmed; does not prove appliance outage",
             observed_at=observed_at, category=api_category),
        _row("truenas_lan", "TrueNAS LAN TCP", lan_state,
             "truenas_internal_tcp", lan_detail, observed_at=observed_at),
        _row("truenas_https", "TrueNAS HTTPS / HAProxy", https_state,
             "truenas_https_probe",
             "Public/WAN or direct path, distinct from API authorization",
             observed_at=observed_at,
             status=public.get("http_status")),
    ]


_SAMPLE_IDS = frozenset({"sample", "fastapi-sample"})


def _sample_probe_row(
    homelab: dict[str, Any],
    *,
    scope: str,
    label: str,
) -> dict[str, Any]:
    results = homelab.get(scope)
    candidates = [
        row for row in results
        if isinstance(row, dict) and row.get("id") in _SAMPLE_IDS
    ] if isinstance(results, list) else []
    observed = [
        row for row in candidates
        if row.get("probe_source") in {"origin", "memory"}
        and row.get("probe_stale") is not True
    ]
    # Multiple ambiguous observations never establish positive health.
    if len(observed) != 1:
        state, status, source = "unknown", None, None
    else:
        source = observed[0].get("probe_source")
        status = observed[0].get("http_status")
        raw_state = observed[0].get("state")
        state = raw_state if raw_state in {"ok", "warn", "fail"} else "unknown"
    return _row(
        "fastapi_truenas_" + ("lan" if scope == "internal_services" else "public"),
        label, state, "truenas_service_probe",
        "Last direct/retained transport probe; this does not establish application readiness"
        if state != "unknown" else
        "No recent direct service probe; not equivalent to exporter scrape status",
        observed_at=observed[0].get("probe_observed_at") if source else None,
        status=status,
    )


def _sample_app_rows(homelab: dict[str, Any]) -> list[dict[str, Any]]:
    services = homelab.get("services")
    matches = [
        row for row in services
        if isinstance(row, dict) and row.get("id") in _SAMPLE_IDS
    ] if isinstance(services, list) else []
    app = matches[0] if len(matches) == 1 else {}
    runtime_state = str(
        app.get("runtime_primary_container_state") or app.get("runtime_state") or ""
    ).upper()
    stale = homelab.get("truenas_runtime_stale") is True
    state = (
        "unknown" if stale or not app else
        "ok" if runtime_state in {"RUNNING", "HEALTHY"} else
        "warn" if runtime_state in {"STOPPED", "EXITED", "FAILED", "CRASHED"} else
        "unknown"
    )
    return [
        _row(
            "fastapi_truenas_runtime", "FastAPI Sample TrueNAS container runtime",
            state, "truenas_app_query",
            "TrueNAS reports a running container; HTTP/API readiness must be tested separately"
            if state == "ok" else
            "Container status absent, stale or not running; do not infer API outage",
            observed_at=homelab.get("checked_at") if not stale else None,
        ),
        _sample_probe_row(
            homelab, scope="public_probe_results",
            label="FastAPI Sample TrueNAS HTTPS transport",
        ),
        _sample_probe_row(
            homelab, scope="internal_services",
            label="FastAPI Sample TrueNAS LAN transport",
        ),
    ]


def _prometheus_rows(metrics: dict[str, Any]) -> list[dict[str, Any]]:
    state = metrics.get("state")
    configured = metrics.get("configured") is True
    query_state = (
        "ok" if state in {"healthy", "degraded"} and configured else
        "warn" if configured else "unknown"
    )
    jobs = _data(metrics.get("exporter_jobs"))
    observed_at = metrics.get("generated_at")
    query_error = metrics.get("error_kind")
    query_http = metrics.get("http_status")
    rows = [
        _row("prometheus_query", "Prometheus instant-query API", query_state,
             "prometheus_query", (
                 "Query succeeded; recording-rule coverage may be incomplete"
                 if query_state == "ok" else
                 "Query not confirmed; check credentials, Access policy and network"
                 if configured else "Prometheus URL not configured on this runtime"
             ), observed_at=observed_at, status=query_http,
             category=query_error)
    ]
    for job, label in (
        ("fastapi_sample", "FastAPI Sample scrape"),
        ("truenas_node", "TrueNAS node exporter"),
        ("cloudflare_exporter", "Cloudflare exporter"),
        ("gatus", "Gatus scrape"),
    ):
        up = jobs.get(job)
        if job == "gatus" and up is None:
            # Preserve the already-observed Gatus up signal even when a
            # service-exporter recording rule is not yet deployed.
            up = _data(metrics.get("synthetic_probes")).get("gatus_up")
        state = "ok" if up == 1 else "fail" if up == 0 else "unknown"
        rows.append(_row(
            "scrape_" + job, label, state, "prometheus_recording_rule",
            "Scrape target UP; application readiness is not established"
            if state == "ok" else
            "Scrape target DOWN; not proof of application outage"
            if state == "fail" else "No matching, fresh recording-rule sample",
            observed_at=observed_at,
        ))
    return rows


def _cloudflare_rows(homelab: dict[str, Any]) -> list[dict[str, Any]]:
    cf = _data(homelab.get("cloudflare"))
    confirmed = cf.get("status_confirmed") is True and cf.get("stale") is not True
    tunnels = cf.get("tunnels")
    tunnel_items = tunnels if isinstance(tunnels, list) else []
    statuses = [
        str(item.get("status") or "").lower()
        for item in tunnel_items if isinstance(item, dict)
    ]
    healthy = sum(value == "healthy" for value in statuses)
    attention = sum(value in {"down", "degraded", "inactive"} for value in statuses)
    tunnel_state = (
        "unknown" if not confirmed
        else "ok" if healthy and not attention and len(statuses) == healthy
        else "warn"
    )
    return [
        _row(
            "cloudflare_tunnels", "Cloudflare Tunnel control-plane inventory",
            "ok" if confirmed else "unknown",
            "cloudflare_control_plane",
            "Tunnel inventory confirmed; this does not verify any particular route"
            if confirmed else "Control-plane inventory unavailable or stale; edge status unknown",
        ),
        _row(
            "cloudflare_tunnel_runtime", "Cloudflare Tunnel reported lifecycle",
            tunnel_state,
            "cloudflare_tunnel_inventory",
            f"{healthy} healthy, {attention} inactive/degraded/down of {len(statuses)} observed; origin unverified"
            if confirmed else "No confirmed, fresh tunnel lifecycle evidence",
            category="tunnel_attention" if confirmed and tunnel_state == "warn" else None,
        ),
        _row(
            "cloudflare_access", "Cloudflare Access policies",
            "ok" if confirmed and cf.get("access_observer_state") == "ok" else "unknown",
            "cloudflare_access_control_plane",
            "Access inventory obtained; does not prove token validity or origin health"
            if confirmed and cf.get("access_observer_state") == "ok" else
            "Access inventory not confirmed",
        ),
    ]


def _external_rows(external: dict[str, Any]) -> list[dict[str, Any]]:
    cloud = _data(external.get("cloud"))
    observed_at = external.get("observed_at")
    cloud_state = cloud.get("state") if external.get("state") == "observed" else "unknown"
    if cloud_state not in {"ok", "warn", "fail", "unknown"}:
        cloud_state = "unknown"
    rows = [
        _row("fastapi_cloud", "FastAPI Cloud anonymous session", cloud_state,
             "truenas_outside_in_https",
             "Anonymous API JSON contract verified; authentication not implied"
             if cloud.get("origin_verified") is True else
             "Public endpoint not verified; protected responses and transport failures are distinct",
             observed_at=observed_at, status=cloud.get("http_status"),
             category=cloud.get("category"))
    ]
    dns = _data(external.get("cloudflare_public_dns"))
    for hostname, identifier in (
        ("sample.albandrieu.com", "dns_sample"),
        ("fastapi-sample.fastapicloud.dev", "dns_fastapi_cloud"),
    ):
        item = _data(dns.get(hostname))
        state = item.get("state") if external.get("state") == "observed" else "unknown"
        if state not in {"ok", "warn", "fail", "unknown"}:
            state = "unknown"
        rows.append(_row(
            identifier, f"Cloudflare DNS resolver: {hostname}", state,
            "cloudflare_recursive_doh",
            "Public resolver returned an A answer; NOT authoritative zone/tunnel/origin health"
            if state == "ok" else
            "Public DoH lookup unconfirmed or negative; inspect DNS without inferring origin health",
            observed_at=observed_at, status=item.get("http_status"),
            category=item.get("category"),
        ))
    return rows


def build_connection_matrix(
    homelab: dict[str, Any],
    platform_metrics: dict[str, Any],
    external: dict[str, Any],
) -> dict[str, Any]:
    """Return one bounded inventory of independent connection/evidence states."""
    rows = [
        *_truenas_rows(_data(homelab)),
        *_sample_app_rows(_data(homelab)),
        *_prometheus_rows(_data(platform_metrics)),
        *_cloudflare_rows(_data(homelab)),
        *_external_rows(_data(external)),
    ]
    return {
        "schema_version": 1,
        "generated_at": utc_now(),
        "scope": external.get("scope", "unknown"),
        "external_probe_state": external.get("state", "not_executed"),
        "external_cache_source": external.get("cache_source"),
        "rows": rows,
        "counts": {
            state: sum(row["state"] == state for row in rows)
            for state in ("ok", "warn", "fail", "unknown")
        },
        "semantics": (
            "Layer diagnostics only. Scrape DOWN is not service DOWN; "
            "Cloudflare DNS resolution or Access inventory is not origin health."
        ),
    }
