from locust import HttpUser, between, task

from nabla.logger import logger


class QuickstartUser(HttpUser):
    wait_time = between(1, 2)

    def on_start(self):
        """on_start is called when a Locust start before any task is scheduled"""
        self.client.verify = False
        # self.login_page()
        logger.info("QuickstartUser done")

    # def login_page(self):
    # pylint: disable=line-too-long
    #     self.client.post("/api/login", "verify=False", json={"Password":"xxxxx","ReturnUrl":"","UserName":"xxxx@gmail.com"})

    @task(2)
    def jm_front(self):
        # self.client.get("/en", verify=False)

        logger.info("Starting tests")

        # pylint: disable=line-too-long
        self.client.post(
            "/threads?locale=en",
            "verify=False",
            json={
                "question": "Can you write an arbitration agreement where ICC is the institution?",
                "type": "legal-research",
                "documents": [],
                "include_jm_documents": True,
            },
        )

        # self.client.get("/hello")
        # self.client.get("/world")
