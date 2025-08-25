# Adapted from http://webpy.org/docs/0.3/tutorial
import random
import os

import redis
import web

from redis.cluster import Redis

urls = ("/", "index")
app = web.application(urls, globals())

REDIS_HOST = os.environ.get("REDIS_HOST", "127.0.0.1")
REDIS_PORT = int(os.environ.get("REDIS_PORT", 6379)) # [invalid-envvar-default]

# Global variable declaration
redis_conn: Redis | None


class index:
    def GET(self):
        redis_conn = redis.StrictRedis(host=REDIS_HOST, port=REDIS_PORT)
        redis_conn.set("randomnumber", random.randint(1, 27))  # noqa: S311
        return str(redis_conn.get("randomnumber"))


# web.wsgi.runwsgi = lambda func, addr=None: web.wsgi.runfcgi(func, addr)
if __name__ == "__main__":
    app.run()
