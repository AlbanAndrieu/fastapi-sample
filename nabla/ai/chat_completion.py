import os

import openai
from grafana_openai_monitoring import chat_v2

from nabla.ai.llm_factory import litellm_openai_api_base
from nabla.config_settings import get_settings


def _resolve_openai_api_key_and_model() -> tuple[str, str]:
    """Prefer LiteLLM proxy, then Azure OpenAI, then ``OPENAI_API_KEY`` and default model."""
    settings = get_settings()
    litellm_url = (settings.litellm_url or "").strip()
    if litellm_url:
        return settings.litellm_api_key.get_secret_value(), "gpt-5"
    if settings.azure_openai_instance:
        instance = next(iter(settings.azure_openai_instance.values()))
        return instance.api_key, instance.available_models
    return os.environ["OPENAI_API_KEY"], "gpt-5"


_api_key, _default_chat_model = _resolve_openai_api_key_and_model()
openai.api_key = _api_key
_litellm_url = (get_settings().litellm_url or "").strip()
if _litellm_url:
    openai.api_base = litellm_openai_api_base(_litellm_url)

# Apply the custom decorator to the OpenAI API function
openai.ChatCompletion.create = chat_v2.monitor(
    openai.ChatCompletion.create,
    metrics_url=os.environ["YOUR_PROMETHEUS_METRICS_URL"],  # Example: "https://prometheus.grafana.net/api/prom"
    logs_url=os.environ["YOUR_LOKI_LOGS_URL"],  # Example: "https://logs.example.com/loki/api/v1/push/"
    metrics_username=os.environ["YOUR_METRICS_USERNAME"],  # Example: "123456"
    logs_username=os.environ["YOUR_LOGS_USERNAME"],  # Example: "987654"
    access_token=os.environ["YOUR_ACCESS_TOKEN"],  # Example: "glc_eyasdansdjnaxxxxxxxxxxx"
)

# Now any call to openai.ChatCompletion.create will be automatically tracked
response = openai.ChatCompletion.create(
    model=_default_chat_model,
    max_tokens=100,
    messages=[{"role": "user", "content": "What is Grafana?"}],
)
print(response)
