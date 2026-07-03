from functools import lru_cache
from typing import Any

import anyio
import pybreaker
import sentry_sdk
from dotenv import load_dotenv
from fastapi import APIRouter
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field
from tenacity import retry, stop_after_attempt, wait_exponential

from nabla.ai.llm_factory import build_chat_llm
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


def _all_workflow_tools() -> tuple[Any, ...]:
    return (*_WORKFLOW_TOOLS, *build_openrag_mcp_tools())


_TOOLS_WITH_USER_QUESTION_FALLBACK = frozenset(
    {
        alban_me.fetch_my_profile.name,
        bababou.fetch_bababou_public_page.name,
    },
)

# Configure separate circuit breakers for the two external services:
# Both fail after 2 consecutive errors and open the circuit for 10 seconds.
circuit_breaker_llm = pybreaker.CircuitBreaker(fail_max=2, reset_timeout=10)


@lru_cache(maxsize=1)
def _get_workflow_llm() -> BaseChatModel:
    return build_chat_llm()


def _invoke_with_optional_tools(message: str) -> AIMessage:
    """Single-turn chat with optional tool calls (LangChain tool pattern, Sentry-friendly)."""
    llm = _get_workflow_llm()
    tools = list(_all_workflow_tools())
    llm_tools = llm.bind_tools(tools)
    tool_by_name = {t.name: t for t in tools}
    messages: list[Any] = [
        SystemMessage(content=alban_me.get_agent_system_prompt()),
        HumanMessage(content=message),
    ]
    max_tool_rounds = 6
    for _ in range(max_tool_rounds):
        ai_msg = llm_tools.invoke(messages)
        messages.append(ai_msg)
        if not ai_msg.tool_calls:
            return ai_msg
        for call in ai_msg.tool_calls:
            name = call["name"]
            args = call.get("args") or {}
            tool_fn = tool_by_name.get(name)
            if tool_fn is None:
                payload = f"Unknown tool: {name}"
            else:
                if name in _TOOLS_WITH_USER_QUESTION_FALLBACK and "user_question" not in args:
                    args = {**args, "user_question": message}
                payload = tool_fn.invoke(args)
            messages.append(
                ToolMessage(content=str(payload), tool_call_id=call["id"]),
            )
    return AIMessage(
        content="Tool loop limit exceeded; summarize with what you have so far.",
    )


@retry(wait=wait_exponential(multiplier=1, min=2, max=10), stop=stop_after_attempt(3))
def safe_invoke_llm(message: str):
    return _invoke_with_optional_tools(message)


def answer_question(state: dict) -> dict:
    logger.info(f"Received input: {state['user_input']}")
    try:
        response = safe_invoke_llm(state["user_input"])
        logger.info("LLM response generated")
        return {"answer": response.content}
    except Exception as e:
        return {"answer": f"Error: {e!s}"}


class RequestData(BaseModel):
    user_input: str = Field(min_length=1, max_length=500)


# Build the graph (must follow final answer_question definition)
workflow = StateGraph(dict)
workflow.add_node("answer", answer_question)
workflow.add_edge(START, "answer")
workflow.add_edge("answer", END)
graph = workflow.compile()


@router.post("/run")
# TODO @circuit_breaker_llm
async def run_workflow(data: RequestData):
    # Groups LangGraph + LangChain LLM spans under one trace root (Sentry AI monitoring).
    with sentry_sdk.start_transaction(name="nabla-ai-workflow", op="ai.langgraph"):
        result = await anyio.to_thread.run_sync(
            lambda: graph.invoke({"user_input": data.user_input}),
        )
    return {"result": result["answer"]}
