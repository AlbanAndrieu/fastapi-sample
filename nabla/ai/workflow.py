import pybreaker
from dotenv import load_dotenv
from fastapi import APIRouter
from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph

from nabla.utils.logger import logger

router = APIRouter()

load_dotenv()

# Configure separate circuit breakers for the two external services:
# Both fail after 2 consecutive errors and open the circuit for 10 seconds.
circuit_breaker_llm = pybreaker.CircuitBreaker(fail_max=2, reset_timeout=10)

llm = ChatOpenAI(model="gpt-4o")  # You can switch to gpt-4o-mini for cheaper calls

# Define state
def answer_question(state: dict) -> dict:
    user_input = state["user_input"]
    response = llm.invoke([HumanMessage(content=user_input)])
    return {"answer": response.content}
# Build the graph
workflow = StateGraph(dict)
workflow.add_node("answer", answer_question)
workflow.add_edge(START, "answer")
workflow.add_edge("answer", END)
graph = workflow.compile()

from tenacity import retry, stop_after_attempt, wait_exponential


@retry(wait=wait_exponential(multiplier=1, min=2, max=10), stop=stop_after_attempt(3))
def safe_invoke_llm(message):
    return llm.invoke([HumanMessage(content=message)])
def answer_question(state: dict) -> dict:
    user_input = state["user_input"]
    try:
        response = safe_invoke_llm(user_input)
        return {"answer": response.content}
    except Exception as e:
        return {"answer": f"Error: {e!s}"}

from pydantic import BaseModel, constr


class RequestData(BaseModel):
    user_input: constr(min_length=1, max_length=500)  # limit input size

def answer_question(state: dict) -> dict:
    logger.info(f"Received input: {state['user_input']}")
    response = safe_invoke_llm(state['user_input'])
    logger.info("LLM response generated")
    return {"answer": response.content}

from workflow import RequestData, graph


@router.post("/run")
# TODO @circuit_breaker_llm
async def run_workflow(data: RequestData):
    result = graph.invoke({"user_input": data.user_input})
    return {"result": result["answer"]}
