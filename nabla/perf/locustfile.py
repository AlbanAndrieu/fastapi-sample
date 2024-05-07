from locust import HttpUser, between, task


class QuickstartUser(HttpUser):
    wait_time = between(1, 2)

    def on_start(self):
        """on_start is called when a Locust start before any task is scheduled"""
        self.client.verify = False
        # self.login_page()

    # def login_page(self):
    # pylint: disable=line-too-long
    #     self.client.post("/api/login", "verify=False", json={"Password":"xxxxx","ReturnUrl":"","UserName":"xxxx@gmail.com"})

    # http://fastapi-sample.service.gra.dev.consul/

    @task
    def hello_world(self):
        self.client.get("/v1/items/1?q=test", verify=False)
        self.client.get("io_task", verify=False)
        self.client.get("cpu_task", verify=False)
        self.client.get("/v1/external-api", verify=False)

        # self.client.get("/hello")
        # self.client.get("/world")

    # @task(3)
    # def view_item(self):
    #     for item_id in range(10):
    #         self.client.get(f"/item?id={item_id}", name="/item")
