from locust import HttpUser, between, task


class QuickstartUser(HttpUser):
    wait_time = between(1, 2)

    def on_start(self):
        """on_start is called when a Locust start before any task is scheduled"""
        self.client.verify = False
        # self.login_page()

    # def login_page(self):
    #     self.client.post("/api/login", "verify=False", json={"Password":"xxxxx","ReturnUrl":"","UserName":"xxxx@gmail.com"})

    @task(2)
    def jm_test(self):
        # self.client.get("/en", verify=False)

        self.client.get("/en/conflict-checker?type=p2lf&ref=13&to=1205")

        # self.client.get(
        #    "/en/search?page=1&lang=en&document-types%5B0%5D=treaty", verify=False
        # )

        self.client.get(
            "/en/api/search?page=1&lang=en&document-types[0]=treaty", verify=False
        )

        self.client.get(
            '/en/api/search?query="hilton%20worldwide"&page=1&sort=desc&lang=en',
            verify=False,
        )

        self.client.get(
            "/en/document/treaty/en-qatar-turkey-bit-2001-qatar-turkey-bit-2001-tuesday-25th-december-2001",
            verify=False,
        )

        # self.client.get("/en/coverage/investment-arbitration", verify=False)

        self.client.get("/en/partnership/icc", verify=False)

        # self.client.post("/en/test?query=locus", verify=False)

        self.client.get(
            "/en/document/publication/en-arbitrator-disclosure", verify=False
        )

        # self.client.get("/hello")
        # self.client.get("/world")

    # @task(3)
    # def view_item(self):
    #     for item_id in range(10):
    #         self.client.get(f"/item?id={item_id}", name="/item")
