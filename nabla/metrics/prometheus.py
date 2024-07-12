from prometheus_client import Counter, Histogram

DD_API_LATENCY = Histogram(
    name="dd_api_latency",
    documentation="The time taken for a call on the defact dojo api",
    labelnames=["api"],
    buckets=(1, 2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 25, 30, 40, 50),
)

API_REQUEST_COUNTER = Counter(
    "api_request_counter",
    "Request processing time",
    ["method", "endpoint", "http_status"],
)
API_REQUEST_SUMMARY = Histogram(
    "api_request_summary", "Request processing time", ["method", "endpoint"]
)
# Define a histogram metric
REQUESTS_TIME = Histogram(
    "requests_time", "Request processing time", ["method", "endpoint"]
)
ERROR_COUNT = Counter("errors_total", "The total number of errors.", ["error"])
# See https://signoz.io/blog/opentelemetry-fastapi/
# https://github.com/SigNoz/sample-fastAPI-app/blob/main/app/main.py


# See https://github.com/KenMwaura1/Fast-Api-Grafana-Starter/blob/main/src/app/main.py
# Define a counter metric
REQUESTS_COUNT = Counter(
    "requests_total", "Total number of requests", ["method", "endpoint", "status_code"]
)
