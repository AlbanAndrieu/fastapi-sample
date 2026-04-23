from functools import lru_cache

import pybreaker
from dotenv import load_dotenv
from fastapi import APIRouter
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, constr
from tenacity import retry, stop_after_attempt, wait_exponential

from nabla.ai.llm_factory import build_chat_llm
from nabla.utils.logger import logger

router = APIRouter()

# Made base from https://pub.towardsai.net/building-ai-workflows-with-fastapi-and-langgraph-step-by-step-guide-599937ab84f3

load_dotenv()

# Configure separate circuit breakers for the two external services:
# Both fail after 2 consecutive errors and open the circuit for 10 seconds.
circuit_breaker_llm = pybreaker.CircuitBreaker(fail_max=2, reset_timeout=10)


@lru_cache(maxsize=1)
def _get_workflow_llm() -> BaseChatModel:
    return build_chat_llm(model_name="gpt-5.1")


@retry(wait=wait_exponential(multiplier=1, min=2, max=10), stop=stop_after_attempt(3))
def safe_invoke_llm(message: str):
    return _get_workflow_llm().invoke([HumanMessage(content=message)])


def answer_question(state: dict) -> dict:
    logger.info(f"Received input: {state['user_input']}")
    try:
        response = safe_invoke_llm(state["user_input"])
        logger.info("LLM response generated")
        return {"answer": response.content}
    except Exception as e:
        return {"answer": f"Error: {e!s}"}


class RequestData(BaseModel):
    user_input: constr(min_length=1, max_length=500)  # limit input size


# Build the graph (must follow final answer_question definition)
workflow = StateGraph(dict)
workflow.add_node("answer", answer_question)
workflow.add_edge(START, "answer")
workflow.add_edge("answer", END)
graph = workflow.compile()


@router.post("/run")
# TODO @circuit_breaker_llm
async def run_workflow(data: RequestData):
    result = graph.invoke({"user_input": data.user_input})
    return {"result": result["answer"]}

