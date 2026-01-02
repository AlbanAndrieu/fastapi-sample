# Adapted from http://webpy.org/docs/0.3/tutorial
import random
import os

import web

# from redis.cluster import Redis
from redis.asyncio import Redis

urls = ("/", "index")
app = web.application(urls, globals())

REDIS_HOST = os.environ.get("REDIS_HOST", "127.0.0.1")
REDIS_PORT = int(os.environ.get("REDIS_PORT", 6379))  # noqa: PLW1508 # [invalid-envvar-default]

# Global variable declaration
redis: Redis | None


class index:
    def GET(self):
        redis = Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
        redis.set("randomnumber", random.randint(1, 27))  # noqa: S311 # nosec B311
        return str(redis.get("randomnumber"))


# web.wsgi.runwsgi = lambda func, addr=None: web.wsgi.runfcgi(func, addr)
if __name__ == "__main__":
    app.run()
