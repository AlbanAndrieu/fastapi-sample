from prometheus_client import Histogram

STEP_LATENCY = Histogram(
    name='dd_api_latency',
    documentation='The time taken for a call on the defact dojo api',
    labelnames=['api'],
    buckets=(1, 2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 25, 30, 40, 50),
)

OPENAI_LATENCY = Histogram(
    name='legal_research_openai_latency',
    documentation='The latency of the OpenAI response',
    buckets=(2, 5, 10, 20, 30, 40),
    labelnames=['client'],
)
