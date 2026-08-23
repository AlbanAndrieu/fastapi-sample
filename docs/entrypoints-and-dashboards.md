# Entrypoints et Dashboards

Ce document liste les principaux entrypoints applicatifs (routes, fichiers) et les dashboards disponibles, pour une vue d'ensemble rapide.

## Entrypoints applicatifs

| Type          | Locaux/Fichiers          | URL/API                                                |
|--------------|--------------------------|--------------------------------------------------------|
| ASGI entry    | main.py                  | http://localhost:8091/                                 |
| FastAPI root  | fastapi_server.py        | http://localhost:8091/                                 |
| Health        | nabla/api/health_checks.py| http://localhost:8091/health, /healthz, /sickz         |
| OpenAPI       | fastapi_server.py        | http://localhost:8091/docs, /openapi.json              |
| Prometheus    | nabla/utils/prometheus.py| http://localhost:8091/metrics                          |
| Radar         | opencode.json            | http://localhost:8091/__radar/                         |
| Langfuse      | —                        | (URL à renseigner dans config)                         |
| Datadog       | —                        | (URL selon config DD_SERVICE/DD_ENV)                   |
| Pyroscope     | —                        | http://localhost:4040/                                 |
| Defect Dojo   | —                        | http://defectdojo.service.gra.uat.consul               |

## Dashboards détectés (opencode.json)

Les dashboards sont découverts via [scripts/discover_dashboards.py](../scripts/discover_dashboards.py).

| Nom                  | Description                      | URL                                 | Actif   |
|----------------------|----------------------------------|-------------------------------------|---------|
| fastapi-radar        | Dashboard radar FastAPI          | http://localhost:8091/__radar/      | Oui     |
| fastapi-radar-dashboard | Dashboard radar FastAPI        | http://localhost:8091/__radar/      | Oui     |

*Pour ajouter un dashboard, éditer opencode.json dans la clé 'command'.*

## Table d'accès rapide

- [Entrypoints API](http://localhost:8091/)
- [Documentation OpenAPI](http://localhost:8091/docs)
- [Radar Dashboard](http://localhost:8091/__radar/)
- [Prometheus (metrics)](http://localhost:8091/metrics)
- [Health check](http://localhost:8091/health)
- [Pyroscope](http://localhost:4040/)
- [Defect Dojo](http://defectdojo.service.gra.uat.consul)

---

> Généré automatiquement selon la configuration du projet.
