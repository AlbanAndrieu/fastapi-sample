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
    def jm_front(self):
        self.client.get("en/document/decision/fr-victor-pey-casado-and-president-allende-foundation-v-republic-of-chile-award-thursday-8th-may-2008#decision_849")
        self.client.get("en/document/decision/fr-association-oxfam-france-association-notre-affaire-a-tous-fondation-pour-la-nature-et-lhomme-association-greenpeace-france-v-france-jugement-du-tribunal-administratif-de-paris-wednesday-3rd-february-2021")
        self.client.get("en/document/treaty/en-libya-slovakia-bit-2009-libya-slovakia-bit-2009-friday-20th-february-2009")
    #     # self.client.get("/en", verify=False)

    #     self.client.get("/en/conflict-checker?type=p2lf&ref=13&to=1205")

    #     # self.client.get(
    #     #    "/en/search?page=1&lang=en&document-types%5B0%5D=treaty", verify=False
    #     # )

    #     self.client.get(
    #         "/en/api/search?page=1&lang=en&document-types[0]=treaty", verify=False
    #     )

    #     # TODO check why it is not working on Nomad dev but ok on uat
    #     self.client.get(
    #         '/en/search?query="hilton%20worldwide"&page=1&sort=desc&lang=en',
    #         verify=False,
    #     )

    #     self.client.get(
    #         "/en/document/treaty/en-qatar-turkey-bit-2001-qatar-turkey-bit-2001-tuesday-25th-december-2001",
    #         verify=False,
    #     )

    #     self.client.get(
    #         "/en/api/documents/publications/juris?page=1&items=12&show_volumes=false&group_journals=false",
    #         verify=False,
    #     )

    #     self.client.get(
    #         "/en/document/publication/en-arbitrator-disclosure", verify=False
    #     )

    #     # Documents
    #     # Big

    #     self.client.get(
    #         "/en/document/decision/fr-victor-pey-casado-and-president-allende-foundation-v-republic-of-chile-award-thursday-8th-may-2008#decision_849",
    #         verify=False,
    #     )

    #     # Mid
    #     self.client.get(
    #         "/en/document/decision/fr-association-oxfam-france-association-notre-affaire-a-tous-fondation-pour-la-nature-et-lhomme-association-greenpeace-france-v-france-jugement-du-tribunal-administratif-de-paris-wednesday-3rd-february-2021",
    #         verify=False,
    #     )

    #     # Small
    #     self.client.get(
    #         "/en/document/treaty/en-libya-slovakia-bit-2009-libya-slovakia-bit-2009-friday-20th-february-2009",
    #         verify=False,
    #     )

    #     # self.client.get("/en/coverage/investment-arbitration", verify=False)

    #     self.client.get("/en/partnership/icc", verify=False)

    #     self.client.get("/en/jus-ai-assistant", verify=False)

    #     # self.client.post("/en/test?query=locus", verify=False)

    #     self.client.get("/en/directory/arbitrators/all", verify=False)

    #     # self.client.get("/hello")
    #     # self.client.get("/world")

    # @task(3)
    # def jc_front(self):

    #     # JC Profiles

    #     # Big

    #     self.client.get(
    #         "/en/d/profile/institution/en-icc-international-chamber-of-commerce",
    #         verify=False,
    #     )

    #     # Mid

    #     self.client.get("/en/p/alexis-mourre", verify=False)

    #     # Small

    #     self.client.get("/en/p/daniel-jackson", verify=False)

    # @task(4)
    # def jm_back(self):

    #     self.client.get("/welcome", verify=False)

    #     self.client.get("/wiki/index", verify=False)

    # @task(4)
    # def view_item(self):
    #     for item_id in range(10):
    #         self.client.get(f"/item?id={item_id}", name="/item")
