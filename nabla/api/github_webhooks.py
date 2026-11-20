"""Bounded, read-only GitHub workflow webhook projection. Never dispatch or apply."""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import re
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from redis.exceptions import RedisError

from nabla.api.runtime_environment import homelab_runtime_detected
from nabla.config_settings import get_settings

MAX_BODY = 256 * 1024
TTL = 7 * 86400
WORKFLOWS = {
    "AlbanAndrieu/fastapi-sample": ("docker-build.yml", "security-zap.yml", "master-red-remediation.yml"),
    "AlbanAndrieu/nabla-compose": ("entra.yml", "defectdojo-compose-handoff.yml"),
}
_PREFIX = "nabla:github-workflow:v1:"
_HEADERS = {"Cache-Control": "private, no-store", "X-Robots-Tag": "noindex, nofollow"}
# Fixed keys per allowlisted repo/workflow. Atomic ordering prevents stale receipts
# overwriting newer runs, even across concurrent pods or redeliveries.
_SAVE = """
local previous = redis.call('GET', KEYS[1])
if previous then
  local old = cjson.decode(previous)
  local new = cjson.decode(ARGV[1])
  if old.run_id > new.run_id or (old.run_id == new.run_id and old.attempt >= new.attempt) then
    return 0
  end
end
redis.call('SET', KEYS[1], ARGV[1], 'EX', ARGV[2])
return 1
"""


def response(status: int, code: str) -> JSONResponse:
    return JSONResponse({"state": code}, status_code=status, headers=_HEADERS)


def valid_signature(raw: bytes, secret: str, signature: str) -> bool:
    if not re.fullmatch(r"sha256=[0-9a-f]{64}", signature):
        return False
    expected = "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def project(payload: object, installation: int, *, now: datetime) -> tuple[str, dict] | None:
    if not isinstance(payload, dict) or payload.get("action") != "completed":
        return None
    install = payload.get("installation")
    repo = payload.get("repository")
    run = payload.get("workflow_run")
    if not all(isinstance(item, dict) for item in (install, repo, run)):
        return None
    if type(install.get("id")) is not int or install["id"] != installation:
        return None
    name = repo.get("full_name")
    if not isinstance(name, str) or name not in WORKFLOWS:
        return None
    path = run.get("path")
    if not isinstance(path, str) or not path.startswith(".github/workflows/"):
        return None
    workflow = path.removeprefix(".github/workflows/")
    head_repo = run.get("head_repository")
    if (workflow not in WORKFLOWS[name] or run.get("head_branch") != "master"
            or not isinstance(head_repo, dict) or head_repo.get("full_name") != name
            or run.get("status") != "completed"):
        return None
    sha, run_id, attempt = run.get("head_sha"), run.get("id"), run.get("run_attempt")
    conclusion = run.get("conclusion")
    if (not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{40}", sha)
            or type(run_id) is not int or not 0 < run_id < 2**53
            or type(attempt) is not int or not 0 < attempt <= 10000
            or conclusion not in ("success", "failure", "cancelled", "skipped", "timed_out", "action_required", "neutral", "stale", "startup_failure")):
        return None
    try:
        updated = datetime.fromisoformat(run["updated_at"].replace("Z", "+00:00"))
        age = (now - updated).total_seconds()
    except (KeyError, TypeError, ValueError, AttributeError):
        return None
    if not -60 <= age <= 86400:
        return None
    return _PREFIX + name + ":" + workflow, {
        "repository": name, "workflow": workflow, "run_id": run_id,
        "attempt": attempt, "sha": sha, "conclusion": conclusion,
        "updated_at": updated.astimezone(timezone.utc).isoformat(),
    }


def enabled(settings: object) -> bool:
    return homelab_runtime_detected() and getattr(settings, "github_webhook_enabled", False) is True


def register_github_webhook_routes(app: FastAPI) -> None:
    @app.post("/webhooks/github", include_in_schema=False)
    async def receive(request: Request) -> JSONResponse:
        settings = get_settings()
        if not enabled(settings):
            return response(404, "disabled")
        secret_value = getattr(settings, "github_webhook_secret", None)
        secret = secret_value.get_secret_value() if secret_value else ""
        installed = getattr(settings, "github_webhook_installation_id", 0)
        if len(secret) < 32 or installed <= 0:
            return response(503, "not_configured")
        signatures = request.headers.getlist("x-hub-signature-256")
        events = request.headers.getlist("x-github-event")
        if len(signatures) != 1 or len(events) != 1:
            return response(401, "signature_required")
        if request.headers.get("content-type", "").split(";", 1)[0].strip().lower() != "application/json":
            return response(415, "json_required")
        if request.headers.get("content-encoding", "identity").lower() != "identity":
            return response(415, "encoding_denied")
        body = bytearray()
        try:
            async with asyncio.timeout(5):
                async for chunk in request.stream():
                    if len(body) + len(chunk) > MAX_BODY:
                        return response(413, "too_large")
                    body.extend(chunk)
        except TimeoutError:
            return response(408, "body_timeout")
        raw = bytes(body)
        if not valid_signature(raw, secret, signatures[0]):
            return response(401, "invalid_signature")
        if events[0] == "ping":
            return response(200, "ping")
        if events[0] != "workflow_run":
            return response(200, "ignored")
        try:
            receipt = project(json.loads(raw), installed, now=datetime.now(timezone.utc))
        except (ValueError, UnicodeError, RecursionError):
            return response(400, "invalid_json")
        if receipt is None:
            return response(200, "ignored")
        redis = getattr(request.app.state, "redis", None)
        if redis is None:
            return response(503, "storage_unavailable")
        key, data = receipt
        try:
            async with asyncio.timeout(2):
                saved = await redis.eval(_SAVE, 1, key, json.dumps(data), TTL)
        except (RedisError, TimeoutError):
            return response(503, "storage_unavailable")
        return response(202 if saved else 200, "recorded" if saved else "duplicate_or_stale")

    @app.get("/api/homelab/github-workflows", include_in_schema=False)
    async def status(request: Request) -> JSONResponse:
        if not enabled(get_settings()):
            return response(404, "disabled")
        redis = getattr(request.app.state, "redis", None)
        if redis is None:
            return response(503, "storage_unavailable")
        keys = [_PREFIX + repo + ":" + workflow for repo, workflows in WORKFLOWS.items() for workflow in workflows]
        try:
            async with asyncio.timeout(2):
                records = await redis.mget(keys)
            items = [json.loads(item) for item in records if item is not None]
        except (RedisError, TimeoutError, ValueError, TypeError):
            return response(503, "storage_unavailable")
        return JSONResponse({"state": "observed" if items else "not_observed", "workflows": items}, headers=_HEADERS)
