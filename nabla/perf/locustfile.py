import random
from datetime import datetime
from locust import HttpUser, task, between

from nabla.utils.logger import logger


class FastAPIUser(HttpUser):
    wait_time = between(1, 3)

    # def login_page(self):
    # pylint: disable=line-too-long
    #     self.client.post("/api/login", "verify=False", json={"Password":"xxxxx","ReturnUrl":"","UserName":"xxxx@gmail.com"})

    @task(3)
    def get_user(self):
        user_id = random.randint(1, 1000)  # noqa: S311 # nosec
        self.client.get(f"/test/users/{user_id}")

    @task(1)
    def slow_endpoint(self):
        self.client.post("/test/users/register")

    @task(1)
    def error_endpoint(self):
        self.client.get("/test/exception")


class QuickStart(HttpUser):
    wait_time = between(1, 2)

    def on_start(self):
        """on_start is called when a Locust start before any task is scheduled"""
        self.client.verify = False
        # self.login_page()
        logger.info("QuickStart done")

    # http://fastapi-sample.service.gra.dev.consul/

    @task
    def hello_world(self):
        self.client.get("/", verify=False)  # give UI
        # self.client.get("io_task", verify=False)
        # self.client.get("cpu_task", verify=False)
        self.client.get("chain", verify=False)
        self.client.get("/v1/ping", verify=False)
        self.client.get("/v1/pong", verify=False)
        self.client.get("/v1/external-api", verify=False)
        self.client.get("/v1/internal-api", verify=False)
        self.client.get("/v1/items/1?q=test", verify=False)
        self.client.get("/v2/ping", verify=False)
        self.client.get("/test/users/0", verify=False)
        self.client.get("test/exception", verify=False)
        self.client.get("/test/env", verify=False)
        self.client.get("/test/invalid", verify=False)
        self.client.get("/llm/mcp", verify=False)
        self.client.get("/demo/items/0", verify=False)
        self.client.get("/sensor-data", verify=False)
        self.client.get("/charts", verify=False)
        self.client.get("/stats", verify=False)
        self.client.get("/stream/2", verify=False)
        self.client.get("/health", verify=False)
        self.client.get("/docs", verify=False)

    # @task(3)
    def view_item(self):
        for item_id in range(10):
            self.client.get(f"/demo/item?id={item_id}", name="/item")


class SensorEventUser(HttpUser):
    wait_time = between(0.01, 0.2)
    host = "http://localhost:8091"

    @task
    def post_event(self):
        timestamp = datetime.now()

        # Room temperature range (adjust if you live in Antarctica)
        self.min_temp = 18.0
        self.max_temp = 26.0
        self.min_humidity = 30.0
        self.max_humidity = 65.0

        payload = {
            "timestamp": timestamp.isoformat(),
            "temperature": round(random.uniform(self.min_temp, self.max_temp), 1),  # noqa: S311 # nosec
            "humidity": round(random.uniform(self.min_humidity, self.max_humidity), 1),  # noqa: S311 # nosec
            "pressure": round(random.uniform(1000, 1030), 1),  # noqa: S311 # nosec
            "status": random.choice(["normal", "warning", "critical"]),  # noqa: S311 # nosec
        }
        self.client.post("/events", json=payload)
