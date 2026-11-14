"""Offline regression tests for the Ollama client and workstation launcher."""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[2]
CLIENT = ROOT / "nabla" / "tools" / "client_ollama.py"
LAUNCHER = ROOT / "scripts" / "run-test-ollama.sh"


@pytest.fixture
def isolated_client(monkeypatch: pytest.MonkeyPatch):
    calls = []
    ollama = ModuleType("ollama")
    fastmcp = ModuleType("fastmcp")

    def chat(**kwargs):
        calls.append(kwargs)
        return {"message": {"content": "ok"}}

    ollama.chat = chat
    fastmcp.Client = object
    monkeypatch.setitem(sys.modules, "ollama", ollama)
    monkeypatch.setitem(sys.modules, "fastmcp", fastmcp)
    monkeypatch.delenv("DEFAULT_MODEL", raising=False)
    spec = importlib.util.spec_from_file_location("offline_ollama_client", CLIENT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, calls


def test_both_ollama_turns_keep_identical_gpu_settings(isolated_client) -> None:
    client, calls = isolated_client
    messages = [{"role": "user", "content": "hello"}]
    tools = [{"type": "function", "function": {"name": "add"}}]

    client.chat_with_model(messages, tools=tools)
    client.chat_with_model(messages, temperature=0)

    assert len(calls) == 2
    assert [call["options"] for call in calls] == [
        {"num_ctx": 32768},
        {"num_ctx": 32768, "temperature": 0},
    ]
    assert all(call["model"] == "bonsai-2:9b" for call in calls)
    assert all(call["think"] is False and call["stream"] is False for call in calls)
    assert calls[0]["tools"] == tools
    assert "tools" not in calls[1]
    assert client.OLLAMA_OPTIONS == {"num_ctx": 32768}


@pytest.mark.parametrize(
    ("show_status", "pull_status", "uv_status", "expected_code", "expect_pull"),
    [
        (0, 0, 0, 0, False),
        (1, 0, 0, 0, True),
        (1, 37, 0, 37, True),
        (0, 0, 23, 23, False),
    ],
)
def test_launcher_avoids_repull_and_propagates_errors(
    tmp_path: Path,
    show_status: int,
    pull_status: int,
    uv_status: int,
    expected_code: int,
    expect_pull: bool,
) -> None:
    bindir = tmp_path / "bin"
    bindir.mkdir()
    logfile = tmp_path / "commands.log"
    ollama = bindir / "ollama"
    ollama.write_text(
        '#!/usr/bin/env bash\n'
        'printf "ollama %s\\n" "$*" >> "$OLLAMA_TEST_LOG"\n'
        'if [[ "$1" == show ]]; then exit "$OLLAMA_SHOW_STATUS"; fi\n'
        'if [[ "$1" == pull ]]; then exit "$OLLAMA_PULL_STATUS"; fi\n'
        'exit 30\n',
        encoding="utf-8",
    )
    ollama.chmod(0o755)
    uv = bindir / "uv"
    uv.write_text(
        '#!/usr/bin/env bash\n'
        'printf "uv %s\\n" "$*" >> "$OLLAMA_TEST_LOG"\n'
        'exit "$OLLAMA_UV_STATUS"\n',
        encoding="utf-8",
    )
    uv.chmod(0o755)
    env = {
        **os.environ,
        "PATH": f"{bindir}:{os.environ['PATH']}",
        "OLLAMA_TEST_LOG": str(logfile),
        "OLLAMA_SHOW_STATUS": str(show_status),
        "OLLAMA_PULL_STATUS": str(pull_status),
        "OLLAMA_UV_STATUS": str(uv_status),
        "DEFAULT_MODEL": "bonsai-2:9b",
        "NO_COLOR": "true",
    }
    result = subprocess.run(
        ["bash", str(LAUNCHER)],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )

    assert result.returncode == expected_code, result.stderr
    commands = logfile.read_text(encoding="utf-8").splitlines()
    assert commands[0] == "ollama show bonsai-2:9b"
    assert ("ollama pull bonsai-2:9b" in commands) is expect_pull
    assert ("uv run python nabla/tools/client_ollama.py" in commands) is (
        show_status == 0 or pull_status == 0
    )
