from urllib.parse import urlparse
from uuid import uuid4

from workers import Response


async def on_fetch(request, env):
    url = urlparse(request.url)
    if url.path == "/v1/message":
        return Response("Hello, World!")
    # TODO: add a route to get the redis connection
    if url.path == "/v1/random":
        return Response(uuid4())
    return Response("Not Found", status=404)
