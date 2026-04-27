from functools import lru_cache
from typing import Any

import anyio
import pybreaker
import sentry_sdk
from dotenv import load_dotenv
from fastapi import APIRouter
from pydantic import BaseModel, Field
from tenacity import retry, stop_after_attempt, wait_exponential

from deepagents import create_deep_agent

from nabla.deepagents.llm_factory import build_chat_llm
from nabla.api.users import bababou
from nabla.api.users import me as alban_me
from nabla.integrations.openrag_mcp_tools import build_openrag_mcp_tools
from nabla.utils.logger import logger

router = APIRouter()

# Made base from https://pub.towardsai.net/building-ai-workflows-with-fastapi-and-langgraph-step-by-step-guide-599937ab84f3

load_dotenv()


_WORKFLOW_TOOLS = (
    alban_me.fetch_my_profile,
    bababou.fetch_bababou_public_page,
)

_TOOLS_WITH_USER_QUESTION_FALLBACK = frozenset(
    {
        alban_me.fetch_my_profile.name,
        bababou.fetch_bababou_public_page.name,
    },
)


def _mcp_clients_signature() -> tuple[tuple[str, str, tuple[str, ...], bool], ...]:
    """Stable signature so the deep agent is rebuilt when MCP client definitions change."""
    from nabla.config_settings import get_settings  # noqa: PLC0415

    return tuple(
        (c.name, c.command, tuple(c.args), c.enabled) for c in get_settings().mcp_clients
    )


# Configure separate circuit breakers for the two external services:
# Both fail after 2 consecutive errors and open the circuit for 10 seconds.
circuit_breaker_llm = pybreaker.CircuitBreaker(fail_max=2, reset_timeout=10)


@lru_cache(maxsize=1)
def _get_workflow_llm():
    return build_chat_llm()


@lru_cache(maxsize=16)
def _build_workflow_agent(_sig: tuple[tuple[str, str, tuple[str, ...], bool], ...]) -> Any:
    """Compiled Deep Agents harness (LangGraph under the hood)."""
    llm = _get_workflow_llm()
    tools = list(_WORKFLOW_TOOLS) + build_openrag_mcp_tools()
    return create_deep_agent(
        model=llm,
        tools=tools,
        system_prompt=alban_me.get_agent_system_prompt(),
        debug=False,
        name="nabla-deep-agent",
    )


def _get_workflow_agent() -> Any:
    return _build_workflow_agent(_mcp_clients_signature())


def _invoke_agent(message: str) -> str:
    agent = _get_workflow_agent()
    result = agent.invoke({"messages": [{"role": "user", "content": message}]})
    messages = result.get("messages") or []
    if not messages:
        return ""
    last = messages[-1]
    return getattr(last, "content", "") or ""


@retry(wait=wait_exponential(multiplier=1, min=2, max=10), stop=stop_after_attempt(3))
def safe_invoke_llm(message: str):
    return _invoke_agent(message)


def answer_question(state: dict) -> dict:
    logger.info(f"Received input: {state['user_input']}")
    try:
        response = safe_invoke_llm(state["user_input"])
        logger.info("LLM response generated")
        return {"answer": response}
    except Exception as e:
        return {"answer": f"Error: {e!s}"}


class RequestData(BaseModel):
    user_input: str = Field(min_length=1, max_length=500)


@router.post("/run")
# TODO @circuit_breaker_llm
async def run_workflow(data: RequestData):
    # Groups LangGraph + LangChain LLM spans under one trace root (Sentry AI monitoring).
    with sentry_sdk.start_transaction(name="nabla-ai-workflow", op="ai.langgraph"):
        result = await anyio.to_thread.run_sync(
            lambda: answer_question({"user_input": data.user_input}),
        )
    return {"result": result["answer"]}

