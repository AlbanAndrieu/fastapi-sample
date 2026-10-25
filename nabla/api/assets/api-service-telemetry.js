import { gatusCoverage, gatusServiceEvidence } from "./api-service-gatus-coverage.js";

// Read the ONE fixed Prometheus snapshot already present on /api/health-board.
// Never issue one Prometheus or Gatus request per service card.
const EXPORTERS = Object.freeze({
  pfsense: "pfsense_exporter",
  postgres: "postgres_exporter",
  postgresql: "postgres_exporter",
  redis: "redis_exporter",
  truenas: "truenas_node",
  "fastapi-sample": "fastapi_sample",
  pyroscope: "pyroscope",
  grafana: "grafana",
  prometheus: "prometheus",
  gatus: "gatus",
  "akvorado-inlet": "akvorado_inlet",
  "akvorado-outlet": "akvorado_outlet",
});

const ID_ALIASES = Object.freeze({ postgres: "postgresql" });

function observedBinary(value) {
  return typeof value === "number" && (value === 0 || value === 1);
}

function signal(label, value, source, detail) {
  const known = observedBinary(value);
  return {
    label,
    tone: !known ? "unknown" : value === 1 ? "ok" : "fail",
    status: !known ? "unknown" : value === 1 ? "up" : "down",
    detail: `${source}: ${known ? (value === 1 ? "observed UP" : "observed DOWN") : "not observed"}${detail ? " · " + detail : ""}`,
  };
}

function serviceIds(row) {
  const key = String(row?.dataset?.serviceKey || "").toLowerCase().trim();
  const clean = key.replace(/^albandrieu_/, "").replaceAll("_", "-");
  const topology = String(row?.dataset?.topologyId || "")
    .toLowerCase().trim().split("/").at(-1);
  // Legacy health-check keys and Backstage entityRefs may differ from the
  // nabla_service_id in Gatus. Never join merely by a display label.
  return [...new Set(
    [clean, topology, key, ID_ALIASES[clean], ID_ALIASES[key]]
      .filter(Boolean),
  )];
}

function serviceId(row) {
  const ids = serviceIds(row);
  const matched = ids.find((id) => Object.hasOwn(EXPORTERS, id)) ||
    ids[0] || "";
  return ID_ALIASES[matched] || matched;
}

export function serviceTelemetry(snapshot, row) {
  const metrics = snapshot?.platform_metrics;
  const id = serviceId(row);
  const sourceState = metrics?.state || "unavailable";
  const promValue = metrics?.metrics?.prometheus_up?.value;
  const prom = signal(
    "Prometheus",
    promValue,
    "Prometheus recording rule",
    sourceState,
  );
  const observations = serviceIds(row).map((key) =>
    gatusServiceEvidence(snapshot, key)
  );
  const perService = observations.find((item) => item.probes.length > 0) ||
    observations[0] || { status: "unverified", probes: [] };
  const monitored = perService.status !== "unverified";
  const probes = perService.probes;
  const gatus = {
    label: "Gatus",
    tone:
      !monitored || probes.length === 0
        ? "unknown"
        : probes.every((p) => p.success === 1)
          ? "ok"
          : "fail",
    status: !monitored
      ? "unavailable"
      : probes.length === 0
        ? "no_metric"
        : probes.every((p) => p.success === 1)
          ? "up"
          : "down",
    detail: !monitored
      ? "Gatus via Prometheus unavailable, truncated or stale; no direct Gatus request"
      : probes.length === 0
        ? `Gatus UP but no labeled per-service metrics for ${id}; inspect nabla_service_id and recording rules`
        : `Gatus via Prometheus: ${probes.map((p) => `${p.type}=${p.success === 1 ? "up" : "down"}${typeof p.availability === "number" ? ` (5m ${(p.availability * 100).toFixed(0)}%)` : ""}${typeof p.durationMs === "number" ? ` · ${p.durationMs.toFixed(0)} ms` : ""}`).join(", ")}`,
  };
  // Gatus itself is the scheduler, not the proof that every monitored
  // endpoint is green. Present observed failures and unknown coverage.
  const fleet = id === "gatus" ? gatusCoverage(snapshot) : null;
  const gatusFleet = fleet
    ? {
        label: fleet.down > 0 ? `Monitors ${fleet.down} ↓` :
          fleet.state !== "observed" || fleet.observedProbes === 0
            ? "Monitors ?" : `Monitors ${fleet.up} observed`,
        // A subset of labelled probes UP never means all catalogue
        // monitors are UP. Warn until declared-to-observed parity is proven.
        tone: fleet.state !== "observed" || fleet.observedProbes === 0
          ? "unknown"
          : fleet.down > 0 ? "fail" : "warn",
        status: fleet.state !== "observed" || fleet.observedProbes === 0
          ? "unverified"
          : fleet.down > 0 ? "probes_down" : "partial_coverage",
        detail: fleet.state !== "observed"
          ? `Gatus monitor evidence unverified: ${fleet.reason}`
          : `Gatus monitors: ${fleet.up} UP · ${fleet.down} DOWN across ${fleet.observedServices} observed services. Catalogue-wide coverage and freshness not proven.`,
      }
    : null;
  const job = EXPORTERS[id];
  let exporter = null;
  if (job) {
    const observed =
      job === "prometheus" ? promValue : metrics?.exporter_jobs?.[job];
    exporter = signal(
      "Exporter",
      observed,
      `Prometheus scrape job=${job}`,
      "scrape status only; does not establish application readiness",
    );
  }
  const inlet = metrics?.exporter_jobs?.akvorado_inlet;
  const outlet = metrics?.exporter_jobs?.akvorado_outlet;
  const flowServices = new Set([
    "prometheus",
    "akvorado-console",
    "akvorado-inlet",
    "akvorado-outlet",
  ]);
  const flow =
    flowServices.has(id)
      ? {
          label: "Akvorado",
          tone:
            !observedBinary(inlet) || !observedBinary(outlet)
              ? "unknown"
              : inlet === 1 && outlet === 1
                ? "ok"
                : "fail",
          status:
            !observedBinary(inlet) || !observedBinary(outlet)
              ? "unknown"
              : inlet === 1 && outlet === 1
                ? "scrapes_up"
                : "scrape_down",
          detail:
            "Prometheus targets · " +
            `inlet=${observedBinary(inlet) ? (inlet === 1 ? "UP" : "DOWN") : "not observed"} · ` +
            `outlet=${observedBinary(outlet) ? (outlet === 1 ? "UP" : "DOWN") : "not observed"}` +
            " · Scrape UP is not proof of NetFlow received, Kafka delivery or ClickHouse writes.",
        }
      : null;
  const functional =
    id === "postgresql"
      ? signal(
          "PostgreSQL",
          metrics?.summary?.optional_exporters?.postgres_up,
          "pg_up",
          "database connection, distinct from scrape up",
        )
      : id === "redis"
        ? signal(
            "Redis",
            metrics?.summary?.optional_exporters?.redis_up,
            "redis_up",
            "database connection, distinct from scrape up",
          )
        : null;
  const ram =
    metrics?.summary?.optional_exporters?.pfsense_memory_available_ratio;
  const resource =
    id === "pfsense"
      ? {
          label: "pfSense RAM",
          tone: "neutral",
          status:
            typeof ram === "number" &&
            Number.isFinite(ram) &&
            ram >= 0 &&
            ram <= 1
              ? "observed"
              : "unknown",
          detail:
            typeof ram === "number" &&
            Number.isFinite(ram) &&
            ram >= 0 &&
            ram <= 1
              ? `pfSense memory available: ${(ram * 100).toFixed(1)}% via Prometheus; not a reachability check`
              : "pfSense memory metric not observed; exporter UP alone does not prove resource health",
        }
      : null;
  return {
    prometheus: prom,
    gatus,
    gatusFleet,
    exporter,
    flow,
    functional,
    resource,
    serviceId: id,
  };
}
