from prometheus_client import Counter, Gauge, Histogram

# See https://github.com/KenMwaura1/Fast-Api-Grafana-Starter/blob/main/src/app/main.py
# Define a counter metric
REQUESTS_COUNT = Counter(
    "requests_total", "Total number of requests", ["method", "endpoint", "status_code"]
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

DD_API_LATENCY = Histogram(
    name="dd_api_latency",
    documentation="The time taken for a call on the defact dojo api",
    labelnames=["api"],
    buckets=(1, 2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 25, 30, 40, 50),
)

DD_CRITICAL_FINDINGS_COUNT = Gauge(
    "dd_critical_findings_count",
    "The number of critical findings",
    labelnames=["product"],
)
DD_HIGH_FINDINGS_COUNT = Gauge(
    "dd_high_findings_count", "The number of high findings", labelnames=["product"]
)
DD_MEDIUM_FINDINGS_COUNT = Gauge(
    "dd_medium_findings_count", "The number of medium findings", labelnames=["product"]
)
DD_LOW_FINDINGS_COUNT = Gauge(
    "dd_low_findings_count", "The number of low findings", labelnames=["product"]
)
DD_INFO_FINDINGS_COUNT = Gauge(
    "dd_info_findings_count", "The number of info findings", labelnames=["product"]
)


# See https://github.com/blueswen/fastapi-observability/blob/main/fastapi_app/utils.py

INFO = Gauge("fastapi_app_info", "FastAPI application information.", ["app_name"])
REQUESTS = Counter(
    "fastapi_requests_total",
    "Total count of requests by method and path.",
    ["method", "path", "app_name"],
)
RESPONSES = Counter(
    "fastapi_responses_total",
    "Total count of responses by method, path and status codes.",
    ["method", "path", "status_code", "app_name"],
)
REQUESTS_PROCESSING_TIME = Histogram(
    "fastapi_requests_duration_seconds",
    "Histogram of requests processing time by path (in seconds)",
    ["method", "path", "app_name"],
)
EXCEPTIONS = Counter(
    "fastapi_exceptions_total",
    "Total count of exceptions raised by path and exception type",
    ["method", "path", "exception_type", "app_name"],
)
REQUESTS_IN_PROGRESS = Gauge(
    "fastapi_requests_in_progress",
    "Gauge of requests by method and path currently being processed",
    ["method", "path", "app_name"],
)
