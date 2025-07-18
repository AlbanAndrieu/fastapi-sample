# Adapted from http://webpy.org/docs/0.3/tutorial
import random

import redis
import web

urls = ("/", "index")
app = web.application(urls, globals())


class index:
    def GET(self):
        client = redis.StrictRedis(host="127.0.0.1", port=6379)
        client.set("randomnumber", random.randint(1, 9999))  # noqa: S311
        return str(client.get("randomnumber"))


# web.wsgi.runwsgi = lambda func, addr=None: web.wsgi.runfcgi(func, addr)
if __name__ == "__main__":
    app.run()
