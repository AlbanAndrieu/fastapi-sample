from urllib.parse import urlparse
from uuid import uuid4

from workers import Response


async def on_fetch(request, env):
    url = urlparse(request.url)
    if url.path == "/v1/message":
        return Response("Hello, World!")
    # TODO: add a route to get the redis connection
    if url.path == "/v1/random":
        myuuid = uuid4()
        print('Your UUID is: ' + str(myuuid))
        return Response(str(myuuid))
    return Response("Not Found", status=404)
