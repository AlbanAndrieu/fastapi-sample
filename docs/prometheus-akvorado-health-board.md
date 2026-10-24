# Prometheus/Akvorado → FastAPI Cloud

**Cette procédure a été consolidée** dans
[le runbook d'acceptation observabilité](runbooks/fastapi-observability-acceptance.md).
La version du 24 octobre, avec ses détails de configuration et preuves,
est conservée [ici](archive/2026-10-24/prometheus-akvorado-health-board.md).

Le code FastAPI détient la projection, mais les scrapes et leurs
secrets sont déclarés par `nabla-compose`. Un scrape `UP` n'atteste
pas des flux NetFlow réels. Voir également
[roadmap active](engineering-roadmap.md).
