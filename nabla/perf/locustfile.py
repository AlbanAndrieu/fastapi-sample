from locust import HttpUser, between, task


class QuickstartUser(HttpUser):
    wait_time = between(1, 2)

    def on_start(self):
        """on_start is called when a Locust start before any task is scheduled"""
        self.client.verify = False
        # self.login_page()

    # def login_page(self):
    #     self.client.post("/api/login", "verify=False", json={"Password":"xxxxx","ReturnUrl":"","UserName":"xxxx@gmail.com"})

    @task
    def hello_world(self):
        self.client.get("/en", verify=False)
        # self.client.get("/en/conflict-checker?type=p2lf&ref=13&to=1205")
        self.client.post("/en/coverage/investment-arbitration", verify=False)

        # self.client.get("/hello")
        # self.client.get("/world")

    # @task(3)
    # def view_item(self):
    #     for item_id in range(10):
    #         self.client.get(f"/item?id={item_id}", name="/item")
