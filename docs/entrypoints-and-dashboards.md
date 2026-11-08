# Application entry points and local dashboards

The application serves HTTP, OpenAPI and MCP from the same FastAPI process.
FastAPI Radar is intentionally not installed and is not an MCP server.

## Application entry points

| Purpose | Command or module | Default URL |
| --- | --- | --- |
| FastAPI development | `uv run fastapi dev` | `http://127.0.0.1:8000` unless a port is supplied |
| Repository development | `uv run uvicorn server_all:app --reload --host 0.0.0.0 --port 8080` | `http://127.0.0.1:8080` |
| Docker Compose development stack | `docker compose -f docker-compose.yaml up` (`api`, `db`, `redis`) | `http://127.0.0.1:8080` |
| Docker Compose production-like image | `docker compose -f docker-compose.yaml up fastapi-sample` (profile `prod`) | `http://127.0.0.1:${FASTAPI_PORT:-8080}` |
| Docker Compose observability | `docker compose -f docker-compose.yaml --profile observability up prometheus grafana` | Prometheus `:9090`, Grafana `:3000` (loopback) |
| TrueNAS runtime | `compose.yml` (default Compose file here), deployed as the TrueNAS `sample` app | `http://127.0.0.1:8091` on the TrueNAS host |
| Production container | Gunicorn loads `server_all:app` | port `8080` |
| Python console script | `app` loads `server_app:app` | configured by `EXPOSE_HOST` and `EXPOSE_PORT` |

Use `server_all:app` for ASGI servers and deployment. Running
`python server_all.py` invokes the MCP object's native runner and is not the
normal FastAPI startup path.

## FastAPI and protocol endpoints

| Endpoint | Purpose | Availability |
| --- | --- | --- |
| `/docs` | Swagger UI generated from the complete application schema | Always |
| `/openapi.json` | OpenAPI schema used by Swagger UI and FastMCP | Always |
| `/mcp` | FastMCP Streamable HTTP transport | Always |
| `/a2a` | A2A JSON-RPC application | Only when `A2A_ENABLED` is true and its package imports |
| `/admin` | SQLAdmin UI | Controlled by the current Unleash configuration |
| `/ff` | Feature flags UI | Only when `DEBUG` is enabled |
| `/metrics` | Prometheus metrics | Always registered; operational access policy may require a key |
| `/health`, `/healthz`, `/sickz` | Health and detailed diagnostics | Detailed routes may require `DIAGNOSTICS_ACCESS_KEY` |
| `/api/public-topology` | Sanitized browser topology (no internal URLs/ports/evidence) | Always |
| `/api/homelab-services` | Full exposure/service catalog | May require `DIAGNOSTICS_ACCESS_KEY` |
| `/api/homelab/declared-services` | Full declared service inventory | May require `DIAGNOSTICS_ACCESS_KEY` |
| `/api/homelab-topology` | Full declared service topology | May require `DIAGNOSTICS_ACCESS_KEY` |
| `/api/homelab/runtime`, `/api/homelab/status` | TrueNAS runtime/reconciliation evidence | May require `DIAGNOSTICS_ACCESS_KEY` |

The project-level [`.mcp.json`](../.mcp.json) and
[`opencode.json`](../opencode.json) both target
`http://127.0.0.1:8080/mcp`. Start the API first; neither configuration starts
a second dashboard process.

## Transition de l'écran principal : observabilité réelle

| Chemin | Rôle | Données |
| --- | --- | --- |
| `/` | **Operations Overview** (vue légère, sans PostgreSQL) | `/api/ui/services` pour les comptes publics limités ; sondes, sécurité et ressources uniquement lorsque la session OWNER est authentifiée |
| `/api` | Catalogue, graphiques et diagnostic détaillé | Probes et services via l'API de diagnostic existante |
| `/api/topology` | Topologie des services | Source déclarative + télémétrie quand disponible |
| `/demo/sensors` | Ancienne démonstration, si le module DB est installé | Température, humidité et pression **synthétiques uniquement** |
| `/api/health-board` | Agrégat de santé mis en cache | Réutilise les sondes existantes |
| `/api/topology-telemetry` | Ressources cAdvisor et NetFlow (si configurés) | Cache Prometheus ; disponibilité distincte du service |
| `/api/home/metrics/history?window=1h\|24h\|7d` | Historique Prometheus propriétaire | 5 requêtes prédéfinies : CPU, mémoire, réseau, p95 HTTP et disponibilité Gatus (si exportée) |

La page `/` n'interroge pas la base de notes et ne démarre pas le générateur
de mesures météo. Les anciens endpoints `/stream`, `/chart-data`,
`/charts` et `/sensor-data` restent des contrats de démonstration.
Aucune requête Prometheus, TrueNAS ni Cloudflare n'est déclenchée directement
depuis le JavaScript de la page. Elle réutilise les caches serveur.

La session OWNER est vérifiée via `GET /api/ui/session` avant de charger
`/api/health-board`, `/api/topology-telemetry` et les trois fenêtres
de l'historique `/api/home/metrics/history`. Le serveur revérifie
l'authentification et la source autorisée pour ce nouvel endpoint.
Les visiteurs anonymes reçoivent **uniquement** la projection déjà exposée
par `/api/ui/services`. Sans preuve fraîche, tous les services sont inconnus.

CPU = cœurs réellement consommés, mémoire = MiB actifs, réseau = RX + TX
en KiB/s ; la sonde HTTP mesure une durée de requête **et non** le RTT IP.
La couverture et les sondes ponctuelles conservent 24 observations
**dans l'onglet courant**. Les courbes CPU/mémoire/réseau/p95/Gatus
utilisent le véritable historique Prometheus `query_range` à fenêtre fixe
(1 h, 24 h ou 7 j), au maximum 350 points par série. Les trous sont visibles.
Aucune mesure n'est fabriquée ; Gatus et p95 restent inconnus si la
métrique ou l'exporter manque. Les historiques n'exécutent aucun sondage LAN
supplémentaire depuis FastAPI Cloud.

Détails : [Runbook de transition de l'accueil](runbooks/home-operations-transition.md).

## Docker Compose dashboards

The repository Compose file also publishes independent development services:

| Service | URL | Notes |
| --- | --- | --- |
| Prometheus | `http://127.0.0.1:9090` | Reads `prometheus_data/prometheus.yml` |
| Grafana | `http://127.0.0.1:3000` | Uses the `grafana_data` volume |
| JupyterLab | `http://127.0.0.1:8888` | Development-only data-science image |

PostgreSQL and Redis bind only to loopback on ports 5432 and 6379. They are
service endpoints, not browser dashboards.

## FastAPI Radar decision

FastAPI Radar 0.3.4 is middleware mounted inside an existing FastAPI
application; it provides no module CLI and no MCP transport. Its dashboard can
record request and response bodies, headers, SQL and exceptions.

If Radar is introduced later, add it as one guarded feature with all of these
properties:

- disabled by default and disabled in production;
- an explicit authentication dependency;
- redaction rules for secrets, cookies, authorization headers and personal data;
- a documented retention policy for its DuckDB data;
- tests proving that disabled mode does not import or initialize it.

Do not add port 8091 or a fake OpenCode command until such a feature exists.
