from fastapi import WebSocket
from starlette.websockets import WebSocketDisconnect

from nabla.api.demo.socket.ws_manager import manager


async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await manager.disconnect(websocket)
