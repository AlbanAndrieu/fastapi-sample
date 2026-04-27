"""In-process A2A (Agent-to-Agent) JSON-RPC server mounted at ``/a2a``."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import anyio

from nabla.config_settings import APIDeploymentSettings, get_settings

if TYPE_CHECKING:
    from starlette.applications import Starlette

def _agent_card(settings: APIDeploymentSettings):
    from a2a.types import a2a_pb2  # noqa: PLC0415
    from a2a.utils.constants import (  # noqa: PLC0415
        PROTOCOL_VERSION_CURRENT,
        TransportProtocol,
    )

    base = (settings.a2a_public_base_url or "").rstrip("/")
    iface_url = f"{base}/a2a/" if base else "/a2a/"

    card = a2a_pb2.AgentCard(
        name="nabla-deep-agent",
        description="Nabla DeepAgents workflow (LangGraph) exposed over A2A JSON-RPC.",
        version="1.0.0",
    )
    card.capabilities.streaming = False
    card.capabilities.push_notifications = False
    card.capabilities.extended_agent_card = False
    card.default_input_modes.append("text/plain")
    card.default_output_modes.append("text/plain")

    iface = card.supported_interfaces.add()
    iface.url = iface_url
    iface.protocol_binding = TransportProtocol.JSONRPC.value
    iface.protocol_version = PROTOCOL_VERSION_CURRENT

    skill = card.skills.add()
    skill.id = "nabla-workflow"
    skill.name = "Workflow"
    skill.description = "Single-turn Q&A with optional tools and MCP-backed OpenRAG search when configured."
    return card


def build_a2a_starlette_application(
    settings: APIDeploymentSettings | None = None,
) -> Starlette:
    """Build a Starlette app with agent card + JSON-RPC (mount under ``/a2a``)."""
    from a2a.server.agent_execution.agent_executor import AgentExecutor  # noqa: PLC0415
    from a2a.server.agent_execution.context import RequestContext  # noqa: PLC0415
    from a2a.server.events.event_queue_v2 import EventQueue  # noqa: PLC0415
    from a2a.server.request_handlers import DefaultRequestHandler  # noqa: PLC0415
    from a2a.server.routes.agent_card_routes import create_agent_card_routes  # noqa: PLC0415
    from a2a.server.routes.jsonrpc_routes import create_jsonrpc_routes  # noqa: PLC0415
    from a2a.server.tasks import InMemoryTaskStore  # noqa: PLC0415
    from a2a.utils.constants import AGENT_CARD_WELL_KNOWN_PATH, DEFAULT_RPC_URL  # noqa: PLC0415
    from starlette.applications import Starlette  # noqa: PLC0415
    from starlette.routing import Route  # noqa: PLC0415

    from nabla.deepagents.workflow import answer_question  # noqa: PLC0415

    class NablaDeepAgentExecutor(AgentExecutor):
        """Runs the same sync deep-agent path as ``/ai/run`` and returns a single A2A ``Message``."""

        async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
            from a2a.types import a2a_pb2  # noqa: PLC0415

            user_text = context.get_user_input()
            try:
                state = await anyio.to_thread.run_sync(
                    lambda: answer_question({"user_input": user_text}),
                )
            except Exception as exc:
                text = f"Error: {exc!s}"
            else:
                text = str(state.get("answer", ""))

            msg = a2a_pb2.Message(
                message_id=str(uuid.uuid4()),
                context_id=context.context_id or "",
                task_id=context.task_id or "",
                role=a2a_pb2.Role.ROLE_AGENT,
            )
            msg.parts.add().text = text
            await event_queue.enqueue_event(msg)

        async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
            return None

    s = settings or get_settings()
    card = _agent_card(s)
    task_store = InMemoryTaskStore()
    handler = DefaultRequestHandler(
        agent_executor=NablaDeepAgentExecutor(),
        task_store=task_store,
        agent_card=card,
    )
    routes: list[Route] = [
        *create_agent_card_routes(card, card_url=AGENT_CARD_WELL_KNOWN_PATH),
        *create_jsonrpc_routes(handler, rpc_url=DEFAULT_RPC_URL),
    ]
    return Starlette(routes=routes)
