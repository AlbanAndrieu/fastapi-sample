import openai
from grafana_openai_monitoring import chat_v2

# Set your OpenAI API key
openai.api_key = "YOUR_OPENAI_API_KEY"

# Apply the custom decorator to the OpenAI API function
openai.ChatCompletion.create = chat_v2.monitor(
    openai.ChatCompletion.create,
    metrics_url="YOUR_PROMETHEUS_METRICS_URL",  # Example: "https://prometheus.grafana.net/api/prom"
    logs_url="YOUR_LOKI_LOGS_URL",  # Example: "https://logs.example.com/loki/api/v1/push/"
    metrics_username="YOUR_METRICS_USERNAME",  # Example: "123456"
    logs_username="YOUR_LOGS_USERNAME",  # Example: "987654"
    access_token="YOUR_ACCESS_TOKEN",  # Example: "glc_eyasdansdjnaxxxxxxxxxxx"
)

# Now any call to openai.ChatCompletion.create will be automatically tracked
response = openai.ChatCompletion.create(
    model="gpt-4",
    max_tokens=100,
    messages=[{"role": "user", "content": "What is Grafana?"}],
)
print(response)
