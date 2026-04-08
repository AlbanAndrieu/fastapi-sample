# Adapted from http://webpy.org/docs/0.3/tutorial
import random
import os

import web

# from redis.cluster import Redis
from redis.asyncio import Redis

urls = ("/", "index")
app = web.application(urls, globals())

REDIS_URL = os.environ.get("REDIS_URL", "redis://127.0.0.1:6379/0")

# Global variable declaration
redis: Redis | None


class index:
    def GET(self):
        redis = Redis.from_url(REDIS_URL, decode_responses=True)
        redis.set("randomnumber", random.randint(1, 27))  # noqa: S311 # nosec B311
        return str(redis.get("randomnumber"))


# web.wsgi.runwsgi = lambda func, addr=None: web.wsgi.runfcgi(func, addr)
if __name__ == "__main__":
    app.run()
