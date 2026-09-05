"""Tests for cloud/PaaS runtime detection."""

from nabla.api import runtime_environment


def _clear_runtime_markers(monkeypatch) -> None:
    for name in (
        "FASTAPI_CLOUD",
        "FASTAPI_CLOUD_APP_ID",
        "SICKZ_NETWORK_LABEL",
        "VERCEL",
        "AWS_EXECUTION_ENV",
        "AWS_LAMBDA_FUNCTION_NAME",
        "KUBERNETES_SERVICE_HOST",
        "FLY_APP_NAME",
        "RAILWAY_ENVIRONMENT",
        "RAILWAY_PROJECT_ID",
        "HEROKU_APP_NAME",
        "DYNO",
    ):
        monkeypatch.delenv(name, raising=False)


def test_fastapi_cloud_detected_from_project_network_label(monkeypatch) -> None:
    _clear_runtime_markers(monkeypatch)
    monkeypatch.setenv("SICKZ_NETWORK_LABEL", "fastapicloud")

    assert runtime_environment.fastapi_cloud_runtime_detected() is True
    assert runtime_environment.runtime_mode() == "fastapi_cloud"


def test_fastapi_cloud_detected_from_request_hostname(monkeypatch) -> None:
    _clear_runtime_markers(monkeypatch)

    assert (
        runtime_environment.fastapi_cloud_runtime_detected(
            "fastapi-sample.fastapicloud.dev"
        )
        is True
    )
    assert (
        runtime_environment.runtime_mode("fastapi-sample.fastapicloud.dev")
        == "fastapi_cloud"
    )


def test_generic_paas_does_not_claim_fastapi_cloud(monkeypatch) -> None:
    _clear_runtime_markers(monkeypatch)
    monkeypatch.setenv("AWS_EXECUTION_ENV", "AWS_ECS_FARGATE")

    assert runtime_environment.fastapi_cloud_runtime_detected() is False
    assert runtime_environment.known_paas_runtime_detected() is True
    assert runtime_environment.runtime_mode() == "cloud_paas"


def test_workstation_without_markers_is_local(monkeypatch) -> None:
    _clear_runtime_markers(monkeypatch)

    assert runtime_environment.known_paas_runtime_detected() is False
    assert runtime_environment.runtime_mode() == "local"
