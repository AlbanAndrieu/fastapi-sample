import requests
import os
from bs4 import BeautifulSoup

DOWNLAOD_URL = os.environ.get("REDIS_HOST", "https://example.com/resources/")


html = requests.get(DOWNLAOD_URL).text
soup = BeautifulSoup(html, "html.parser")
for link in soup.find_all("a", href=True):
    if link["href"].endswith(".pdf"):
        file_url = DOWNLAOD_URL + link["href"]
        file_data = requests.get(file_url).content
        open(link["href"], "wb").write(file_data)
