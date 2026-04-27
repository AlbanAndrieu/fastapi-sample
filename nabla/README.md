<!-- markdown-link-check-disable-next-line -->

## [![Nabla](https://nabla.albandrieu.com/assets/nabla/nabla-4.png)](https://github.com/AlbanAndrieu) nabla-hooks

Nabla custom fastAPI

This project intend to be uses by all Nabla products

# Table of contents

<!-- markdown-link-check-disable -->

// spell-checker:disable

<!-- toc -->

- [Monitoring](#monitoring)

<!-- tocstop -->

// spell-checker:enable

## [Monitoring](#table-of-contents)

```bash
.venv/bin/uvicorn serve:app --host 0.0.0.0 --port 8091
```

[health](http://localhost:8091/health)
[ping](http://localhost:8091/ping)
[v1/ping](http://localhost:8091/v1/ping)
[metrics](http://localhost:8091/metrics)

[tracing worker sample](https://github.com/temporalio/samples-python/blob/main/open_telemetry/worker.py)

[prometheus fastAPI guide](https://dev.to/ken_mwaura1/getting-started-monitoring-a-fastapi-app-with-grafana-and-prometheus-a-step-by-step-guide-3fbn)
[prometheus fastAPI sample](https://github.com/SigNoz/sample-fastAPI-app/blob/main/app/main.py)
[grafana fastAPI sample](https://github.com/KenMwaura1/Fast-Api-Grafana-Starter/tree/main)
